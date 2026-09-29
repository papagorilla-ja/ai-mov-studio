import asyncio
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.database import get_db
from models.video_style import VideoStyle
from models.scenario import Scenario
from models.scene import Scene
from models.scene_tts_cache import SceneTtsCache
from schemas.scene import SceneCreate, SceneRead, SceneUpdate, SceneReorder, AiDesignAdjustRequest
from schemas.scenario import NarrationGenerateRequest
from services.llm_service import (
    generate_narration as generate_narration_llm,
    generate_scene_content as generate_scene_content_llm,
    generate_image_prompt as generate_image_prompt_llm,
    ai_adjust_scene_design as ai_adjust_scene_design_llm
)
from services.composition import render_scene_preview_html, _validate_scene_html_fragment
from services.audio_utils import apply_speed
from services.design_tokens import narration_target_chars, normalize_narration_speed
from services.scene_context import build_scene_context, load_context_sources, load_scene_context
from services.reading import normalize_markup, strip_markup
from layouts import _registry as layouts
from layouts import _types
from services.reading_db import scene_lexicon
from services import scene_files, scene_tts
from services.scene_files import delete_scene_files, scene_video_dir
from services.tts_service import derive_seed
from workers.jobs import running_generations
from services.jobs import JobStore, preview_job_store
from routers.llm_errors import llm_error

router = APIRouter(tags=["scenes"])


async def _load_scene_style(db: AsyncSession, scene: Scene) -> VideoStyle:
    stmt_sc = select(Scenario).where(Scenario.id == scene.scenario_id)
    scenario = (await db.execute(stmt_sc)).scalars().first()
    if scenario:
        stmt_style = select(VideoStyle).where(VideoStyle.video_id == scenario.video_id)
        style = (await db.execute(stmt_style)).scalars().first()
        if style:
            return style
    return VideoStyle()


async def _run_preview_synthesis(job_id: str, scene_id: str) -> None:
    """バックグラウンドで試聴の音声を作り、結果をジョブストアに保存する。

    本番（動画の生成）と同じ条件で合成し、結果を本番のキャッシュに入れる（#98）。
      - 試聴した声が、そのまま動画の声になる（以前はシードと区切りが違い、別の声になっていた）
      - 試聴したシーンは、動画の生成で合成し直さない
      - 前に合成した音声がそのまま使えるなら、合成せずにそれを返す
    動画の生成中は、同じファイルを取り合わないよう、キャッシュには書かない。
    """
    from core.database import AsyncSessionLocal
    import tempfile
    from pathlib import Path

    async with AsyncSessionLocal() as db:
        try:
            stmt = select(Scene).where(Scene.id == scene_id)
            scene = (await db.execute(stmt)).scalars().first()
            if not scene:
                preview_job_store.update(job_id, status="error", error="シーンが見つかりません")
                return

            if not scene.narration_text:
                preview_job_store.update(job_id, status="error", error="ナレーションテキストが空です")
                return

            scenario = await db.get(Scenario, scene.scenario_id)
            video_id = scenario.video_id if scenario else None
            style = await _load_scene_style(db, scene)

            # 本番と同じ読み上げ用テキストで聴けるようにする（#60）。
            # 読みの確認をしていなければ、ここで AI に確認させて保存する。
            lexicon, _ = await scene_lexicon(scene, db, run_ai=True)
            await db.commit()
            inp = await scene_tts.prepare(scene, style, lexicon, scene_tts.SpeakerLookup(db))

            video_dir = await scene_video_dir(db, scene)
            cached = await db.get(SceneTtsCache, scene.id)
            generating = bool(video_id) and running_generations.is_running(video_id)
            # 本番と同じシード（動画の ID から）。同じ原稿からは同じ音声になる
            seed = derive_seed(video_id or scene.id)

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir_path = Path(tmpdir)
                if video_dir and scene_tts.cache_usable(cached, inp, scene):
                    # 前に合成した音声（本番か、前の試聴）をそのまま使う
                    raw_path = Path(cached.audio_path)
                    scene_tts.remember(db, cached, scene.id, inp, raw_path)
                elif video_dir and not generating:
                    # 本番のキャッシュへ合成する。区切りの秒数なども本番と同じく残す
                    raw_path = scene_files.raw_audio_path(video_dir, scene.id)
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    stats = await scene_tts.synthesize(inp, raw_path, seed)
                    scene_tts.apply_stats(scene, stats)
                    scene_tts.remember(db, cached, scene.id, inp, raw_path)
                else:
                    # 生成中（または動画のフォルダが分からない）は、試聴のためだけに作って捨てる
                    raw_path = tmp_dir_path / "preview.raw.wav"
                    await scene_tts.synthesize(inp, raw_path, seed)
                await db.commit()

                # 本番と同じ読み上げ速度で聴けるようにする。
                # ここだけ等倍だと、プレビューで速さを確かめられない。
                output_wav_path = tmp_dir_path / "preview.wav"
                await asyncio.to_thread(
                    apply_speed, raw_path, output_wav_path, normalize_narration_speed(style.narration_speed))
                audio_content = output_wav_path.read_bytes()
                preview_job_store.update(job_id, status="done", audio=audio_content)
        except Exception as e:
            preview_job_store.update(job_id, status="error", error=f"音声プレビュー生成エラー: {str(e)}")

