"""読みの制御（#60）の API。

  読み辞書      全体: /reading-dictionary、プロジェクト: /projects/{id}/reading-dictionary、
                シーン: /scenes/{id}/reading-dictionary（#73）
  読みの確認    /scenes/{id}/reading（見るだけ）、/scenes/{id}/reading-check（AI を動かす）
  入力の補助    /scenes/{id}/reading-guess（選んだ語の読みの初期値）、
                /reading/inspect（書式の点検、#73）
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.database import get_db
from models.project import Project
from models.reading_dictionary import ReadingDictionaryEntry
from models.scene import Scene
from schemas.reading import (
    DictionaryEntryCreate,
    DictionaryEntryRead,
    DictionaryEntryUpdate,
    MarkupInspectRead,
    MarkupInspectRequest,
    ReadingGuessRead,
    ReadingGuessRequest,
    SceneReadingRead,
)
from services.reading import build_reading, guess_reading, inspect_markup, normalize_markup, strip_markup
from services.reading_db import scene_lexicon, scope_condition

router = APIRouter(tags=["reading"])


# ==========================================================================
# 読み辞書
# ==========================================================================

async def _list_entries(db: AsyncSession, *, project_id: str | None = None,
                        scene_id: str | None = None) -> list[ReadingDictionaryEntry]:
    return list((await db.execute(
        select(ReadingDictionaryEntry)
        .where(scope_condition(project_id=project_id, scene_id=scene_id))
        .order_by(ReadingDictionaryEntry.surface)
    )).scalars().all())


async def _ensure_unique(db: AsyncSession, surface: str, *, project_id: str | None = None,
                         scene_id: str | None = None, exclude_id: str | None = None) -> None:
    """同じ辞書（範囲）に同じ表記が無いことを確かめる。

    DB の UNIQUE に任せられないのは、全体辞書（project_id が NULL）では
    SQLite が NULL 同士を別物とみなして重複を通すため。
    """
    for entry in await _list_entries(db, project_id=project_id, scene_id=scene_id):
        if entry.surface == surface and entry.id != exclude_id:
            raise HTTPException(status_code=409, detail=f"「{surface}」はすでにこの辞書にあります")


async def _create(db: AsyncSession, payload: DictionaryEntryCreate, *,
                  project_id: str | None = None, scene_id: str | None = None) -> ReadingDictionaryEntry:
    await _ensure_unique(db, payload.surface, project_id=project_id, scene_id=scene_id)
    entry = ReadingDictionaryEntry(project_id=project_id, scene_id=scene_id,
                                   surface=payload.surface, reading=payload.reading)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def _require_project(db: AsyncSession, project_id: str) -> None:
    if not (await db.execute(select(Project.id).where(Project.id == project_id))).first():
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")


@router.get("/reading-dictionary", response_model=list[DictionaryEntryRead])
async def list_global_entries(db: AsyncSession = Depends(get_db)):
    return await _list_entries(db)


@router.post("/reading-dictionary", response_model=DictionaryEntryRead, status_code=status.HTTP_201_CREATED)
async def create_global_entry(payload: DictionaryEntryCreate, db: AsyncSession = Depends(get_db)):
    return await _create(db, payload)


@router.get("/projects/{project_id}/reading-dictionary", response_model=list[DictionaryEntryRead])
async def list_project_entries(project_id: str, db: AsyncSession = Depends(get_db)):
    await _require_project(db, project_id)
    return await _list_entries(db, project_id=project_id)


@router.post("/projects/{project_id}/reading-dictionary", response_model=DictionaryEntryRead,
             status_code=status.HTTP_201_CREATED)
async def create_project_entry(project_id: str, payload: DictionaryEntryCreate,
                               db: AsyncSession = Depends(get_db)):
    await _require_project(db, project_id)
    return await _create(db, payload, project_id=project_id)




async def _get_entry(db: AsyncSession, entry_id: str) -> ReadingDictionaryEntry:
    entry = (await db.execute(
        select(ReadingDictionaryEntry).where(ReadingDictionaryEntry.id == entry_id)
    )).scalars().first()
    if not entry:
        raise HTTPException(status_code=404, detail="辞書の項目が見つかりません")
    return entry


@router.put("/reading-dictionary/{entry_id}", response_model=DictionaryEntryRead)
async def update_entry(entry_id: str, payload: DictionaryEntryUpdate, db: AsyncSession = Depends(get_db)):
    """全体・プロジェクト・シーンのどの項目も、ID だけで更新できる。"""
    entry = await _get_entry(db, entry_id)
    if payload.surface is not None and payload.surface != entry.surface:
        await _ensure_unique(db, payload.surface, project_id=entry.project_id,
                             scene_id=entry.scene_id, exclude_id=entry.id)
        entry.surface = payload.surface
    if payload.reading is not None:
        entry.reading = payload.reading
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/reading-dictionary/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: str, db: AsyncSession = Depends(get_db)):
    await db.delete(await _get_entry(db, entry_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==========================================================================
# 読みの確認
# ==========================================================================

async def _get_scene(db: AsyncSession, scene_id: str) -> Scene:
    scene = (await db.execute(select(Scene).where(Scene.id == scene_id))).scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="シーンが見つかりません")
    return scene


@router.get("/scenes/{scene_id}/reading", response_model=SceneReadingRead)
async def get_scene_reading(scene_id: str, db: AsyncSession = Depends(get_db)):
    """読み上げ用テキストを返す。AI は動かさない（保存済みで最新の AI の読みだけ使う）。"""
    scene = await _get_scene(db, scene_id)
    lexicon, ai_checked = await scene_lexicon(scene, db, run_ai=False)
    return build_reading(scene.narration_text, lexicon).to_dict(ai_checked)


@router.post("/scenes/{scene_id}/reading-check", response_model=SceneReadingRead)
async def check_scene_reading(scene_id: str, force: bool = False, db: AsyncSession = Depends(get_db)):
    """AI に読み間違えやすい語を確認させてから、読み上げ用テキストを返す。

    今のナレーションに対する結果が保存済みなら、AI は動かさずに使い回す。
    force=true で作り直す。
    """
    scene = await _get_scene(db, scene_id)
    lexicon, ai_checked = await scene_lexicon(scene, db, run_ai=True, force_ai=force)
    if not ai_checked:
        raise HTTPException(
            status_code=503,
            detail="ローカル LLM に接続できないため、読みを確認できませんでした。LM Studio の起動を確認してください。",
        )
    return build_reading(scene.narration_text, lexicon).to_dict(True)


@router.get("/scenes/{scene_id}/reading-dictionary", response_model=list[DictionaryEntryRead])
async def list_scene_entries(scene_id: str, db: AsyncSession = Depends(get_db)):
    """このシーンだけの読み（#73）。本文に記号を入れずに読みを変える。"""
    await _get_scene(db, scene_id)
    return await _list_entries(db, scene_id=scene_id)


