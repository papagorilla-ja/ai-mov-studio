from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.clock import utcnow
from core.database import get_db
from core.project_path import get_project_dir
from models.project import Project
from models.video import Video
from models.generation_history import GenerationHistory
from schemas.generation import GenerationHistoryRead
from workers.jobs import running_generations
from workers.progress import GenerationProgress
from workers.renderer import run_generation
from pathlib import Path
from urllib.parse import quote

from services.composition import PREVIEW_DIR_NAME
from services.subtitles import build_srt

# StaticFiles でそのまま配信しているコンテナ内のルート。
# 動画のフォルダは絶対パス (/app/projects/...) なので、ここを削って URL のパスに直す。
PROJECTS_MOUNT_ROOT = "/app"

router = APIRouter(tags=["generation"])
ws_router = APIRouter(tags=["ws"])

class ConnectionManager:
    """動画ごとの WebSocket の接続と、最後に送った進捗を持つ。"""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.latest_progress: dict[str, dict] = {}

    async def connect(self, video_id: str, websocket: WebSocket):
        await websocket.accept()
        if video_id not in self.active_connections:
            self.active_connections[video_id] = []
        self.active_connections[video_id].append(websocket)
        
        # 接続直後に、最新の進捗キャッシュがあれば送信して初期取りこぼしを防ぐ
        if video_id in self.latest_progress:
            try:
                await websocket.send_json(self.latest_progress[video_id])
            except Exception:
                pass

    def disconnect(self, video_id: str, websocket: WebSocket):
        connections = self.active_connections.get(video_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                del self.active_connections[video_id]

    async def broadcast(self, video_id: str, message: dict):
        self.latest_progress[video_id] = message
        # 送っている間に接続が増減しても大丈夫なよう、写しを回す。
        # 送れなかった接続（閉じている）は外す
        for connection in list(self.active_connections.get(video_id, [])):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(video_id, connection)

manager = ConnectionManager()

@ws_router.websocket("/ws/videos/{video_id}/generation-progress")
async def websocket_endpoint(websocket: WebSocket, video_id: str):
    await manager.connect(video_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(video_id, websocket)


@router.post("/videos/{video_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_video(
    video_id: str,
    regenerate_audio: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """動画生成を開始する。

    regenerate_audio=True の場合は、既存のナレーション音声とその TTS キャッシュを
    破棄してから全シーンを合成し直す。内容・話者・参照音声の録り直し（#98）で
    変わったシーンは、この指定が無くても作り直される。
    """
    stmt = select(Video).where(Video.id == video_id)
    video = (await db.execute(stmt)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="動画が見つかりません")

    # 二重生成を防ぐ（#96）。DB の印ではなく、実際に動いている処理で判断する
    if running_generations.is_running(video_id):
        raise HTTPException(status_code=400, detail="この動画は既に生成処理中です")
    # 実行中の印だけが残っているもの（再起動で途切れたなど）は失敗にしてから始める
    await _fail_orphaned_runs(video_id, db)

    history = GenerationHistory(video_id=video_id, status="running")
    db.add(history)
    # 「生成中」はここで付ける。裏の処理が付けるのを待つと、その間に
    # もう一度「生成」を押せてしまう
    video.status = "generating"
    await db.flush()
    generation_id = history.id

    running_generations.reserve(video_id, generation_id)
    try:
        await db.commit()
    except Exception:
        running_generations.release(video_id)
        raise

    progress = GenerationProgress(generation_id, lambda msg: manager.broadcast(video_id, msg))
    # 前回の最後の進捗（完了・失敗）を今回の最初の進捗に置き換える。残したままだと、
    # 今回の処理が最初の進捗を送る前に接続した画面へ、前回の「完了」が届いてしまう
    await manager.broadcast(video_id, progress.queued())
    running_generations.start(
        video_id, run_generation(video_id, generation_id, progress, regenerate_audio)
    )

    return {
        "message": "動画の生成処理を開始しました",
        "generation_id": generation_id,
        "regenerate_audio": regenerate_audio,
    }


async def _fail_orphaned_runs(video_id: str, db: AsyncSession) -> bool:
    """実行中の印が付いているのに、処理が動いていない生成を失敗にする。直したら True。

    api の再起動などで途切れた生成が「実行中」のまま残らないようにする。
    以前は開始から 60 分で一律に失敗にしていたため、長い動画ではまだ動いている
    生成を失敗扱いにし、同じ動画の生成をもう 1 つ始められてしまっていた（#96）。
    """
    if running_generations.is_running(video_id):
        return False
    histories = (await db.execute(
        select(GenerationHistory).where(
            GenerationHistory.video_id == video_id, GenerationHistory.status == "running"
        )
    )).scalars().all()
    video = (await db.execute(
        select(Video).where(Video.id == video_id, Video.status == "generating")
    )).scalars().first()
    if not histories and not video:
        return False
    for h in histories:
        h.status = "failed"
        h.error_message = "生成の処理が見つかりません（サーバーの再起動などで途切れました）"
        h.completed_at = utcnow()
    if video:
        video.status = "failed"
    await db.commit()
    return True


@router.post("/videos/{video_id}/generation/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_generation(video_id: str, db: AsyncSession = Depends(get_db)):
    """実行中の生成を止める（#96）。

    音声合成中なら次のシーンに進まずに止まり、レンダリング中ならレンダラーが
    hyperframes を終了させる。履歴は「中止」（cancelled）になる。
    """
    if running_generations.cancel(video_id):
        return {"message": "生成を中止しています"}
    if await _fail_orphaned_runs(video_id, db):
        return {"message": "途切れていた生成を終了扱いにしました"}
    raise HTTPException(status_code=409, detail="生成中ではありません")


@router.get("/videos/{video_id}/generation-status", response_model=GenerationHistoryRead)
async def get_generation_status(video_id: str, db: AsyncSession = Depends(get_db)):
    await _fail_orphaned_runs(video_id, db)
    stmt = (
        select(GenerationHistory)
        .where(GenerationHistory.video_id == video_id)
        .order_by(GenerationHistory.started_at.desc())
        .limit(1)
    )
    history = (await db.execute(stmt)).scalars().first()
    if not history:
        raise HTTPException(status_code=404, detail="生成履歴が見つかりません")
    return history


@router.get("/videos/{video_id}/preview")
async def get_render_preview(video_id: str, db: AsyncSession = Depends(get_db)):
    """レンダリング待ちの間に流す「音声なしの下見」の URL を返す。

    下見はレンダリング開始の直前に renderer が固める。
    それより前（音声合成中など）はまだ無いので available=false を返し、
    画面側はプレースホルダのままにする。
    """
    row = (await db.execute(
        select(Video, Project).join(Project, Project.id == Video.project_id).where(Video.id == video_id)
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="動画が見つかりません")
    video, project = row
    # 動画のフォルダはプロジェクトから求める。video.output_dir は、読み込んだ
    # プロジェクトの動画では空のため、下見が出なかった（#96）
    index_path = get_project_dir(project) / "videos" / video.id / PREVIEW_DIR_NAME / "index.html"
    if not index_path.exists():
        return {"available": False, "url": None}

    try:
        rel = index_path.relative_to(PROJECTS_MOUNT_ROOT)
    except ValueError:
        # 想定外の場所に出力している場合は URL に直せない
        return {"available": False, "url": None}

    # プロジェクト名に日本語が入るため、パスは必ずエンコードする。
    # クエリの意味:
    #   preview  … ダッシュボード用の表示モードに入る
    #   bare     … サイドバー等を隠してステージだけにする（埋め込み用）
    #   autoplay … 読み込み後に 1 度だけ再生する（ループしない）
    url = "/" + quote(str(rel)) + "?preview=1&bare=1&autoplay=1"
    return {"available": True, "url": url}


@router.get("/videos/{video_id}/generations", response_model=list[GenerationHistoryRead])
async def list_generations(video_id: str, db: AsyncSession = Depends(get_db)):
    await _fail_orphaned_runs(video_id, db)
    stmt = (
        select(GenerationHistory)
        .where(GenerationHistory.video_id == video_id)
        .order_by(GenerationHistory.started_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/generations/{gen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generation(gen_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(GenerationHistory).where(GenerationHistory.id == gen_id)
    history = (await db.execute(stmt)).scalars().first()
    if not history:
        raise HTTPException(status_code=404, detail="生成履歴が見つかりません")

    # 実行中の履歴は消せない。消すと、動いている生成が書き込む先を失う（#96）
    if running_generations.current(history.video_id) == history.id:
        raise HTTPException(status_code=400, detail="生成中の履歴は削除できません。中止してから削除してください。")
    if history.status == "running":
        # 処理の無い「実行中」（途切れたもの）は、動画の状態も戻してから消す
        await _fail_orphaned_runs(history.video_id, db)

    if history.output_path:
        Path(history.output_path).unlink(missing_ok=True)
        # この回の字幕（#97）
        Path(history.output_path).with_suffix(".srt").unlink(missing_ok=True)
    if history.thumbnail_path:
        Path(history.thumbnail_path).unlink(missing_ok=True)

    await db.delete(history)
    await db.commit()


@router.get("/generations/{gen_id}/download")
async def download_video(gen_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(GenerationHistory).where(GenerationHistory.id == gen_id)
    history = (await db.execute(stmt)).scalars().first()
    if not history:
        raise HTTPException(status_code=404, detail="生成履歴が見つかりません")

    if history.status != "completed" or not history.output_path:
        raise HTTPException(status_code=400, detail="この動画は生成中、または生成に失敗しています")

    path = Path(history.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")

    stmt_v = select(Video).where(Video.id == history.video_id)
    video = (await db.execute(stmt_v)).scalars().first()
    filename = f"{video.name if video else 'video'}.mp4"

    return FileResponse(
        path=str(path),
        media_type="video/mp4",
        filename=filename
    )


@router.get("/generations/{gen_id}/play")
async def play_video(gen_id: str, db: AsyncSession = Depends(get_db)):
    """インアプリ再生用のインライン・Range対応エンドポイント"""
    stmt = select(GenerationHistory).where(GenerationHistory.id == gen_id)
    history = (await db.execute(stmt)).scalars().first()
    if not history:
        raise HTTPException(status_code=404, detail="生成履歴が見つかりません")

    if history.status != "completed" or not history.output_path:
        raise HTTPException(status_code=400, detail="この動画は生成中、または生成に失敗しています")

    path = Path(history.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")

    # filename を指定しないことで Content-Disposition: inline 扱いとし、RangeRequests に対応させる
    return FileResponse(
        path=str(path),
        media_type="video/mp4"
    )


def _attachment(filename: str) -> str:
    """日本語のファイル名でも崩れない Content-Disposition（ASCII の代わりの名前も付ける）。"""
    return f"attachment; filename=\"subtitle.srt\"; filename*=UTF-8''{quote(filename)}"


@router.get("/generations/{gen_id}/subtitle.srt")
async def download_subtitle(gen_id: str, db: AsyncSession = Depends(get_db)):
    """生成完了済み動画の SRT 字幕をダウンロードする。

    生成が完了したときに、その回の本文と時刻で書き出した字幕を返す（#97）。
    後で本文を直しても、その回の動画と字幕は食い違わない。
    書き出すようになる前の履歴だけ、今の本文と時刻から作る。

    ファイル名は動画と同じ名前にする。動画（{名前}.mp4）と同じ場所に置くと、
    多くの再生ソフトが字幕を自動で読み込む。
    """
    from models.scenario import Scenario
    from models.scene import Scene
    from models.video_style import VideoStyle

    history = (await db.execute(
        select(GenerationHistory).where(GenerationHistory.id == gen_id)
    )).scalars().first()
    if not history or history.status != "completed":
        raise HTTPException(status_code=404, detail="完了済み生成が見つかりません")
    video = (await db.execute(select(Video).where(Video.id == history.video_id))).scalars().first()
    filename = f"{video.name if video else 'video'}.srt"

    saved = Path(history.output_path).with_suffix(".srt") if history.output_path else None
    if saved and saved.exists():
        content = saved.read_text(encoding="utf-8")
    else:
        scenario = (await db.execute(
            select(Scenario).where(Scenario.video_id == history.video_id)
        )).scalars().first()
        scenes = (await db.execute(
            select(Scene).where(Scene.scenario_id == scenario.id).order_by(Scene.index)
        )).scalars().all() if scenario else []
        style = (await db.execute(
            select(VideoStyle).where(VideoStyle.video_id == history.video_id)
        )).scalars().first()
        content = build_srt(scenes, style)
    if not content.strip():
        raise HTTPException(status_code=404, detail="字幕にできる本文がありません。先に動画を生成してください。")

    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-subrip",
        headers={"Content-Disposition": _attachment(filename)},
    )
