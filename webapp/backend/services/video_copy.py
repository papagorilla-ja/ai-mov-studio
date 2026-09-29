"""動画の複製・プロジェクトの書き出し/読み込みで、何を引き継ぐか（#76）。

以前は複製・書き出し・読み込みの 3 か所が、写す項目を 1 つずつ手で書いていた。
機能を足すたびにそこを直し忘れ、ナレーションの長さ・3D 背景・話速・あらすじ・
元資料などが、複製や読み込みで黙って既定値に戻っていた。

ここでは、各テーブルの全列を「引き継ぐ」「引き継がない（理由つき）」の
どちらかに分類する。3 か所はこの一覧だけを使う。

列を足したのに分類し忘れると、起動時に warn_unclassified() が警告を出す。
分類されていない列は引き継がれない（安全側に倒れる）ので、動作は壊れない。
"""
import json
import logging

from models.scenario import Scenario
from models.scene import Scene
from models.video_style import VideoStyle

logger = logging.getLogger(__name__)

# ── シーン ──────────────────────────────────────────────
SCENE_FIELDS = (
    "index", "title", "layout_type", "slide_content_json",
    "narration_text", "outline_summary",
    "speaker_id", "speaker_b_id",
    "narration_length", "layout_pinned",
    "custom_html", "custom_css", "image_prompt",
    "narration_segments_json",      # 区切りの文字列だけ（秒数は捨てる。scene_value を参照）
    "narration_ai_readings_json",   # 本文のハッシュ付きなので、本文と一緒に写せばそのまま使える
)
SCENE_EXCLUDED = {
    "id": "新しく振る",
    "scenario_id": "新しいシナリオに付け替える",
    "created_at": "新しく記録する",
    "updated_at": "新しく記録する",
    # 音声は引き継がず、最初の生成で合成し直す。音声から決まる値も一緒に捨てる
    "narration_audio_path": "音声は引き継がない",
    "narration_audio_duration": "音声は引き継がない",
    "narration_audio_degraded": "音声は引き継がない",
    "narration_audio_warning": "音声は引き継がない",
    "data_start": "音声の長さから決まる",
    "data_duration": "音声の長さから決まる",
}

# ── スタイル ────────────────────────────────────────────
STYLE_FIELDS = (
    "template_id",
    "color_primary", "color_secondary", "color_accent", "color_bg", "color_text_primary",
    "font_heading", "font_body",
    "background_motif", "decor_style", "type_scale", "transition",
    "layout_breadth", "motion_character", "background_3d",
    "style_prompt", "custom_css",
    "default_speaker_id", "default_speaker_b_id",
    "bgm_volume", "bgm_prompt",
    "narration_length", "narration_speed",
    "canvas_width", "canvas_height",
)
STYLE_EXCLUDED = {
    "id": "新しく振る",
    "video_id": "新しい動画に付け替える",
    # 動画ごとのフォルダにあるファイルを指す。ファイルをコピーしてから付け直す
    "bgm_path": "ファイルをコピーして、コピー先を指し直す",
}

# ── シナリオ ────────────────────────────────────────────
SCENARIO_FIELDS = ("source_type", "source_content", "chat_messages")
SCENARIO_EXCLUDED = {
    "id": "新しく振る",
    "video_id": "新しい動画に付け替える",
    "created_at": "新しく記録する",
}

# 話者を指す列。話者はアプリ全体の設定で書き出しに含まれないので、
# 読み込み先に無ければ外す（remap_speakers）
SCENE_SPEAKER_FIELDS = ("speaker_id", "speaker_b_id")
STYLE_SPEAKER_FIELDS = ("default_speaker_id", "default_speaker_b_id")

# 動画のフォルダを複製するとき、コピーしないもの（音声は合成し直す）
DUPLICATE_SKIP_DIRS = ("assets/audio", "output", "preview")

_TABLES = (
    (Scene, SCENE_FIELDS, SCENE_EXCLUDED),
    (VideoStyle, STYLE_FIELDS, STYLE_EXCLUDED),
    (Scenario, SCENARIO_FIELDS, SCENARIO_EXCLUDED),
)


def unclassified() -> dict[str, list[str]]:
    """分類されていない列（テーブル名 → 列名）。分類に無い列名も含める。"""
    out: dict[str, list[str]] = {}
    for model, fields, excluded in _TABLES:
        columns = {c.name for c in model.__table__.columns}
        classified = set(fields) | set(excluded)
        problems = sorted(columns - classified) + sorted(f"（存在しない列）{c}" for c in classified - columns)
        if problems:
            out[model.__tablename__] = problems
    return out


def warn_unclassified() -> None:
    """起動時に呼ぶ。分類漏れがあれば、直す場所まで示して警告する。"""
    for table, columns in unclassified().items():
        logger.warning(
            f"[video_copy] {table} の列が、複製・書き出しの分類に入っていません: {', '.join(columns)}。"
            "services/video_copy.py の *_FIELDS（引き継ぐ）か *_EXCLUDED（引き継がない）に足してください。"
            "足すまでは、複製・書き出し・読み込みでこの列は引き継がれません。"
        )


def scene_value(field: str, value):
    """シーンの列を引き継ぐときの値。区切りだけは秒数を捨てる。

    区切りの秒数（starts）は音声から測った値。音声を引き継がないので、
    残すと合成し直すまでの間、古い秒数で要素が出てしまう。
    """
    if field == "narration_segments_json" and value:
        try:
            data = json.loads(value)
        except ValueError:
            return None
        texts = data.get("texts") if isinstance(data, dict) else None
        return json.dumps({"texts": texts}, ensure_ascii=False) if texts else None
    return value


def export_row(obj, fields: tuple[str, ...]) -> dict:
    """モデルの行を、書き出し用の dict にする。"""
    return {f: (scene_value(f, getattr(obj, f)) if isinstance(obj, Scene) else getattr(obj, f))
            for f in fields}


def apply_row(obj, data: dict, fields: tuple[str, ...]) -> None:
    """dict（書き出したもの、または複製元の値）をモデルの行に書き戻す。

    dict に無い列には触らない（モデルの既定値のまま）。古い書き出しファイルには
    新しい列が無いので、None で上書きすると NOT NULL の列（話速など）で落ちる。
    """
    for f in fields:
        if f in data:
            value = data[f]
            setattr(obj, f, scene_value(f, value) if isinstance(obj, Scene) else value)


def remap_speakers(obj, fields: tuple[str, ...], valid_ids: set[str]) -> int:
    """存在しない話者の指定を外す（既定の話者に戻る）。外した数を返す。"""
    removed = 0
    for f in fields:
        value = getattr(obj, f, None)
        if value and value not in valid_ids:
            setattr(obj, f, None)
            removed += 1
    return removed
