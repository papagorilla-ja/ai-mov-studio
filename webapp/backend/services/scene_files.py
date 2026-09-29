"""シーンに属するファイル（ナレーション音声・画像素材）の置き場所（#92）。

ファイル名は必ずシーンの **ID** で決める。

以前はシーンの **番号**（index）で決めていた（scene3.raw.wav / scene_3/slot1.png）。
番号は並べ替え・追加・削除で変わるが、音声のキャッシュ（SceneTtsCache）は
シーンの ID で引く。そのため並べ替えた後の生成で、あるシーンが
「前回その番号だった別のシーンの音声」を自分のキャッシュとして読んでいた。
画像素材も、並べ替えた後のアップロードが別のシーンの画像を上書きしていた。

ID は変わらないので、置き場所がシーン同士でぶつかることは無い。
"""
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.project_path import get_project_dir
from models.project import Project
from models.scenario import Scenario
from models.scene import Scene
from models.scene_asset import SceneAsset
from models.scene_tts_cache import SceneTtsCache
from models.video import Video

# 動画のフォルダの中での置き場所（index.html からの相対パスにもなる）
AUDIO_DIR = "assets/audio"
IMAGES_DIR = "assets/images"


def raw_audio_path(video_dir: Path, scene_id: str) -> Path:
    """生の音声（等倍）。キャッシュが指すのはこちら。"""
    return video_dir / AUDIO_DIR / f"{scene_id}.raw.wav"


def audio_path(video_dir: Path, scene_id: str) -> Path:
    """動画が使う音声（読み上げ速度を掛けたもの）。"""
    return video_dir / AUDIO_DIR / f"{scene_id}.wav"


def audio_src(scene_id: str) -> str:
    """index.html から動画の音声を指す相対パス。"""
    return f"{AUDIO_DIR}/{scene_id}.wav"


def image_rel_path(scene_id: str, slot: int, ext: str) -> str:
    """画像素材の、動画のフォルダからの相対パス（SceneAsset.file_path に入れる値）。"""
    return f"{IMAGES_DIR}/{scene_id}/slot{slot}{ext}"


def shared_cache_paths(cache_rows) -> set[str]:
    """2 つ以上のシーンのキャッシュが指している音声ファイル。

    番号で名付けていた頃は、並べ替えた後に生成し直していないシーンの
    キャッシュが、別のシーンが上書きしたファイルを指したままになりうる。
    どちらの音声なのか区別できないので、共有されているファイルは信用しない
    （そのシーンは合成し直す）。ID で名付けてからは共有は起きない。
    """
    counts = Counter(row.audio_path for row in cache_rows)
    return {path for path, n in counts.items() if n > 1}


def remove_unused_audio(video_dir: Path, scene_ids) -> int:
    """どのシーンの音声でもないファイルを消す。消した数を返す。

    番号で名付けていた頃のファイルや、削除したシーンの音声が残り続けないよう、
    生成で全シーンの音声が揃ったところで呼ぶ。
    """
    keep = set()
    for sid in scene_ids:
        keep.add(raw_audio_path(video_dir, sid).name)
        keep.add(audio_path(video_dir, sid).name)
    removed = 0
    for p in (video_dir / AUDIO_DIR).glob("*.wav"):
        if p.name not in keep:
            p.unlink(missing_ok=True)
            removed += 1
    return removed


async def scene_video_dir(db: AsyncSession, scene: Scene) -> Path | None:
    """シーンが属する動画のフォルダ。見つからなければ None。"""
    row = (await db.execute(
        select(Video, Project)
        .join(Scenario, Scenario.video_id == Video.id)
        .join(Project, Project.id == Video.project_id)
        .where(Scenario.id == scene.scenario_id)
    )).first()
    if not row:
        return None
    video, project = row
    return get_project_dir(project) / "videos" / video.id


async def delete_scene_files(db: AsyncSession, scene: Scene) -> None:
    """シーンを消す前に、そのシーンの音声・キャッシュ・画像素材のファイルを消す。

    DB は外部キーを強制していない（SQLite の foreign_keys が無効）ため、
    キャッシュ行の ondelete="CASCADE" は効かない。ここで明示的に消す。
    素材の行は Scene.assets の cascade で消えるが、ファイルは残るので消す。
    """
    video_dir = await scene_video_dir(db, scene)

    cache = await db.get(SceneTtsCache, scene.id)
    if cache is not None:
        # 番号で名付けていた頃のファイルは、他のシーンのキャッシュも
        # 指していることがある（shared_cache_paths 参照）。そのときは残す。
        others = (await db.execute(
            select(func.count()).select_from(SceneTtsCache).where(
                SceneTtsCache.audio_path == cache.audio_path,
                SceneTtsCache.scene_id != scene.id,
            )
        )).scalar() or 0
        if not others:
            Path(cache.audio_path).unlink(missing_ok=True)
        await db.delete(cache)

    if video_dir is None:
        return
    raw_audio_path(video_dir, scene.id).unlink(missing_ok=True)
    audio_path(video_dir, scene.id).unlink(missing_ok=True)

    assets = (await db.execute(
        select(SceneAsset).where(SceneAsset.scene_id == scene.id)
    )).scalars().all()
    for asset in assets:
        if asset.file_path:
            (video_dir / asset.file_path).unlink(missing_ok=True)
    # 空になったシーンの画像フォルダも片付ける（中身が残っていれば消さない）
    image_dir = video_dir / IMAGES_DIR / scene.id
    if image_dir.is_dir() and not any(image_dir.iterdir()):
        image_dir.rmdir()


async def delete_orphan_tts_cache(db: AsyncSession) -> int:
    """消えたシーンを指すキャッシュ行を消す。消した数を返す。

    シーンの削除やシナリオの取り込み直しで、キャッシュ行だけが残っていた
    （外部キーが強制されないため）。起動時に 1 回呼んで片付ける。
    """
    result = await db.execute(
        delete(SceneTtsCache).where(SceneTtsCache.scene_id.not_in(select(Scene.id)))
    )
    return result.rowcount or 0
