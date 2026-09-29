import asyncio
import json
import shutil
import time
import traceback
import wave
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.future import select

from core.config import settings
from core.clock import utcnow
from core.database import AsyncSessionLocal
from core.project_path import get_project_dir
from services.design_tokens import normalize_narration_speed
from models.generation_history import GenerationHistory
from models.project import Project
from models.scenario import Scenario
from models.scene import Scene
from models.scene_asset import SceneAsset
from models.scene_tts_cache import SceneTtsCache
from models.video import Video
from models.video_style import VideoStyle
from services.audio_utils import apply_speed
from services.composition import (
    PREVIEW_DIR_NAME,
    TRANSITION_BUFFER,
    find_missing_css_refs,
    find_missing_local_refs,
    generate_composition,
    write_preview_snapshot,
)
from services import scene_files, scene_tts
from services.reading_db import load_dictionaries, scene_lexicon
from services.subtitles import build_srt
from services.tts_service import (
    TTS_PEAK_WARN_MB,
    audio_warning_message,
    derive_seed,
    ensure_tts_ready,
)
from workers.progress import (
    COMPOSITION_AT,
    FINISHING_AT,
    RENDER_RANGE,
    TTS_RANGE,
    GenerationProgress,
    remaining_seconds,
    render_stage_label,
    span,
)

TEMPLATES_BLANK_DIR = Path("/app/templates/blank")

def get_wav_duration(file_path: Path) -> float:
    with wave.open(str(file_path), "rb") as f:
        frames = f.getnframes()
        rate = f.getframerate()
        return frames / float(rate)

# レンダリングの進捗を受け取る関数。(進み具合 0〜1, hyperframes の段階) を受け取る
RenderProgressFn = Callable[[float, str], Awaitable[None]]


