import shutil
import time
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.database import get_db
from models.project import Project
from models.video import Video
from models.video_style import VideoStyle
from models.scenario import Scenario
from models.scene import Scene
from models.scene_asset import SceneAsset
from services.reading_db import export_readings, import_readings
from services.video_copy import (
    DUPLICATE_SKIP_DIRS, SCENARIO_FIELDS, SCENE_FIELDS, STYLE_FIELDS, apply_row, export_row,
)
from schemas.video import VideoCreate, VideoRead, VideoUpdate
from schemas.style import VideoStyleRead
from services.composition import generate_composition
from core.project_path import get_project_dir_name, get_project_dir

router = APIRouter(tags=["videos"])

PROJECTS_DIR = Path("/app/projects")
TEMPLATES_BLANK_DIR = Path("/app/templates/blank")

@router.get("/projects/{project_id}/videos", response_model=list[VideoRead])
async def list_videos(project_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).where(Video.project_id == project_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/projects/{project_id}/videos", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
async def create_video(project_id: str, payload: VideoCreate, db: AsyncSession = Depends(get_db)):
    stmt_p = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt_p)).scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    video_id = str(uuid.uuid4())
    video_dir = get_project_dir(project) / "videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    (video_dir / "assets/audio").mkdir(parents=True, exist_ok=True)
    (video_dir / "assets/images").mkdir(parents=True, exist_ok=True)
    (video_dir / "output").mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy(TEMPLATES_BLANK_DIR / "style.css", video_dir / "style.css")
        shutil.copy(TEMPLATES_BLANK_DIR / "app.js", video_dir / "app.js")
        shutil.copy(TEMPLATES_BLANK_DIR / "gsap.min.js", video_dir / "gsap.min.js")
        shutil.copy(TEMPLATES_BLANK_DIR / "chart.min.js", video_dir / "chart.min.js")
        shutil.copy(TEMPLATES_BLANK_DIR / "index.html", video_dir / "index.html")
        shutil.copy(TEMPLATES_BLANK_DIR / "meta.json", video_dir / "meta.json")
    except Exception as e:
        print(f"Template files copying failed: {e}")

    video = Video(
        id=video_id,
        project_id=project_id,
        name=payload.name,
        status="draft",
        output_dir=str(video_dir)
    )
    db.add(video)
    
    video_style = VideoStyle(
        video_id=video_id,
    )
    db.add(video_style)

    scenario = Scenario(
        video_id=video_id,
        source_type="paste",
    )
    db.add(scenario)

    await db.flush()
    return video

@router.get("/videos/{video_id}", response_model=VideoRead)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).where(Video.id == video_id)
    video = (await db.execute(stmt)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="動画が見つかりません")
    return video

@router.patch("/videos/{video_id}", response_model=VideoRead)
async def update_video(video_id: str, payload: VideoUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).where(Video.id == video_id)
    video = (await db.execute(stmt)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="動画が見つかりません")

    if payload.name is not None:
        video.name = payload.name
    if payload.status is not None:
        video.status = payload.status
    if payload.duration_sec is not None:
        video.duration_sec = payload.duration_sec

    await db.flush()
    return video

@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).where(Video.id == video_id)
    video = (await db.execute(stmt)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="動画が見つかりません")

    stmt_p = select(Project).where(Project.id == video.project_id)
    project = (await db.execute(stmt_p)).scalars().first()
    if project:
        video_dir = get_project_dir(project) / "videos" / video.id
        if video_dir.exists():
            shutil.rmtree(video_dir)

    await db.delete(video)
    await db.flush()

def _relocate_into(path: str | None, src_dir: Path, dst_dir: Path) -> str | None:
    """src_dir の中のファイルを指すパスを、コピー先の dst_dir の同じ場所に付け替える。

    src_dir の外を指している（古いデータなど）ときは、dst_dir/bgm にコピーしてから指す。
    ファイルが無ければ None（指す先の無いパスを残さない）。
    """
    if not path:
        return None
    src = Path(path)
    try:
        moved = dst_dir / src.resolve().relative_to(src_dir.resolve())
    except ValueError:
        if not src.exists():
            return None
        moved = dst_dir / "bgm" / src.name
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, moved)
    return str(moved) if moved.exists() else None


