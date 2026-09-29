import shutil
import io
import json
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from core.database import get_db
from models.project import Project
from models.video import Video
from models.video_style import VideoStyle
from models.scenario import Scenario
from models.scene import Scene
from models.scene_asset import SceneAsset
from models.speaker import Speaker
from core.project_path import get_project_dir
from services.reading_db import export_readings, import_readings
from services.video_copy import (
    SCENARIO_FIELDS, SCENE_FIELDS, SCENE_SPEAKER_FIELDS, STYLE_FIELDS, STYLE_SPEAKER_FIELDS,
    apply_row, export_row, remap_speakers,
)
from schemas.project import ProjectCreate, ProjectImportRead, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])

PROJECTS_DIR = Path("/app/projects")


def _bgm_zip_path(video_id: str, bgm_path: str | None) -> str | None:
    """BGM を ZIP のどこに入れるか。ファイルが無ければ None（manifest にも書かない）。"""
    if not bgm_path or not Path(bgm_path).exists():
        return None
    return f"files/{video_id}/bgm/{Path(bgm_path).name}"


def _inside(path: Path, root: Path) -> bool:
    """path が root の中にあるか。manifest を書き換えた ZIP で外のファイルを読まないため。"""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

@router.get("", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Project, func.count(Video.id).label("video_count"))
        .outerjoin(Project.videos)
        .group_by(Project.id)
    )
    result = await db.execute(stmt)
    projects_with_counts = []
    for row in result:
        proj, count = row
        read_obj = ProjectRead.model_validate(proj)
        read_obj.video_count = count
        projects_with_counts.append(read_obj)
    return projects_with_counts

@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(Project).where(Project.name == payload.name)
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="同名のプロジェクトが既に存在します")

    proj = Project(name=payload.name, description=payload.description)
    db.add(proj)
    await db.flush()

    # ディレクトリ作成
    proj_dir = PROJECTS_DIR / proj.name
    proj_dir.mkdir(parents=True, exist_ok=True)

    read_obj = ProjectRead.model_validate(proj)
    read_obj.video_count = 0
    return read_obj