@router.get("/videos/{video_id}/scenes", response_model=list[SceneRead])
async def list_scenes(video_id: str, db: AsyncSession = Depends(get_db)):
    stmt_sc = select(Scenario).where(Scenario.video_id == video_id)
    scenario = (await db.execute(stmt_sc)).scalars().first()
    if not scenario:
        return []
    
    stmt_scenes = select(Scene).where(Scene.scenario_id == scenario.id).order_by(Scene.index)
    result = await db.execute(stmt_scenes)
    return result.scalars().all()

@router.post("/videos/{video_id}/scenes", response_model=SceneRead, status_code=status.HTTP_201_CREATED)
async def create_scene(video_id: str, payload: SceneCreate, db: AsyncSession = Depends(get_db)):
    stmt_sc = select(Scenario).where(Scenario.video_id == video_id)
    scenario = (await db.execute(stmt_sc)).scalars().first()
    if not scenario:
        scenario = Scenario(video_id=video_id, source_type="paste")
        db.add(scenario)
        await db.flush()

    stmt_max = select(Scene.index).where(Scene.scenario_id == scenario.id).order_by(Scene.index.desc()).limit(1)
    max_index = (await db.execute(stmt_max)).scalar() or 0

    scene = Scene(
        scenario_id=scenario.id,
        index=max_index + 1,
        title=payload.title,
        layout_type=payload.layout_type,
        slide_content_json=payload.slide_content_json,
        # 読み・間の書式の表記ゆれをそろえて保存する（#73）
        narration_text=normalize_markup(payload.narration_text) if payload.narration_text else payload.narration_text,
        speaker_id=payload.speaker_id
    )
    db.add(scene)
    await db.flush()
    return scene

@router.get("/scenes/{scene_id}", response_model=SceneRead)
async def get_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")
    return scene