@router.post("/scenes/{scene_id}/reading-dictionary", response_model=DictionaryEntryRead,
             status_code=status.HTTP_201_CREATED)
async def create_scene_entry(scene_id: str, payload: DictionaryEntryCreate,
                             db: AsyncSession = Depends(get_db)):
    await _get_scene(db, scene_id)
    return await _create(db, payload, scene_id=scene_id)


# ==========================================================================
# 入力の補助（#73）
# ==========================================================================

@router.post("/scenes/{scene_id}/reading-guess", response_model=ReadingGuessRead)
async def guess_scene_reading(scene_id: str, payload: ReadingGuessRequest,
                              db: AsyncSession = Depends(get_db)):
    """ナレーション欄で選んだ語の、今の読み（推定）を返す。読みの指定画面の初期値に使う。

    AI は動かさない（押すたびに待たせないため）。保存済みの AI の読みは使う。
    """
    scene = await _get_scene(db, scene_id)
    lexicon, _ = await scene_lexicon(scene, db, run_ai=False)
    # 選択範囲に書式が混ざっていても、表記として扱う
    surface = strip_markup(payload.surface).strip()
    if not surface:
        raise HTTPException(status_code=422, detail="読みを調べる語を選んでください")
    reading, source = guess_reading(surface, lexicon)
    return {"surface": surface, "reading": reading, "source": source}


@router.post("/reading/inspect", response_model=MarkupInspectRead)
async def inspect_narration(payload: MarkupInspectRequest):
    """ナレーションの書式を点検する。入力のたびに呼ばれるので DB には触れない。"""
    normalized = normalize_markup(payload.text)
    return {
        "normalized": normalized,
        "plain_length": len(strip_markup(normalized)),
        # 点検は送られてきた本文そのものに対して行う。そろえた後の本文で行うと、
        # 文字数が変わったぶん（［間：1.50］→［間:1.5］など）画面の欄の位置とずれる
        "problems": [vars(p) for p in inspect_markup(payload.text)],
    }
