"""読みの制御（#60）のうち、DB と LLM に触れる部分。

純粋な書き換えは services.reading にあり、ここはその材料を集める。
  - 辞書（全体・プロジェクト）を読む
  - AI の読みを、保存済みなら使い回し、古ければ作り直す
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.reading_dictionary import ReadingDictionaryEntry
from models.scenario import Scenario
from models.scene import Scene
from models.video import Video
from services.llm_service import suggest_readings
from services.reading import (
    Lexicon,
    clean_ai_readings,
    dump_ai_readings,
    load_ai_readings,
    strip_markup,
)


async def project_id_of_scene(scene: Scene, db: AsyncSession) -> str | None:
    return (await db.execute(
        select(Video.project_id)
        .join(Scenario, Scenario.video_id == Video.id)
        .where(Scenario.id == scene.scenario_id)
    )).scalars().first()


def scope_condition(*, project_id: str | None = None, scene_id: str | None = None):
    """辞書の範囲を絞る条件。どちらも None なら全体辞書。

    シーンの読みは project_id が NULL なので、全体辞書の条件に
    「scene_id も NULL」を入れないと、シーンの読みまで全体辞書に混ざる。
    """
    E = ReadingDictionaryEntry
    if scene_id is not None:
        return E.scene_id == scene_id
    if project_id is not None:
        return (E.project_id == project_id) & E.scene_id.is_(None)
    return E.project_id.is_(None) & E.scene_id.is_(None)


async def load_dictionaries(db: AsyncSession, project_id: str | None) -> tuple[dict, dict]:
    """(プロジェクト辞書, 全体辞書) を「表記 → 読み」で返す。シーンの読みは含まない。"""
    cond = scope_condition()
    if project_id:
        cond = cond | scope_condition(project_id=project_id)
    rows = (await db.execute(select(ReadingDictionaryEntry).where(cond))).scalars().all()
    project = {r.surface: r.reading for r in rows if r.project_id is not None}
    global_ = {r.surface: r.reading for r in rows if r.project_id is None}
    return project, global_


async def export_readings(db: AsyncSession, *, project_id: str | None = None,
                          scene_id: str | None = None) -> list[dict]:
    """辞書の範囲を [{surface, reading}] で取り出す（動画の複製、プロジェクトの書き出し用）。"""
    rows = (await db.execute(
        select(ReadingDictionaryEntry)
        .where(scope_condition(project_id=project_id, scene_id=scene_id))
        .order_by(ReadingDictionaryEntry.surface)
    )).scalars().all()
    return [{"surface": r.surface, "reading": r.reading} for r in rows]


def import_readings(db: AsyncSession, readings: list | None, *, project_id: str | None = None,
                    scene_id: str | None = None) -> None:
    """export_readings の結果を、別のプロジェクト・シーンに書き戻す。

    読み込むファイルは手で編集されうるので、壊れた要素と重複は黙って捨てる。
    """
    seen: set[str] = set()
    for r in readings or []:
        if not isinstance(r, dict):
            continue
        surface, reading = str(r.get("surface") or "").strip(), str(r.get("reading") or "").strip()
        if surface and reading and surface not in seen:
            seen.add(surface)
            db.add(ReadingDictionaryEntry(project_id=project_id, scene_id=scene_id,
                                          surface=surface, reading=reading))


async def load_scene_readings(db: AsyncSession, scene_id: str) -> dict[str, str]:
    """このシーンだけの読みを「表記 → 読み」で返す。"""
    rows = (await db.execute(
        select(ReadingDictionaryEntry).where(scope_condition(scene_id=scene_id))
    )).scalars().all()
    return {r.surface: r.reading for r in rows}


async def ensure_ai_readings(scene: Scene, *, force: bool = False,
                             log=print) -> dict[str, str] | None:
    """シーンの AI の読みを返す。保存済みで最新なら使い回し、古ければ LLM で作る。

    ナレーションを書き換えるまでは作り直さない（force のときだけ作り直す）。
    LLM に届かないときは None を返す。読みの制御は品質の上乗せなので、
    ここで失敗しても音声の合成は止めない（辞書とルビだけで読む）。
    結果はシーンの列に書くだけで、コミットは呼び出し側に任せる。
    """
    narration = scene.narration_text or ""
    if not narration.strip():
        return {}
    if not force:
        saved = load_ai_readings(scene.narration_ai_readings_json, narration)
        if saved is not None:
            return saved
    try:
        raw = await suggest_readings(strip_markup(narration))
    except Exception as e:  # noqa: BLE001
        log(f"  読みの自動確認に失敗しました（辞書とルビだけで読みます）: {e}")
        return None
    readings = clean_ai_readings(raw, narration)
    scene.narration_ai_readings_json = dump_ai_readings(readings, narration)
    return readings


async def scene_lexicon(scene: Scene, db: AsyncSession, *, run_ai: bool,
                        force_ai: bool = False, dictionaries: tuple[dict, dict] | None = None,
                        log=print) -> tuple[Lexicon, bool]:
    """シーンの読み上げ用テキストを作るための辞書一式と、AI の確認が済んでいるかを返す。

    run_ai=False なら LLM は動かさず、保存済みで最新の AI の読みだけを使う
    （GET /reading のように、見るだけの経路のため）。
    dictionaries を渡すと DB を読まない（一括生成で全シーンぶん使い回す）。
    """
    if dictionaries is None:
        dictionaries = await load_dictionaries(db, await project_id_of_scene(scene, db))
    project, global_ = dictionaries
    # シーンの読みはシーンごとに違うので、一括生成でも毎回読む（1 シーン 1 回の軽い問い合わせ）
    scene_readings = await load_scene_readings(db, scene.id)
    if run_ai:
        ai = await ensure_ai_readings(scene, force=force_ai, log=log)
    else:
        ai = load_ai_readings(scene.narration_ai_readings_json, scene.narration_text)
    lexicon = Lexicon.build(scene=scene_readings, project=project, global_=global_, ai=ai)
    return lexicon, ai is not None