async def request_render(
    video_dir: str,
    output_rel: str,
    fps: int,
    workers: int,
    renderer_timeout: float,
    log,
    on_progress: RenderProgressFn | None = None,
) -> None:
    """ホストのレンダラーサーバーに 1 本分のレンダリングを依頼する。

    レンダラーは進捗を 1 行ずつ返す（#96）。受け取るたびに on_progress を呼ぶ。
    生成を中止すると、このリクエストごと取り消され、接続が切れたのを見て
    レンダラーが hyperframes を止める。
    """
    # ─── 参照ファイルの実在確認 ───────────────────────────────
    # hyperframes は JS/CSS が 404 でもエラーを返さず完走し、
    # 「アニメーションが一切効いていない静止画の動画」を出力してしまう。
    # 無言で壊れた動画を作らないよう、依頼前にここで止める。
    missing = find_missing_local_refs(Path(video_dir) / "index.html")
    critical = [m for m in missing if m.endswith((".js", ".css")) or m == "index.html"]
    if critical:
        raise RuntimeError(
            "レンダリングに必要なファイルが見つかりません: "
            f"{', '.join(critical)}（対象ディレクトリ: {video_dir}）"
        )
    if missing:
        log(f"警告: 参照先が見つからないメディアがあります（そのまま続行します）: {', '.join(missing)}")

    # style.css が読む同梱フォントも 404 が無言で通る。
    # 欠けるとシステムフォントに差し替わり、指定した書体と違う動画が出来上がる。
    missing_css = find_missing_css_refs(Path(video_dir) / "style.css")
    if missing_css:
        log(f"警告: フォント等の参照先が見つかりません（既定の書体で続行します）: {', '.join(missing_css)}")

    payload = {
        "video_dir": video_dir,
        "output_path": output_rel,
        "timeout": int(renderer_timeout),
        "fps": fps,
    }
    if workers > 0:
        payload["workers"] = workers

    result: dict | None = None
    async with httpx.AsyncClient(timeout=renderer_timeout) as client:
        async with client.stream(
            "POST", f"{settings.renderer_base_url}/render/stream", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("type") == "progress":
                    if on_progress:
                        await on_progress(event["percent"] / 100, event.get("stage") or "")
                elif event.get("type") == "result":
                    result = event

    if result is None:
        raise RuntimeError("レンダラーの応答が途中で途切れました（レンダラーが停止した可能性があります）")
    if result.get("status") != "success":
        raise RuntimeError(
            f"HyperFrames rendering failed: {result.get('stderr') or result.get('message')}"
        )
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        log(f"HyperFrames stdout: {stdout[-500:]}")


def split_scenes_into_chunks(scenes: list[Scene], chunk_sec: int) -> list[list[Scene]]:
    """シーン境界で、1 チャンクの尺が chunk_sec を超えないように分割する。

    1 シーンだけで chunk_sec を超える場合はそのシーン単体で 1 チャンクにする
    （シーンの途中で切ると音声とアニメーションがずれるため分割しない）。
    chunk_sec <= 0 なら分割しない。
    """
    if chunk_sec <= 0 or not scenes:
        return [list(scenes)]

    chunks: list[list[Scene]] = []
    current: list[Scene] = []
    current_sec = 0.0
    for scene in scenes:
        dur = (scene.narration_audio_duration or 0.0) + TRANSITION_BUFFER
        if current and current_sec + dur > chunk_sec:
            chunks.append(current)
            current = []
            current_sec = 0.0
        current.append(scene)
        current_sec += dur
    if current:
        chunks.append(current)
    return chunks


async def render_in_chunks(
    video: Video,
    style: VideoStyle,
    chunks: list[list[Scene]],
    assets_map: dict,
    video_dir: Path,
    output_path: Path,
    fps: int,
    workers: int,
    renderer_timeout: float,
    log,
    on_progress: Callable[[float, str, tuple[int, int]], Awaitable[None]] | None = None,
) -> None:
    """チャンクごとにレンダリングし、ffmpeg で 1 本に連結する。

    on_progress には、レンダリング全体の進み具合（0〜1）と、何番目の区間か (i, n) を渡す。
    """
    chunk_root = video_dir / "_chunks"
    if chunk_root.exists():
        shutil.rmtree(chunk_root, ignore_errors=True)
    chunk_root.mkdir(parents=True, exist_ok=True)

    part_paths: list[Path] = []
    try:
        for i, chunk_scenes in enumerate(chunks, start=1):
            chunk_dir = chunk_root / f"chunk{i}"
            chunk_dir.mkdir(parents=True, exist_ok=True)

            # 音声などのアセットはシンボリックリンクで共有する（コピーしない）。
            # コンポジション内の参照は assets/audio/<シーンID>.wav の相対パスのままでよい。
            #
            # リンク先は必ず「相対パス」にすること。レンダリングはホスト側プロセスが行うため、
            # コンテナ内の絶対パス（/app/projects/...）で張るとホストから辿れなくなる。
            # chunk_dir は <video_dir>/_chunks/chunkN なので assets は 2 階層上にある。
            # 同梱フォント (1ファイル 2MB 超) も同じ理由でリンク共有する。
            # チャンクごとにコピーするとレンダリングのたびに数十MBの無駄が出る。
            for link_name in ("assets", "fonts"):
                link = chunk_dir / link_name
                if not link.is_symlink() and not link.exists():
                    link.symlink_to(Path(f"../../{link_name}"), target_is_directory=True)

            # generate_composition は渡されたシーンだけで 0 秒からタイムラインを組み直すため、
            # チャンク単体で正しい尺の動画になる
            generate_composition(
                video, chunk_scenes, style, TEMPLATES_BLANK_DIR, chunk_dir, assets_map, fps=fps
            )

            log(f"チャンク {i}/{len(chunks)}: {len(chunk_scenes)} シーンをレンダリング中...")

            # 区間の中の進み具合を、全体の進み具合に直して渡す
            async def chunk_progress(done: float, stage: str, i: int = i) -> None:
                if on_progress:
                    await on_progress((i - 1 + done) / len(chunks), stage, (i, len(chunks)))

            await request_render(
                video_dir=str(chunk_dir),
                output_rel="part.mp4",
                fps=fps,
                workers=workers,
                renderer_timeout=renderer_timeout,
                log=log,
                on_progress=chunk_progress,
            )
            part = chunk_dir / "part.mp4"
            if not part.exists():
                raise RuntimeError(f"チャンク {i} の出力が見つかりません: {part}")
            part_paths.append(part)

        # ─── ffmpeg concat で連結 ────────────────────────────────
        # 全チャンクは同じ設定でエンコードされているため再エンコード不要（-c copy）
        list_file = chunk_root / "parts.txt"
        list_file.write_text(
            "".join(f"file '{p}'\n" for p in part_paths), encoding="utf-8"
        )
        log(f"{len(part_paths)} 個のチャンクを連結しています...")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not output_path.exists():
            raise RuntimeError(
                f"チャンクの連結に失敗しました: {stderr.decode(errors='replace')[-500:]}"
            )
        log("チャンクの連結が完了しました。")
    finally:
        shutil.rmtree(chunk_root, ignore_errors=True)


async def purge_scene_audio(db, scenes: list[Scene], video_dir: Path, log) -> int:
    """既存のナレーション音声と TTS キャッシュを削除する（音声再作成オプション用）。

    内容・話者・参照音声（録り直し。#98）が変わったシーンは、この指定が無くても
    作り直される。これは、それ以外の理由（声の出来が気に入らない等）で
    確実に全シーンを合成し直したいときのためのもの。
    """
    scene_ids = [s.id for s in scenes]
    stmt_cache = select(SceneTtsCache).where(SceneTtsCache.scene_id.in_(scene_ids))
    cache_rows = (await db.execute(stmt_cache)).scalars().all()

    removed_files = 0
    # キャッシュが指す WAV を削除する
    for row in cache_rows:
        p = Path(row.audio_path)
        if p.exists():
            p.unlink()
            removed_files += 1
        await db.delete(row)

    # 動画の全シーンを作り直すので、音声のフォルダは丸ごと空にしてよい。
    # 生の音声（.raw.wav）を残すと「作り直した」のに前回の音声が使われ続ける。
    # 番号で名付けていた頃のファイル（#92）もここで一緒に消える。
    for wav_path in (video_dir / scene_files.AUDIO_DIR).glob("*.wav"):
        wav_path.unlink(missing_ok=True)
        removed_files += 1

    for scene in scenes:
        scene.narration_audio_path = None
        scene.narration_audio_duration = None
        scene.narration_audio_degraded = None
        scene.narration_audio_warning = None

    await db.flush()
    log(f"音声再作成: 既存のキャッシュ {len(cache_rows)} 件 / 音声ファイル {removed_files} 件を削除しました")
    return len(cache_rows)


# BGM の終わりをフェードアウトさせる秒数
BGM_FADE_SEC = 2.0


async def mix_bgm(output_path: Path, bgm_path: Path, volume: float, video_sec: float, log) -> str | None:
    """動画に BGM を混ぜて上書きする。失敗したら元の動画のまま、画面に出す文言を返す。

    amix は既定（normalize=1）で入力の数で割るため、2 本を混ぜると
    ナレーションまで半分（-6 dB）になっていた（#94）。normalize=0 で
    ナレーションは元の音量のまま、BGM の大きさは volume だけで決める。
    ナレーションのピークは実測 -8.8 dB で、BGM を 0.3 倍で足しても 0 dB を超えにくい。
    """
    mixed_path = output_path.with_name(output_path.stem + "_bgm_tmp.mp4")
    fade_start = max(0.0, video_sec - BGM_FADE_SEC)
    bgm_filter = (
        f"[1:a]volume={volume}[bgm_vol];"
        f"[bgm_vol]afade=t=out:st={fade_start:.2f}:d={BGM_FADE_SEC}[bgm_fade];"
        f"[0:a][bgm_fade]amix=inputs=2:duration=first:normalize=0[out]"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", str(output_path),
            "-stream_loop", "-1", "-i", str(bgm_path),
            "-filter_complex", bgm_filter,
            "-map", "0:v", "-map", "[out]",
            "-c:v", "copy",
            str(mixed_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
    except Exception as e:  # noqa: BLE001
        mixed_path.unlink(missing_ok=True)
        log(f"BGM ミックスエラー（BGM なしで続行）: {e}")
        return "BGM を入れられませんでした"

    # 終了コードを見る。見ていなかった頃は、途中で失敗して短くなった
    # ファイルでも元の動画を上書きしていた。
    if proc.returncode != 0 or not mixed_path.exists():
        mixed_path.unlink(missing_ok=True)
        log(f"BGM ミックス失敗（BGM なしで続行）: {stderr.decode(errors='replace')[-500:]}")
        return "BGM を入れられませんでした"

    shutil.move(str(mixed_path), str(output_path))
    log("BGM ミックス完了")
    return None


async def _status_after_cancel(db, video_id: str) -> str:
    """中止した後の動画の状態。前に完成した回があれば completed、無ければ draft。

    中止は失敗ではないので failed にはしない。
    """
    done = (await db.execute(
        select(GenerationHistory.id).where(
            GenerationHistory.video_id == video_id, GenerationHistory.status == "completed"
        ).limit(1)
    )).scalars().first()
    return "completed" if done else "draft"


async def run_generation(video_id: str, generation_id: str, progress: GenerationProgress,
                         regenerate_audio: bool = False):
    """動画を 1 本生成する（音声合成 → コンポジション → レンダリング → 仕上げ）。

    workers.jobs のタスクとして動く。中止されるとタスクが cancel され、
    途中の処理（音声合成・レンダリングの依頼）ごと取り消される（#96）。
    """
    async with AsyncSessionLocal() as db:
        stmt_v = select(Video).where(Video.id == video_id)
        video = (await db.execute(stmt_v)).scalars().first()
        if not video:
            print(f"Video {video_id} not found")
            await progress.failed("動画が見つかりません")
            return

        stmt_p = select(Project).where(Project.id == video.project_id)
        project = (await db.execute(stmt_p)).scalars().first()
        
        stmt_style = select(VideoStyle).where(VideoStyle.video_id == video_id)
        style = (await db.execute(stmt_style)).scalars().first()
        if not style:
            style = VideoStyle(video_id=video_id)
            db.add(style)
            await db.flush()

        stmt_scenario = select(Scenario).where(Scenario.video_id == video_id)
        scenario = (await db.execute(stmt_scenario)).scalars().first()
        if not scenario:
            scenario = Scenario(video_id=video_id, source_type="paste")
            db.add(scenario)
            await db.flush()

        stmt_scenes = select(Scene).where(Scene.scenario_id == scenario.id).order_by(Scene.index)
        scenes = list((await db.execute(stmt_scenes)).scalars().all())

        stmt_history = select(GenerationHistory).where(GenerationHistory.id == generation_id)
        history = (await db.execute(stmt_history)).scalars().first()
        if not history:
            print(f"GenerationHistory {generation_id} not found")
            await progress.failed("生成履歴が見つかりません")
            return

        video.status = "generating"
        history.status = "running"
        await db.commit()

        video_dir = get_project_dir(project) / "videos" / video.id
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / scene_files.AUDIO_DIR).mkdir(parents=True, exist_ok=True)

        # 前回の下見をここで必ず捨てる。残したまま始めると、音声合成の間に
        # 画面を開き直したときに「前回の動画」が今の下見として流れてしまう。
        # 今回ぶんはレンダリングの直前に作り直す。
        shutil.rmtree(video_dir / PREVIEW_DIR_NAME, ignore_errors=True)

        # 読み上げ速度は動画ごとの設定。DB の値をここで一度だけ丸めておく
        # （範囲外の値をそのまま ffmpeg に渡さないため）。
        narration_speed = normalize_narration_speed(getattr(style, "narration_speed", None))

        logs = []
        def log(msg):
            print(msg)
            logs.append(f"[{datetime.now().isoformat()}] {msg}")

        try:
            # ─── ステップ1: 音声合成 ──────────────────────────────────
            # コンポジションより先に音声を作り、実際の尺を確定させる。
            # （旧実装は仮の尺で HTML を組んでから build_timeline.py で計算し直しており、
            #   同じ計算が2箇所に存在し、初回と2回目でアニメーションの速さが変わっていた）
            log("ステップ1: 音声合成を開始...")
            await progress.report("tts", TTS_RANGE[0], "ナレーション音声を合成中...")

            total_scenes = len(scenes)

            if total_scenes == 0:
                raise ValueError("合成するシーンがありません。シーンを追加してください。")

            # 音声再作成オプション: 既存音声とキャッシュを破棄してから合成し直す
            if regenerate_audio:
                # 削除する前に必ず TTS が使えることを確認する。
                # 確認せずに削除すると、TTS が停止していた場合に既存の音声を失った
                # うえで合成にも失敗し、動画に使える音声が何も残らなくなる。
                await progress.report("tts", TTS_RANGE[0], "TTSサーバーを確認しています...")
                await ensure_tts_ready()
                log("TTSサーバーの稼働を確認しました。既存の音声を削除します。")

                await progress.report("tts", TTS_RANGE[0], "既存の音声を削除しています...")
                await purge_scene_audio(db, scenes, video_dir, log)

            # 動画 ID から決定的にシードを導出する。
            # 同じ原稿からは常に同じ音声が得られ、声質のブレも防げる。
            seed = derive_seed(video.id)
            empty_narration_count = 0

            # シーンごとのキャッシュエントリを一括取得
            scene_ids = [s.id for s in scenes]
            stmt_cache = select(SceneTtsCache).where(SceneTtsCache.scene_id.in_(scene_ids))
            cache_rows = (await db.execute(stmt_cache)).scalars().all()
            cache_map: dict[str, SceneTtsCache] = {c.scene_id: c for c in cache_rows}
            # 複数のシーンが同じファイルを指しているキャッシュは信用しない（#92）
            untrusted_paths = scene_files.shared_cache_paths(cache_rows)

            skipped_count = 0

            # 読み辞書は生成の開始時に 1 回だけ読む（#60）
            dictionaries = await load_dictionaries(db, project.id if project else None)
            # LLM に届かなかったら、残りのシーンでは AI の読みを呼ばない。
            # シーンの数だけ接続エラーを待つことになるため。
            ai_available = True
            speakers = scene_tts.SpeakerLookup(db)
            tts_started = time.monotonic()

            for idx, scene in enumerate(scenes, start=1):
                # 進捗は「終えたシーンの数」で出す。以前は合成を始める時点で
                # そのシーンを終えた扱いの値を送り、1 シーン先を示していた
                done = (idx - 1) / total_scenes
                tts_eta = remaining_seconds(time.monotonic() - tts_started, done)
                # ─── 読み上げ用テキスト（#60） ─────────────────────────
                # ルビ・辞書・AI の読みで書き換えた文字列を TTS に渡す。本文は変えない。
                # キャッシュの判定もこの文字列で行うので、辞書を直すとそのシーンだけ作り直される。
                lexicon, ai_checked = await scene_lexicon(
                    scene, db, run_ai=ai_available, dictionaries=dictionaries, log=log)
                if ai_available and not ai_checked and (scene.narration_text or "").strip():
                    ai_available = False
                    log("  以降のシーンは、読みの自動確認をせずに辞書とルビだけで読みます")
                # 何を・誰の声で・どう読むか。試聴と同じ関数で決める（#98）
                inp = await scene_tts.prepare(scene, style, lexicon, speakers)

                cached = cache_map.get(scene.id)
                # 生の音声（常に等倍）と、読み上げ速度を掛けた最終ファイルを分ける。
                # キャッシュ対象は raw の方。速度をハッシュに含めると、速度を
                # 1 段階変えるたびに全シーンを合成し直すことになるため。
                # ファイル名はシーンの ID で決める。番号だと並べ替えで
                # 別のシーンのファイルを上書き・再利用してしまう（#92）。
                raw_path = scene_files.raw_audio_path(video_dir, scene.id)
                wav_path = scene_files.audio_path(video_dir, scene.id)

                if scene_tts.cache_usable(cached, inp, scene, untrusted_paths):
                    # ─── キャッシュヒット: WAV を再利用 ──────────────────
                    log(f"シーン {idx}/{total_scenes}: キャッシュ利用（スキップ）")
                    await progress.report(
                        "tts", span(TTS_RANGE, done),
                        f"シーン {idx}/{total_scenes} はキャッシュを使用（スキップ）",
                        stage_eta_sec=tts_eta,
                    )
                    # 番号で名付けていた頃のキャッシュ（scene{N}.raw.wav、さらに前の
                    # 速度対応より前は scene{N}.wav）は、ID のファイル名へコピーして
                    # 引き継ぐ。中身は等倍なので再合成は要らない。旧ファイル名へは
                    # もう誰も書き込まないので、引き継ぎの途中で上書きされることは無い。
                    cached_wav = Path(cached.audio_path)
                    if cached_wav.resolve() != raw_path.resolve():
                        shutil.copy2(str(cached_wav), str(raw_path))
                    # ファイル名の引き継ぎと、参照音声の記録（無ければ付ける。#98）
                    scene_tts.remember(db, cached, scene.id, inp, raw_path)
                    skipped_count += 1
                else:
                    # ─── キャッシュミス: TTS で再合成 ────────────────────
                    if not (scene.narration_text or "").strip() and not inp.dialog_lines:
                        empty_narration_count += 1
                        log(
                            f"シーン {idx}/{total_scenes}: "
                            "ナレーションが未入力のため 2.0秒の無音を挿入します"
                        )

                    log(f"シーン {idx}/{total_scenes} の音声を合成中...")
                    await progress.report(
                        "tts", span(TTS_RANGE, done),
                        f"シーン {idx}/{total_scenes} の音声を合成中...",
                        stage_eta_sec=tts_eta,
                    )

                    tts_stats = await scene_tts.synthesize(inp, raw_path, seed)
                    # 区切りの秒数と、作り直しても直らなかった区間（#57）をシーンに残す
                    scene_tts.apply_stats(scene, tts_stats)
                    if tts_stats:
                        peak = tts_stats.get("peak_mb")
                        log(
                            f"  TTS: チャンク {tts_stats.get('chunks')} / "
                            f"リトライ {tts_stats.get('retries')} / "
                            f"品質低下 {tts_stats.get('degraded')} / "
                            f"所要 {tts_stats.get('generate_sec')}秒"
                            + (f" / メモリ最大 {int(peak):,}MB" if peak else "")
                        )
                        # ピークが物理メモリに迫ると macOS にプロセスを
                        # 強制終了される。合成が終わると値は戻ってしまうので、
                        # 山の高さはここで記録しておかないと後から追えない。
                        if peak and int(peak) > TTS_PEAK_WARN_MB:
                            log(
                                f"  警告: 音声合成中のメモリが {int(peak):,}MB に達しました。"
                                "設定の「TTS チャンク最大文字数」を下げると下がります。"
                            )

                    # キャッシュを更新（upsert）
                    scene_tts.remember(db, cached, scene.id, inp, raw_path)

                # 読み上げ速度を掛けて、動画が使う WAV を作る。
                # キャッシュを使ったシーンでもここは必ず通す（速度だけ変えた
                # ときに、前回の速度の音声が残らないようにするため）。
                if raw_path.exists():
                    # ffmpeg を待つ間も画面の操作が詰まらないよう、別スレッドで動かす（#99）
                    changed = await asyncio.to_thread(apply_speed, raw_path, wav_path, narration_speed)
                    if changed and idx == 1:
                        log(f"読み上げ速度 {narration_speed:g} 倍を適用しています")

                # WAV が確定したのでメタデータを更新
                if wav_path.exists():
                    duration = get_wav_duration(wav_path)
                else:
                    duration = 0.0

                scene.narration_audio_path = str(wav_path)
                scene.narration_audio_duration = duration
                log(f"シーン {idx} の音声長: {duration:.2f}秒")
                # 文言は話速で割った秒数で書くので、音声を確定させるたびに作り直す
                # （キャッシュを使った回や、話速だけ変えた回も含めて）。
                scene.narration_audio_warning = audio_warning_message(
                    scene.narration_audio_degraded, narration_speed
                )
                if scene.narration_audio_warning:
                    log(f"  警告: シーン {idx}: {scene.narration_audio_warning}")

            log(f"音声合成完了: {total_scenes - skipped_count} シーンを合成、{skipped_count} シーンをスキップ")
            # 全シーンの音声が揃ったので、どのシーンの音声でもないファイル
            # （番号で名付けていた頃のもの・削除したシーンのもの）を片付ける（#92）
            removed = scene_files.remove_unused_audio(video_dir, [s.id for s in scenes])
            if removed:
                log(f"使われなくなった音声ファイルを {removed} 件削除しました")
            # 崩れの残ったシーンを履歴に残す。生成は止めず、完了時に画面が知らせる（#57）。
            audio_warnings = [
                {"scene_id": s.id, "scene_index": s.index,
                 "title": s.title or f"シーン {s.index}", "message": s.narration_audio_warning}
                for s in scenes if s.narration_audio_warning
            ]
            history.audio_warnings_json = (
                json.dumps(audio_warnings, ensure_ascii=False) if audio_warnings else None
            )
            if audio_warnings:
                log(f"音声が崩れている可能性のあるシーン: {len(audio_warnings)} 件 "
                    f"（{', '.join(str(w['scene_index']) for w in audio_warnings)}）")
            if empty_narration_count:
                log(f"ナレーション未入力: {empty_narration_count} シーン（2.0秒の無音になっています）")

            # composition が確定した音声尺を読めるようにフラッシュする
            await db.flush()

            # ─── ステップ2: コンポジション ────────────────────────────
            # 実際の音声尺だけを使って index.html を 1 回で完成させる。
            # タイムラインの計算はここが唯一の場所。
            log("ステップ2: コンポジションの生成を開始...")
            await progress.report("composition", COMPOSITION_AT, "コンポジションを生成中...")

            stmt_assets = select(SceneAsset).where(
                SceneAsset.scene_id.in_([s.id for s in scenes])
            )
            all_assets = (await db.execute(stmt_assets)).scalars().all()
            assets_map = {}
            for a in all_assets:
                assets_map.setdefault(a.scene_id, []).append(a)

            # generate_composition が scene.data_start / scene.data_duration /
            # video.duration_sec を設定するため、HTML を読み直す必要はない
            render_fps = int(getattr(settings, "default_fps", 24) or 24)
            generate_composition(
                video, scenes, style, TEMPLATES_BLANK_DIR, video_dir, assets_map, fps=render_fps
            )
            await db.commit()
            log(f"コンポジションを書き出しました。合計尺: {video.duration_sec:.2f}秒 "
                f"({video.duration_sec / 60:.1f}分)")

            # レンダリングを始める前に「音声なしの下見」を固めておく。
            # 待っている間にブラウザで流すためのもので、成果物ではない。
            # 失敗しても動画生成は止めない（演出が出ないだけ）。
            try:
                if write_preview_snapshot(video_dir):
                    log("レンダリング中に見られる下見を用意しました。")
            except Exception as e:  # noqa: BLE001
                print(f"[preview] 下見の作成に失敗しました: {e}")

            log("ステップ3: HyperFrames レンダリングを開始...")
            await progress.report("rendering", RENDER_RANGE[0], "動画をレンダリング中...")
            render_started = time.monotonic()

            async def on_render_progress(done: float, stage: str,
                                         part: tuple[int, int] | None = None) -> None:
                """レンダラーの進捗（done はレンダリング全体の進み具合）を画面へ送る。"""
                where = f"・{part[0]}/{part[1]} 区間" if part else ""
                await progress.report(
                    "rendering", span(RENDER_RANGE, done),
                    f"動画をレンダリング中... {int(done * 100)}%（{render_stage_label(stage)}{where}）",
                    stage_eta_sec=remaining_seconds(time.monotonic() - render_started, done),
                )

            output_path = video_dir / f"output/{generation_id}.mp4"
            output_path.parent.mkdir(exist_ok=True)

            renderer_timeout = float(getattr(settings, "renderer_request_timeout", 3600))
            render_workers = int(getattr(settings, "render_workers", 0) or 0)
            chunk_sec = int(getattr(settings, "render_chunk_sec", 0) or 0)
            total_duration = video.duration_sec or 0.0

            chunks = split_scenes_into_chunks(scenes, chunk_sec)
            if len(chunks) > 1:
                # ─── 分割レンダリング ────────────────────────────────
                # 長尺動画を1回のブラウザセッションで処理するとフレーム数に比例して
                # メモリが増え続け、途中で停止する。シーン境界で分割して
                # 1回あたりのフレーム数を抑え、最後に ffmpeg で連結する。
                log(f"分割レンダリング: 合計 {total_duration:.0f}秒 を {len(chunks)} 個に分割します"
                    f"（閾値 {chunk_sec}秒）")
                await render_in_chunks(
                    video=video, style=style, chunks=chunks, assets_map=assets_map,
                    video_dir=video_dir, output_path=output_path,
                    fps=render_fps, workers=render_workers,
                    renderer_timeout=renderer_timeout,
                    log=log, on_progress=on_render_progress,
                )
                # 分割時はシーンの data_start がチャンク基準で上書きされているため、
                # 全体コンポジションを作り直して DB の値と index.html を元に戻す
                generate_composition(
                    video, scenes, style, TEMPLATES_BLANK_DIR, video_dir, assets_map, fps=render_fps
                )
                await db.commit()
            else:
                await request_render(
                    video_dir=str(video_dir),
                    output_rel=f"output/{generation_id}.mp4",
                    fps=render_fps,
                    workers=render_workers,
                    renderer_timeout=renderer_timeout,
                    log=log,
                    on_progress=on_render_progress,
                )
            log("HyperFrames レンダリングが完了しました。")
            await progress.report("finishing", FINISHING_AT, "仕上げ中（BGM・サムネイル）...")

            # ─── BGM ミックス（設定されている場合のみ） ──────────────
            bgm_note = None
            if style.bgm_path and Path(style.bgm_path).exists():
                bgm_volume = style.bgm_volume if style.bgm_volume is not None else 0.3
                log(f"BGM ミックスを開始... volume={bgm_volume}")
                bgm_note = await mix_bgm(
                    output_path, Path(style.bgm_path), bgm_volume, video.duration_sec or 0.0, log)

            # ─── サムネイル抽出 ────────────────────────────────────────
            thumb_path = output_path.parent / f"{generation_id}_thumb.jpg"
            try:
                thumb_proc = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-i", str(output_path),
                    "-ss", "0",          # 先頭フレーム
                    "-vframes", "1",
                    "-q:v", "3",         # JPEG 品質 (1=最高, 31=最低)
                    str(thumb_path),
                    "-y",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await thumb_proc.communicate()
                if thumb_path.exists():
                    # web アクセスパス: /projects/{...} にマップされるよう /app/ を除去
                    history.thumbnail_path = str(thumb_path).replace("/app/", "")
                    log(f"サムネイル生成完了: {thumb_path.name}")
                else:
                    log("サムネイル生成に失敗しました（ffmpeg 出力なし）")
            except Exception as e:
                log(f"サムネイル生成エラー（スキップ）: {e}")

            # 字幕を、この回の本文と時刻で書き出す（#97）。後で本文を直しても、
            # この回の動画と字幕は食い違わない。失敗しても動画はそのまま完成とする
            try:
                output_path.with_suffix(".srt").write_text(build_srt(scenes, style), encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                log(f"字幕の書き出しに失敗しました（動画はそのまま）: {e}")

            history.status = "completed"
            history.output_path = str(output_path)
            # BGM を入れた後に測る（入れる前の大きさを記録していた。#94）
            history.file_size_bytes = output_path.stat().st_size if output_path.exists() else 0
            history.duration_sec = video.duration_sec
            history.completed_at = utcnow()
            
            video.status = "completed"
            await db.commit()

            await progress.completed("レンダリング完了" + (f"（{bgm_note}）" if bgm_note else ""))

        except asyncio.CancelledError:
            # 中止（#96）。途中の DB 操作が取り消されている可能性があるので、
            # 巻き戻してから記録する。キャンセルはこの後もう一度送り出す。
            log("生成を中止しました")
            await db.rollback()
            history.status = "cancelled"
            history.error_message = "生成を中止しました"
            history.completed_at = utcnow()
            video.status = await _status_after_cancel(db, video_id)
            await db.commit()
            await progress.cancelled()
            raise

        except Exception as e:
            tb = traceback.format_exc()
            raw_err = str(e).strip()
            err_msg = raw_err if raw_err else f"{type(e).__name__}: レンダリング処理中にエラーが発生しました ({repr(e)})"
            log(f"エラーが発生しました: {err_msg}\n{tb}")
            
            history.status = "failed"
            history.error_message = err_msg
            history.completed_at = utcnow()
            
            video.status = "failed"
            await db.commit()

            await progress.failed(err_msg)
        
        finally:
            history.log_text = "\n".join(logs)
            await db.commit()