@router.post("/import", response_model=ProjectImportRead, status_code=status.HTTP_201_CREATED)
async def import_project(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """ZIP ファイルからプロジェクトをインポートする。新しい ID でレコードを再作成する。"""
    content = await file.read()

    with tempfile.TemporaryDirectory() as tmp_dir:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(tmp_dir)

        manifest_path = Path(tmp_dir) / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=400, detail="無効な ZIP ファイルです (manifest.json が見つかりません)")

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        if manifest.get("app") not in ("AI-MovGen", "HyperFrames"):
            raise HTTPException(status_code=400, detail="AI-MovGen のエクスポートファイルではありません")
        # 1.0 は項目が少ないだけで形は同じ。無い項目は既定値のまま（video_copy.apply_row）

        old_project = manifest["project"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_project_name = f"{old_project['name']}_import_{timestamp}"

        # ID マッピング: {旧ID: 新ID}
        id_map: dict[str, str] = {}
        # 話者はアプリ全体の設定で、書き出しに含まれない。読み込み先に無い話者の
        # 指定は外して既定の話者に戻し、その数を知らせる（#76）
        speaker_ids = set((await db.execute(select(Speaker.id))).scalars().all())
        missing_speakers = 0

        # プロジェクト作成
        new_project_id = str(uuid.uuid4())
        id_map[old_project["id"]] = new_project_id
        new_project = Project(
            id=new_project_id,
            name=new_project_name,
            description=old_project.get("description"),
        )
        db.add(new_project)
        # プロジェクトの読み辞書（#73）。古いファイルには無い
        import_readings(db, manifest.get("reading_dictionary"), project_id=new_project_id)

        # 各動画を再作成
        for vid_export in manifest.get("videos", []):
            old_vid = vid_export["video"]
            new_vid_id = str(uuid.uuid4())
            id_map[old_vid["id"]] = new_vid_id

            new_video = Video(
                id=new_vid_id,
                project_id=new_project_id,
                name=old_vid["name"],
                status="draft",
            )
            db.add(new_video)

            # VideoStyle（引き継ぐ項目は services/video_copy.py の一覧で決める、#76）
            new_vid_dir = PROJECTS_DIR / new_project_name / "videos" / new_vid_id
            new_vid_dir.mkdir(parents=True, exist_ok=True)
            style_data = vid_export.get("style")
            if style_data:
                new_style = VideoStyle(video_id=new_vid_id)
                apply_row(new_style, style_data, STYLE_FIELDS)
                missing_speakers += remap_speakers(new_style, STYLE_SPEAKER_FIELDS, speaker_ids)
                # BGM のファイルが ZIP にあれば、新しい動画のフォルダに置いて指す
                bgm_rel = style_data.get("bgm_file")
                bgm_src = Path(tmp_dir) / bgm_rel if bgm_rel else None
                if bgm_src and bgm_src.is_file() and _inside(bgm_src, Path(tmp_dir)):
                    bgm_dst = new_vid_dir / "bgm" / bgm_src.name
                    bgm_dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bgm_src, bgm_dst)
                    new_style.bgm_path = str(bgm_dst)
                db.add(new_style)

            # Scenario（貼り付けた原稿・企画チャットも運ぶ。#53 の元資料になる）
            sc_data = vid_export.get("scenario")
            new_sc_id = str(uuid.uuid4())
            new_scenario = Scenario(id=new_sc_id, video_id=new_vid_id, source_type="paste")
            apply_row(new_scenario, sc_data or {}, SCENARIO_FIELDS)
            db.add(new_scenario)

            # Scenes + Assets

            for scene_export in vid_export.get("scenes", []):
                new_scene_id = str(uuid.uuid4())
                id_map[scene_export["id"]] = new_scene_id

                # 音声は書き出しに含まれない（次回の生成で合成し直す）
                new_scene = Scene(id=new_scene_id, scenario_id=new_sc_id, layout_type="text_only")
                apply_row(new_scene, scene_export, SCENE_FIELDS)
                missing_speakers += remap_speakers(new_scene, SCENE_SPEAKER_FIELDS, speaker_ids)
                db.add(new_scene)
                # このシーンだけの読み（#73）
                import_readings(db, scene_export.get("readings"), scene_id=new_scene_id)

                # SceneAsset
                for asset_export in scene_export.get("assets", []):
                    new_asset_id = str(uuid.uuid4())
                    new_file_path = None

                    if asset_export.get("file_path"):
                        old_vid_id = old_vid["id"]
                        src = Path(tmp_dir) / "files" / old_vid_id / asset_export["file_path"]
                        if src.exists():
                            dst = new_vid_dir / asset_export["file_path"]
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(src), str(dst))
                            new_file_path = asset_export["file_path"]

                    new_asset = SceneAsset(
                        id=new_asset_id,
                        scene_id=new_scene_id,
                        slot=asset_export["slot"],
                        asset_type=asset_export["asset_type"],
                        file_path=new_file_path,
                        svg_content=asset_export.get("svg_content"),
                        display_config_json=asset_export.get("display_config_json"),
                    )
                    db.add(new_asset)

        await db.flush()

        stmt_result = select(Project).where(Project.id == new_project_id)
        result = (await db.execute(stmt_result)).scalars().first()
        warnings = []
        if missing_speakers:
            warnings.append(
                f"このアプリに無い話者が {missing_speakers} か所で指定されていたため、既定の話者に戻しました。"
                "話者の設定を確認してください。"
            )
        return ProjectImportRead.model_validate(result).model_copy(update={"import_warnings": warnings})


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Project).where(Project.id == project_id)
    proj = (await db.execute(stmt)).scalars().first()
    if not proj:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    count_stmt = select(func.count(Video.id)).where(Video.project_id == project_id)
    video_count = (await db.execute(count_stmt)).scalar() or 0

    read_obj = ProjectRead.model_validate(proj)
    read_obj.video_count = video_count
    return read_obj

@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(project_id: str, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(Project).where(Project.id == project_id)
    proj = (await db.execute(stmt)).scalars().first()
    if not proj:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    old_name = proj.name
    if payload.name is not None and payload.name != proj.name:
        stmt_check = select(Project).where(Project.name == payload.name)
        existing = (await db.execute(stmt_check)).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail="同名のプロジェクトが既に存在します")
        
        old_dir = PROJECTS_DIR / old_name
        new_dir = PROJECTS_DIR / payload.name
        if old_dir.exists():
            old_dir.rename(new_dir)
        else:
            new_dir.mkdir(parents=True, exist_ok=True)
        proj.name = payload.name

    if payload.description is not None:
        proj.description = payload.description

    await db.flush()

    count_stmt = select(func.count(Video.id)).where(Video.project_id == project_id)
    video_count = (await db.execute(count_stmt)).scalar() or 0

    read_obj = ProjectRead.model_validate(proj)
    read_obj.video_count = video_count
    return read_obj

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Project).where(Project.id == project_id)
    proj = (await db.execute(stmt)).scalars().first()
    if not proj:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    proj_dir = PROJECTS_DIR / proj.name
    if proj_dir.exists():
        shutil.rmtree(proj_dir)

    await db.delete(proj)
    await db.flush()