@router.post("/videos/{video_id}/duplicate", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
async def duplicate_video(video_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).where(Video.id == video_id)
    src_video = (await db.execute(stmt)).scalars().first()
    if not src_video:
        raise HTTPException(status_code=404, detail="複製元の動画が見つかりません")

    stmt_p = select(Project).where(Project.id == src_video.project_id)
    project = (await db.execute(stmt_p)).scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    new_video_id = str(uuid.uuid4())
    new_video_dir = get_project_dir(project) / "videos" / new_video_id

    src_dir = get_project_dir(project) / "videos" / video_id
    if src_dir.exists():
        # 画像素材と BGM は写す。音声・生成済みの動画・下見は写さない（#76）。
        # 音声は複製先で合成し直すので要らず、生成済みの動画は履歴を引き継がないため
        # どこからも参照されない。どちらも容量だけを食う。
        skip = {(src_dir / d).resolve() for d in DUPLICATE_SKIP_DIRS}
        shutil.copytree(
            src_dir, new_video_dir,
            ignore=lambda d, names: [n for n in names if (Path(d) / n).resolve() in skip],
        )
    for d in ("assets/audio", "assets/images", "output"):
        (new_video_dir / d).mkdir(parents=True, exist_ok=True)

    new_video = Video(
        id=new_video_id,
        project_id=src_video.project_id,
        name=f"{src_video.name} - コピー",
        status="draft",
        output_dir=str(new_video_dir),
        # 生成済みの尺は引き継がない（音声を合成し直すと変わる）
    )
    db.add(new_video)

    stmt_style = select(VideoStyle).where(VideoStyle.video_id == video_id)
    src_style = (await db.execute(stmt_style)).scalars().first()
    if src_style:
        # 引き継ぐ項目は services/video_copy.py の一覧で決める
        new_style = VideoStyle(video_id=new_video_id)
        apply_row(new_style, export_row(src_style, STYLE_FIELDS), STYLE_FIELDS)
        # BGM は複製先にコピーしたファイルを指し直す。元のファイルを指したままだと、
        # 複製先で BGM を差し替え・削除したときに元の動画の BGM が消える
        new_style.bgm_path = _relocate_into(src_style.bgm_path, src_dir, new_video_dir)
        db.add(new_style)

    stmt_scenario = select(Scenario).where(Scenario.video_id == video_id)
    src_scenario = (await db.execute(stmt_scenario)).scalars().first()
    if src_scenario:
        new_scenario = Scenario(video_id=new_video_id)
        apply_row(new_scenario, export_row(src_scenario, SCENARIO_FIELDS), SCENARIO_FIELDS)
        db.add(new_scenario)
        await db.flush()

        stmt_scenes = select(Scene).where(Scene.scenario_id == src_scenario.id).order_by(Scene.index)
        src_scenes = (await db.execute(stmt_scenes)).scalars().all()
        for s in src_scenes:
            # 音声とその長さは引き継がない（最初の生成で合成し直す）
            new_scene = Scene(scenario_id=new_scenario.id)
            apply_row(new_scene, export_row(s, SCENE_FIELDS), SCENE_FIELDS)
            db.add(new_scene)
            await db.flush()
            # このシーンだけの読み（#73）。本文に記号が無いので、写さないと読みが消える
            import_readings(db, await export_readings(db, scene_id=s.id), scene_id=new_scene.id)

            stmt_assets = select(SceneAsset).where(SceneAsset.scene_id == s.id)
            src_assets = (await db.execute(stmt_assets)).scalars().all()
            for asset in src_assets:
                new_asset = SceneAsset(
                    scene_id=new_scene.id,
                    slot=asset.slot,
                    asset_type=asset.asset_type,
                    file_path=asset.file_path,
                    svg_content=asset.svg_content,
                    display_config_json=asset.display_config_json
                )
                db.add(new_asset)

    await db.flush()
    return new_video


PROJECTS_DIR_V = Path("/app/projects")

@router.post("/videos/{video_id}/bgm", response_model=VideoStyleRead)
async def upload_bgm(
    video_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """BGM ファイルをアップロードして VideoStyle に保存する。"""
    # 動画 → プロジェクト
    stmt_v = select(Video).where(Video.id == video_id)
    video = (await db.execute(stmt_v)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="動画が見つかりません")

    stmt_p = select(Project).where(Project.id == video.project_id)
    project = (await db.execute(stmt_p)).scalars().first()

    # スタイル取得または作成
    stmt_s = select(VideoStyle).where(VideoStyle.video_id == video_id)
    style = (await db.execute(stmt_s)).scalars().first()
    if not style:
        style = VideoStyle(video_id=video_id)
        db.add(style)
        await db.flush()

    # 旧 BGM ファイルを削除
    if style.bgm_path and Path(style.bgm_path).exists():
        Path(style.bgm_path).unlink(missing_ok=True)

    # 新ファイルを保存
    ext = Path(file.filename or "bgm.mp3").suffix.lower() or ".mp3"
    bgm_dir = get_project_dir(project) / "videos" / video_id / "bgm"
    bgm_dir.mkdir(parents=True, exist_ok=True)
    dest = bgm_dir / f"bgm{ext}"
    dest.write_bytes(await file.read())

    style.bgm_path = str(dest)
    await db.flush()
    return style


@router.delete("/videos/{video_id}/bgm", response_model=VideoStyleRead)
async def delete_bgm(video_id: str, db: AsyncSession = Depends(get_db)):
    """BGM を削除する。"""
    stmt_s = select(VideoStyle).where(VideoStyle.video_id == video_id)
    style = (await db.execute(stmt_s)).scalars().first()
    if not style:
        raise HTTPException(status_code=404, detail="スタイルが見つかりません")

    if style.bgm_path and Path(style.bgm_path).exists():
        Path(style.bgm_path).unlink(missing_ok=True)

    style.bgm_path = None
    await db.flush()
    return style


@router.post("/videos/{video_id}/preview")
async def generate_slide_preview(video_id: str, scene_id: str | None = None,
                                 db: AsyncSession = Depends(get_db)):
    """スライド HTML プレビューを生成してアクセス URL を返す。

    scene_id を渡すと、そのシーンだけを繰り返し再生する URL（scene_preview_url）と、
    シーンの範囲（scene_start / scene_end、秒）も返す（#82）。
    音声が未合成のシーンは、文字数から見積もった長さで範囲が決まる（#58）。

    TTS 合成・動画レンダリングは行わない。
    音声ファイルが未生成の場合でも HTML は正常に出力される。
    """
    stmt_v = select(Video).where(Video.id == video_id)
    video = (await db.execute(stmt_v)).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="動画が見つかりません")

    stmt_p = select(Project).where(Project.id == video.project_id)
    project = (await db.execute(stmt_p)).scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    stmt_style = select(VideoStyle).where(VideoStyle.video_id == video_id)
    style = (await db.execute(stmt_style)).scalars().first()
    if not style:
        style = VideoStyle(video_id=video_id)

    stmt_scenario = select(Scenario).where(Scenario.video_id == video_id)
    scenario = (await db.execute(stmt_scenario)).scalars().first()
    if not scenario:
        raise HTTPException(status_code=400, detail="シナリオがまだ作成されていません")

    stmt_scenes = select(Scene).where(Scene.scenario_id == scenario.id).order_by(Scene.index)
    scenes = list((await db.execute(stmt_scenes)).scalars().all())
    if not scenes:
        raise HTTPException(status_code=400, detail="シーンがありません")

    video_dir = get_project_dir(project) / "videos" / video.id
    video_dir.mkdir(parents=True, exist_ok=True)

    stmt_assets = select(SceneAsset).where(
        SceneAsset.scene_id.in_([s.id for s in scenes])
    )
    all_assets = (await db.execute(stmt_assets)).scalars().all()
    assets_map: dict = {}
    for a in all_assets:
        assets_map.setdefault(a.scene_id, []).append(a)

    generate_composition(video, scenes, style, TEMPLATES_BLANK_DIR, video_dir, assets_map)

    # preview=1 … 再生コントロール付きのダッシュボードUIを表示させるフラグ。
    #             付けない場合はレンダリングと同じ「素のステージ」表示になる。
    # t=…       … iframe のキャッシュ回避（呼び出し側で付け足さなくて済むようにする）
    preview_url = (
        f"/projects/{get_project_dir_name(project)}/videos/{video.id}/index.html"
        f"?preview=1&t={int(time.time() * 1000)}"
    )
    result = {"preview_url": preview_url}

    if scene_id:
        # generate_composition が各シーンの data_start / data_duration を決めている
        scene = next((s for s in scenes if s.id == scene_id), None)
        if scene is None:
            raise HTTPException(status_code=404, detail="シーンが見つかりません")
        start = scene.data_start or 0.0
        end = start + (scene.data_duration or 0.0)
        # bare     … 操作バーなどを隠し、ステージだけを出す（モーダルに埋め込むため）
        # autoplay … 準備ができたら再生する
        # from/to  … 再生する範囲（秒）。loop で from に戻って繰り返す
        result.update({
            "scene_start": round(start, 2),
            "scene_end": round(end, 2),
            "scene_preview_url": f"{preview_url}&bare=1&autoplay=1&from={start:.2f}&to={end:.2f}&loop=1",
        })
    return result