@router.patch("/scenes/{scene_id}", response_model=SceneRead)
async def update_scene(scene_id: str, payload: SceneUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    # model_fields_set: 明示的に送信されたフィールドだけを更新する
    # (null 送信でクリア可能、未送信フィールドは無視)
    fs = payload.model_fields_set
    if 'title' in fs:
        scene.title = payload.title
    if 'layout_type' in fs:
        # 見せ方を「別のものに変えた」＝ユーザーが選び直したということなので固定する。
        # 同じ値で保存し直しただけのときに固定してしまうと、
        # 内容を編集して保存するたびに勝手に「おまかせ」が外れる。
        # 明示的に layout_pinned が送られていれば、そちらを優先する（下で反映）。
        if payload.layout_type and payload.layout_type != scene.layout_type:
            scene.layout_pinned = True
        scene.layout_type = payload.layout_type
    if 'narration_length' in fs:
        scene.narration_length = payload.narration_length  # null 送信で動画の既定に戻る
    if 'layout_pinned' in fs and payload.layout_pinned is not None:
        scene.layout_pinned = payload.layout_pinned
    if 'slide_content_json' in fs:
        scene.slide_content_json = payload.slide_content_json
    if 'narration_text' in fs:
        # 読み・間の書式の表記ゆれ（全角・半角）をそろえてから比べる・保存する（#73）。
        # 比べる前にそろえないと、見た目が同じ本文でも「書き換えた」扱いになり、
        # 下の区切りを無駄に捨ててしまう。
        narration = (normalize_markup(payload.narration_text)
                     if payload.narration_text else payload.narration_text)
        # 本文を書き換えたら、#3 の区切り（narration_segments_json）は捨てる。
        # 区切りがあると音声合成は本文ではなく区切りの文字列を読むため、
        # 残すと「直したのに音声は直す前の文章を読む」ことになる。
        # 同じ本文で保存し直しただけなら残す（項目の出るタイミングを失わないため）。
        if narration != scene.narration_text:
            scene.narration_segments_json = None
        scene.narration_text = narration
    if 'outline_summary' in fs:
        scene.outline_summary = payload.outline_summary  # null 送信でクリア可
    if 'image_prompt' in fs:
        scene.image_prompt = payload.image_prompt  # null 送信でクリア可
    if 'speaker_id' in fs:
        scene.speaker_id = payload.speaker_id  # null 送信でクリア可
    if 'speaker_b_id' in fs:
        scene.speaker_b_id = payload.speaker_b_id  # null 送信でクリア可
    if 'data_start' in fs:
        scene.data_start = payload.data_start
    if 'data_duration' in fs:
        scene.data_duration = payload.data_duration
    if 'custom_html' in fs:
        scene.custom_html = payload.custom_html  # null 送信でクリア可
    if 'custom_css' in fs:
        scene.custom_css = payload.custom_css

    await db.flush()
    return scene


@router.get("/scenes/{scene_id}/effective-html")
async def get_scene_effective_html(scene_id: str, db: AsyncSession = Depends(get_db)):
    """このシーンの「現在の実効 HTML/CSS」を返す（custom_html があればそれ、なければ自動生成結果）。"""
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    style = await _load_scene_style(db, scene)
    return {
        "html": render_scene_preview_html(scene, style),
        "css": scene.custom_css or "",
        "is_custom": bool(scene.custom_html),
    }


@router.post("/scenes/{scene_id}/ai-design-adjust", response_model=SceneRead)
async def ai_design_adjust(scene_id: str, payload: AiDesignAdjustRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    style = await _load_scene_style(db, scene)
    current_html = render_scene_preview_html(scene, style)
    scene_dom_id = f"scene-{scene.id}"
    style_vars = {
        "color_primary": style.color_primary,
        "color_secondary": style.color_secondary,
        "color_accent": style.color_accent,
        "color_bg": style.color_bg,
        "color_text_primary": style.color_text_primary,
    }

    try:
        result = await ai_adjust_scene_design_llm(
            current_html=current_html,
            current_css=scene.custom_css or "",
            instruction=payload.instruction,
            scene_dom_id=scene_dom_id,
            style_vars=style_vars,
        )
    except (ValueError, RuntimeError) as e:
        raise llm_error(e, "AI デザイン調整") from e

    ok, err = _validate_scene_html_fragment(result["html"])
    if not ok:
        raise HTTPException(status_code=502, detail=f"AIの生成結果が不正でした: {err}")

    scene.custom_html = result["html"]
    scene.custom_css = result["css"]
    await db.flush()
    return scene

@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    scenario_id = scene.scenario_id
    # 音声・キャッシュ・画像素材のファイルも消す（#92。残すと溜まり続ける）
    await delete_scene_files(db, scene)
    await db.delete(scene)
    await db.flush()

    stmt_scenes = select(Scene).where(Scene.scenario_id == scenario_id).order_by(Scene.index)
    scenes = (await db.execute(stmt_scenes)).scalars().all()
    for idx, s in enumerate(scenes, start=1):
        s.index = idx
    await db.flush()

@router.post("/scenes/{scene_id}/reorder", response_model=list[SceneRead])
async def reorder_scene(scene_id: str, payload: SceneReorder, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    target_scene = (await db.execute(stmt)).scalars().first()
    if not target_scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    scenario_id = target_scene.scenario_id
    stmt_scenes = select(Scene).where(Scene.scenario_id == scenario_id).order_by(Scene.index)
    scenes = list((await db.execute(stmt_scenes)).scalars().all())

    if target_scene in scenes:
        scenes.remove(target_scene)

    new_index = payload.new_index
    if new_index < 1:
        new_index = 1
    elif new_index > len(scenes) + 1:
        new_index = len(scenes) + 1

    scenes.insert(new_index - 1, target_scene)

    for idx, s in enumerate(scenes, start=1):
        s.index = idx

    await db.flush()
    return scenes

@router.post("/scenes/{scene_id}/preview-audio/start", status_code=status.HTTP_202_ACCEPTED)
async def start_preview_audio(scene_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """プレビュー音声合成をバックグラウンドで開始し、ジョブIDを即座に返す。
    TTS 合成に時間がかかっても HTTP リクエスト自体はすぐに完了するため、
    フロントエンド側のタイムアウトに引っかからない。"""
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")
    if not scene.narration_text:
        raise HTTPException(status_code=400, detail="ナレーションテキストが空です")

    job_id = str(uuid.uuid4())
    preview_job_store.register(job_id)
    background_tasks.add_task(_run_preview_synthesis, job_id, scene_id)
    return {"job_id": job_id}


@router.get("/scenes/preview-audio/{job_id}/status")
async def get_preview_audio_status(job_id: str):
    """ポーリング用: ジョブの現在の状態を返す（軽量・即時応答）。"""
    job = preview_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません（期限切れの可能性があります）")
    return {"status": job["status"], "error": job["error"]}


@router.get("/scenes/preview-audio/{job_id}/audio")
async def get_preview_audio_result(job_id: str):
    """合成が完了したジョブから WAV バイナリを取得する。"""
    job = preview_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません（期限切れの可能性があります）")
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job["error"] or "音声合成に失敗しました")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="音声はまだ準備中です")
    return Response(content=job["audio"], media_type="audio/wav")


async def _video_context(scene: Scene, db: AsyncSession) -> tuple[str, str | None, str | None]:
    """シーンが属する動画の (縦横比, レイアウトの幅, ナレーション長の既定) を引く。

    縦横比と幅はレイアウトの自動差し替えに、ナレーション長は内容生成に使う。
    取れなければ既定（16:9 / レジストリ既定 / 標準）に委ねる。
    """
    stmt = (
        select(VideoStyle.canvas_width, VideoStyle.canvas_height,
               VideoStyle.layout_breadth, VideoStyle.narration_length)
        .join(Scenario, Scenario.video_id == VideoStyle.video_id)
        .where(Scenario.id == scene.scenario_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return "16:9", None, None
    width, height, breadth, length = row
    aspect = "4:3" if ((width or 1920) / (height or 1080)) < 1.5 else "16:9"
    return aspect, breadth, length


def _effective_narration_length(scene: Scene, video_default: str | None) -> str | None:
    """このシーンに効くナレーション長。

    シーン個別が入っていればそれを、無ければ動画の既定を使う。
    どちらも無ければ None（正規化側で「標準」に落ちる）。
    """
    return getattr(scene, "narration_length", None) or video_default


async def _previous_layout(scene: Scene, db: AsyncSession) -> tuple[str, ...]:
    """直前のシーンで使った見せ方。同じものが続くのを避けるために渡す。"""
    stmt = (
        select(Scene.layout_type)
        .where(Scene.scenario_id == scene.scenario_id, Scene.index < scene.index)
        .order_by(Scene.index.desc()).limit(1)
    )
    prev = (await db.execute(stmt)).scalars().first()
    return (prev,) if prev else ()


async def apply_generated_content(scene: Scene, result: dict) -> None:
    """generate_scene_content の結果をシーンへ反映する。

    レイアウトも結果に含まれる（AI が選び、件数の検査で必要なら差し替わっている）。
    内容は既に型のスキーマへ正規化済みなので、ここで整形はしない。
    """
    scene.layout_type = result["layout"]
    content = dict(result["slide_content_json"])
    if not content.get("title"):
        content["title"] = scene.title or ""
    scene.slide_content_json = json.dumps(content, ensure_ascii=False)
    if result.get("narration_text"):
        scene.narration_text = result["narration_text"]
    # 区切りはナレーションと対で意味を持つ。本文を更新したときだけ入れ替える
    # （古い本文に新しい区切りが残ると、語られていない項目が先に出る）。
        segments = result.get("narration_segments") or []
        # starts は音声合成のときに入る。ここでは本文だけ保存する。
        scene.narration_segments_json = (
            json.dumps({"texts": segments}, ensure_ascii=False) if segments else None
        )
    if result.get("layout_reason"):
        print(f"[layouts] scene {scene.index}: {result['layout_reason']}")


@router.post("/scenes/{scene_id}/generate-content", response_model=SceneRead)
async def generate_scene_content(scene_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    aspect, _, video_length = await _video_context(scene, db)
    # 見せ方が固定されていれば、連続回避（avoid）も効かせない。
    # 「直前と同じだから変える」はユーザーの選択を覆す理由にならない。
    pinned = bool(getattr(scene, "layout_pinned", False))
    try:
        result = await generate_scene_content_llm(
            title=scene.title or "",
            summary=scene.outline_summary or "",
            layout_type=scene.layout_type or "text_only",
            aspect=aspect,
            avoid=() if pinned else await _previous_layout(scene, db),
            narration_length=_effective_narration_length(scene, video_length),
            layout_pinned=pinned,
            # 何番目のシーンか・全体の構成・元資料を添える。
            # 無いと途中のシーンでも「こんにちは」から始めてしまう（#53）
            context=(await load_scene_context(scene, db)).to_prompt(),
        )
    except (ValueError, RuntimeError) as e:
        raise llm_error(e, "シーン内容の生成") from e
    await apply_generated_content(scene, result)
    await db.flush()
    return scene


@router.post("/scenes/{scene_id}/generate-image-prompt", response_model=SceneRead)
async def generate_image_prompt(scene_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")
    try:
        content = json.loads(scene.slide_content_json) if scene.slide_content_json else {}
    except Exception:
        content = {}
    try:
        result = await generate_image_prompt_llm(
            title=scene.title or "",
            summary=scene.outline_summary or "",
            layout_type=scene.layout_type or "text_only",
            slide_content=content,
            image_description=content.get("image_description", ""),
        )
    except (ValueError, RuntimeError) as e:
        raise llm_error(e, "画像プロンプトの生成") from e
    if not result["image_prompt"]:
        raise HTTPException(status_code=502, detail="画像プロンプトの生成に失敗しました")

    scene.image_prompt = result["image_prompt"]
    if result.get("note"):
        content["image_prompt_note"] = result["note"]
        scene.slide_content_json = json.dumps(content, ensure_ascii=False)
    await db.flush()
    return scene


@router.post("/scenes/{scene_id}/generate-narration", response_model=SceneRead)
async def generate_narration(
    scene_id: str,
    payload: NarrationGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    # シーンの存在確認
    stmt = select(Scene).where(Scene.id == scene_id)
    scene = (await db.execute(stmt)).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")

    # 長さはシーン個別 → 動画の既定の順に効かせる（内容生成と同じ決め方）。
    _, _, video_length = await _video_context(scene, db)
    try:
        reply = await generate_narration_llm(
            title=scene.title,
            slide_content=scene.slide_content_json,
            summary=scene.outline_summary or "",
            target_chars=narration_target_chars(_effective_narration_length(scene, video_length)),
            # 直前のシーンのナレーションも文脈に含まれる
            context=(await load_scene_context(scene, db)).to_prompt(),
        )
    except RuntimeError as e:
        raise llm_error(e, "ナレーションの生成") from e

    scene.narration_text = reply.strip()
    # この生成は区切りを作らない。前回の内容生成で付いた区切りが残ると、
    # 音声は新しいナレーションではなく古い区切りの文字列を読んでしまう。
    scene.narration_segments_json = None
    await db.flush()

    return scene


# 一括生成のジョブの進捗（プロセス内メモリ、期限付き）
bulk_content_job_store = JobStore()

def _needs_generation(scene: Scene) -> bool:
    """一括生成の「未生成（内容が空）のシーンのみ」の対象か（#81）。

    以前は、スライドの中身に決め打ちの 8 つの項目名（bullet_points など）が
    あるかで判定していた。見せ方の型が増えて body などが一覧に無く、
    本文を持つシーンが「生成済み」と誤判定されて、ナレーションが空のまま残った。

    型の定義で「中身が空か」を見るだけでも足りない。シナリオ作成時に、
    あらすじを型に合わせて流し込む（_types.fill_from_summary）ので、
    未生成のシーンにも中身が入っている。

    そこで、判定の軸はナレーションにする。AI の内容生成は必ずナレーションも
    作るので、ナレーションが空なら未生成。ナレーションがあっても、
    スライドの中身が型として空なら未生成とする。
    """
    if not strip_markup(scene.narration_text).strip():
        return True
    try:
        content = json.loads(scene.slide_content_json) if scene.slide_content_json else {}
    except ValueError:
        return True
    if not isinstance(content, dict):
        return True
    return _types.is_blank(layouts.type_of(scene.layout_type), content)


async def _run_bulk_generate_content(job_id: str, video_id: str, only_empty: bool):
    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            stmt_sc = select(Scenario).where(Scenario.video_id == video_id)
            scenario = (await db.execute(stmt_sc)).scalars().first()
            if not scenario:
                bulk_content_job_store[job_id] = {"status": "error", "error": "シナリオが見つかりません"}
                return

            # 文脈の材料は 1 回だけ読む。シーンのオブジェクトは生成のたびに
            # 書き換わるので、後のシーンは今回作った直前のナレーションを参照できる。
            all_scenes, _, video_name = await load_context_sources(scenario.id, db)

            target_scenes = [s for s in all_scenes if (not only_empty or _needs_generation(s))]
            total = len(target_scenes)

            bulk_content_job_store[job_id] = {
                "status": "processing",
                "done": 0,
                "total": total,
                "current_title": "",
                "error": None,
                # 生成が終わったシーンの ID。画面はこれを見て、終わったシーンから
                # 順に表示を最新にする（#81）。失敗したシーンは入れない
                "completed_scene_ids": [],
            }

            if total == 0:
                bulk_content_job_store[job_id]["status"] = "completed"
                return

            aspect, _, video_length = (
                await _video_context(target_scenes[0], db) if target_scenes
                else ("16:9", None, None)
            )
            # 直近に使った見せ方を持ち回して、同じ絵が続かないようにする。
            # 1 つ前だけでは A→B→A→B の交互を防げないため 2 件見る。
            # resolve() の avoid は禁止ではなく減点なので、候補が尽きることはない。
            RECENT = 2
            recent: list[str] = []
            failed: list[str] = []
            # どのシーンがどの見せ方になったかを最後にまとめて出す。
            # 選択が偏っていないかを、動画を作らずに確認できるようにする。
            chosen: list[str] = []
            for idx, scene in enumerate(target_scenes):
                bulk_content_job_store[job_id]["current_title"] = scene.title or f"Scene {scene.index}"
                pinned = bool(getattr(scene, "layout_pinned", False))
                try:
                    result = await generate_scene_content_llm(
                        title=scene.title or "",
                        summary=scene.outline_summary or "",
                        layout_type=scene.layout_type or "text_only",
                        aspect=aspect,
                        # 固定したシーンは連続回避の対象外（選択を覆さない）
                        avoid=() if pinned else tuple(recent),
                        narration_length=_effective_narration_length(scene, video_length),
                        layout_pinned=pinned,
                        context=build_scene_context(
                            scene, all_scenes, scenario, video_name).to_prompt(),
                    )
                except Exception as e:  # noqa: BLE001
                    # 1 シーンの失敗で 20 シーン分の生成を捨てない。
                    # 失敗したシーンは元の内容のまま残し、最後にまとめて知らせる。
                    print(f"[bulk] シーン {scene.index} の生成に失敗: {e}")
                    failed.append(f"{scene.index}. {scene.title or '無題'}")
                    bulk_content_job_store[job_id]["done"] = idx + 1
                    continue

                await apply_generated_content(scene, result)
                recent.append(result["layout"])
                del recent[:-RECENT]
                chosen.append(f"{scene.index}. {result['layout']}")
                await db.commit()
                bulk_content_job_store[job_id]["completed_scene_ids"].append(scene.id)
                bulk_content_job_store[job_id]["done"] = idx + 1

            if chosen:
                kinds = len({c.split(". ", 1)[1] for c in chosen})
                print(f"[bulk] 見せ方の選択結果（{len(chosen)} シーン / {kinds} 種）: "
                      + " / ".join(chosen))

            bulk_content_job_store[job_id]["status"] = "completed"
            bulk_content_job_store[job_id]["failed"] = failed
            if failed:
                bulk_content_job_store[job_id]["error"] = (
                    f"{len(failed)} 件のシーンで生成に失敗しました（他は完了しています）: "
                    + " / ".join(failed[:5]) + (" ほか" if len(failed) > 5 else "")
                )
        except Exception as e:
            bulk_content_job_store[job_id] = {"status": "error", "error": str(e)}


@router.post("/videos/{video_id}/scenes/generate-content-all/start")
async def start_generate_content_all(
    video_id: str,
    background_tasks: BackgroundTasks,
    only_empty: bool = True,
    db: AsyncSession = Depends(get_db)
):
    job_id = str(uuid.uuid4())
    bulk_content_job_store[job_id] = {
        "status": "processing",
        "done": 0,
        "total": 0,
        "current_title": "準備中...",
        "error": None,
        "completed_scene_ids": [],
    }
    background_tasks.add_task(_run_bulk_generate_content, job_id, video_id, only_empty)
    return {"job_id": job_id}


@router.get("/scenes/generate-content-all/status/{job_id}")
async def get_generate_content_all_status(job_id: str):
    job = bulk_content_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return job