@router.get("/{project_id}/export")
async def export_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """プロジェクトを ZIP ファイルとしてエクスポートする。
    DB レコード（JSON）+ シーンアセットファイルを含む。音声・生成済み MP4 は含まない。"""

    # プロジェクト取得
    stmt_p = select(Project).where(Project.id == project_id)
    project = (await db.execute(stmt_p)).scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    # 動画一覧
    stmt_v = select(Video).where(Video.project_id == project_id)
    videos = (await db.execute(stmt_v)).scalars().all()

    # 各動画に紐づくデータを収集
    export_videos = []
    bgm_sources: dict[str, Path] = {}   # 動画 ID → BGM の実ファイル（ZIP に入れる）
    for video in videos:
        stmt_sty = select(VideoStyle).where(VideoStyle.video_id == video.id)
        style = (await db.execute(stmt_sty)).scalars().first()
        if style and style.bgm_path and Path(style.bgm_path).exists():
            bgm_sources[video.id] = Path(style.bgm_path)

        stmt_sc = select(Scenario).where(Scenario.video_id == video.id)
        scenario = (await db.execute(stmt_sc)).scalars().first()

        scenes_data = []
        if scenario:
            stmt_scenes = (
                select(Scene)
                .where(Scene.scenario_id == scenario.id)
                .order_by(Scene.index)
            )
            scenes = (await db.execute(stmt_scenes)).scalars().all()
            for scene in scenes:
                stmt_assets = select(SceneAsset).where(SceneAsset.scene_id == scene.id)
                assets = (await db.execute(stmt_assets)).scalars().all()
                scenes_data.append({
                    "id": scene.id,
                    # 引き継ぐ項目は services/video_copy.py の一覧で決める（#76）
                    **export_row(scene, SCENE_FIELDS),
                    # このシーンだけの読み（#73）。本文に記号が無いので、運ばないと読みが消える
                    "readings": await export_readings(db, scene_id=scene.id),
                    "assets": [
                        {
                            "id": a.id,
                            "slot": a.slot,
                            "asset_type": a.asset_type,
                            "file_path": a.file_path,      # video_dir 相対パス
                            "svg_content": a.svg_content,
                            "display_config_json": a.display_config_json,
                        }
                        for a in assets
                    ],
                })

        export_videos.append({
            "video": {
                "id": video.id,
                "name": video.name,
            },
            "style": {
                **export_row(style, STYLE_FIELDS),
                # BGM は動画のフォルダにあるファイル。ZIP の中の置き場所を書いておく
                "bgm_file": _bgm_zip_path(video.id, style.bgm_path),
            } if style else None,
            "scenario": export_row(scenario, SCENARIO_FIELDS) if scenario else None,
            "scenes": scenes_data,
        })

    manifest = {
        # 2.0: 全項目を書き出すようにした（#76）。1.0 のファイルも読み込める
        "version": "2.0",
        "app": "AI-MovGen",
        "exported_at": datetime.now().isoformat(),
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
        },
        "videos": export_videos,
        # プロジェクトの読み辞書（#73）
        "reading_dictionary": await export_readings(db, project_id=project.id),
    }

    # ZIP を in-memory で構築
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # アセットファイルを追加
        for vid_export in export_videos:
            vid_id = vid_export["video"]["id"]
            # 以前は PROJECTS_DIR / project.name 決め打ちで、フォルダ名が ID の
            # プロジェクト（新しく作ったもの）では画像素材が書き出されていなかった（#76）
            vid_dir = get_project_dir(project) / "videos" / vid_id

            style_export = vid_export.get("style") or {}
            if style_export.get("bgm_file") and bgm_sources.get(vid_id):
                zf.write(str(bgm_sources[vid_id]), style_export["bgm_file"])

            for scene_export in vid_export["scenes"]:
                for asset_export in scene_export["assets"]:
                    file_rel = asset_export.get("file_path")
                    if file_rel:
                        abs_path = vid_dir / file_rel
                        if abs_path.exists():
                            # ZIP 内パス: files/{video_id}/{file_rel}
                            zf.write(str(abs_path), f"files/{vid_id}/{file_rel}")

    from urllib.parse import quote

    buf.seek(0)
    filename = f"project_{project.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    encoded_filename = quote(filename)
    ascii_fallback = f"project_{project.id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}"
        },
    )
