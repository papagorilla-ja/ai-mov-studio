"""LLM プロンプトの部品を、型とレイアウトの定義から自動で組み立てる。

プロンプトに値を直書きしない（design_tokens.py と同じ方針）。
レイアウトを 1 つ足したら、AI が選べる候補にも自動で載る。

2 段階にしている理由:
    ローカルの qwen3:14b に 40 種類のスキーマを一度に見せるのは、
    トークン量でも選択精度でも成立しない。

      段階 1 … 「この内容はどの型か」            14 択
      段階 2 … その型のスキーマで内容を作りつつ
               「どの見せ方か」を選ぶ             4〜6 択
      段階 3 … 件数・縦横比・連続の検査（LLM 不使用、_registry.resolve）
"""

from layouts._icons import icon_names
from layouts._registry import get, layouts_for_type
from layouts._types import CONTENT_TYPES, COMMON_FIELDS, FieldSpec
# 秒と文字数の換算は design_tokens に一本化する（ここに数値を持たない）。
# design_tokens は何も import しない葉モジュールなので循環しない。
from services.design_tokens import BASE_CHARS_PER_SEC, narration_target_chars


# ==========================================================================
# 段階 1 — 型の一覧
# ==========================================================================

def type_menu(allowed: tuple[str, ...] | None = None) -> str:
    """「この内容はどの型か」を選ばせるための一覧。

    description（何の型か）だけでなく when_to_use（どんなときに選ぶか／
    どんなときは選ばないか）も出す。description だけを見せていた頃は
    並列と画像に偏り、階層や循環がほとんど選ばれなかった。
    """
    ids = allowed or tuple(CONTENT_TYPES)
    lines = []
    for tid in ids:
        ct = CONTENT_TYPES.get(tid)
        if not ct:
            continue
        lines.append(f'  - "{ct.id}"（{ct.label}）: {ct.description}')
        if ct.when_to_use:
            lines.append(f"      選ぶ目安: {ct.when_to_use}")
    return "\n".join(lines)


# ==========================================================================
# 段階 2 — 型のスキーマと見せ方の候補
# ==========================================================================

def _field_line(f: FieldSpec, indent: str, last: bool = False) -> list[str]:
    """1 フィールドを「JSON の形 + 書き方の指針」の行にする。

    末尾カンマの有無まで正しく出すこと。LLM はこの雛形をそのまま真似るため、
    壊れた JSON を見せると壊れた JSON を返してくる。
    """
    note = f"{f.label}"
    if f.hint:
        note += f" — {f.hint}"
    if f.max_chars:
        note += f"（{f.max_chars}文字以内）"
    comma = "" if last else ","

    if f.kind == "items":
        out = [f'{indent}"{f.name}": [                 // {note}', f"{indent}  {{"]
        for i, child in enumerate(f.children):
            out.extend(_field_line(child, indent + "    ", last=(i == len(f.children) - 1)))
        out.append(f"{indent}  }}")
        out.append(f"{indent}]{comma}")
        return out
    if f.kind == "group":
        out = [f'{indent}"{f.name}": {{                // {note}']
        for i, child in enumerate(f.children):
            out.extend(_field_line(child, indent + "  ", last=(i == len(f.children) - 1)))
        out.append(f"{indent}}}{comma}")
        return out
    if f.kind == "tree":
        return [f'{indent}"{f.name}": [{{"label": "…", "text": "…", "children": []}}]{comma}   // {note}']
    if f.kind == "table":
        return [f'{indent}"headers": ["…", "…"],   // {note}', f'{indent}"rows": [["…", "…"]]{comma}']
    if f.kind == "chart":
        return [f'{indent}"chart": {{"type": "bar|line|pie", "labels": ["…"], "values": [0], "unit": "…"}}{comma}   // {note}']
    if f.kind == "images":
        return [f'{indent}"image_description": "…"{comma}   // どんな画像を置くべきかを日本語 30〜60 文字で']
    if f.kind == "choice":
        opts = " | ".join(f.options)
        return [f'{indent}"{f.name}": "{opts}"{comma}   // {note}（この中から選ぶ）']
    return [f'{indent}"{f.name}": "…"{comma}   // {note}']


def schema_sketch(type_id: str) -> str:
    """その型の JSON の形を、書き方の指針つきで組み立てる。"""
    ct = CONTENT_TYPES.get(type_id)
    if not ct:
        return "{}"
    # 画像そのものは人間がアップロードするので、AI には「何を置くべきか」だけ書かせる。
    fields = list(COMMON_FIELDS) + list(ct.fields)
    lines = ["{"]
    for i, f in enumerate(fields):
        lines.extend(_field_line(f, "  ", last=(i == len(fields) - 1)))
    lines.append("}")
    return "\n".join(lines)


def layout_menu(type_id: str, aspect: str = "16:9", only: str | None = None) -> str:
    """その型に属する見せ方の候補一覧。

    only を渡すと、その 1 つだけを出す。ユーザーが見せ方を固定したとき用で、
    候補を絞ることで「件数の上限」が LLM に正しく伝わる
    （他の候補の上限に引きずられて、収まらない件数を書かせないため）。
    """
    lines = []
    for s in layouts_for_type(type_id):
        if aspect not in s.aspect:
            continue
        if only and s.id != only:
            continue
        cap = "件数の制限なし" if s.capacity.any else f"{s.capacity.min}〜{s.capacity.max}件"
        lines.append(f'  - "{s.id}"（{s.label} / {cap}）: {s.when_to_use}')
    return "\n".join(lines)


def default_layout_for(type_id: str) -> str:
    """章立ての段階（まだ内容が無い時点）で置く見せ方。

    型が宣言した default_layout を使う。以前はその型のレイアウトのうち
    ディレクトリ名が一番先のものを機械的に返していたため、
    宣言 → statement_bignum（巨大数値）、扉 → cover_summary（まとめ）のように
    内容と無関係な既定が付いていた。
    """
    ct = CONTENT_TYPES.get(type_id)
    if ct and ct.default_layout and get(ct.default_layout):
        return ct.default_layout
    specs = layouts_for_type(type_id)
    return specs[0].id if specs else "text_only"


ICON_VOCABULARY_NOTE = (
    "icon に書けるのは次の語だけです（それ以外を書くとアイコンは表示されません）:\n  "
    + " / ".join(icon_names())
)


def narration_length_rule(target_chars: int | None = None) -> str:
    """ナレーションの長さの指示文（「約 N 文字（読み上げで約 M 秒）」）。

    秒と文字数を両方伝える（秒だけだと尺の感覚が無く、
    文字数だけだと「長い/短い」の狙いが伝わらない）。
    換算は design_tokens 側の実測値（5.96 文字/秒）に一本化している。
    内容生成・ナレーションのみの生成・PPTX 取り込みの全経路でこれを使う。
    以前は経路ごとに「300〜500文字」と決め打ちしていて、設定が効かなかった（#53）。
    """
    chars = target_chars if target_chars and target_chars > 0 else narration_target_chars(None)
    return f"約 {chars} 文字（読み上げで約 {round(chars / BASE_CHARS_PER_SEC)} 秒）"


def content_prompt(type_id: str, title: str, summary: str, aspect: str = "16:9",
                   *, target_chars: int | None = None,
                   fixed_layout: str | None = None,
                   context: str = "") -> str:
    """段階 2 のプロンプト。内容の生成と見せ方の選択を 1 回のやり取りで行う。

    target_chars … ナレーションの目安の文字数。None なら既定（標準）を使う。
    fixed_layout … ユーザーが見せ方を固定しているとき、その ID。
                   見せ方の一覧をその 1 つに絞り、件数の上限も伝える。
    context      … 動画全体の中での位置づけ（services.scene_context が作る）。
                   空ならシーン単独の情報だけで作る。
    """
    ct = CONTENT_TYPES.get(type_id) or CONTENT_TYPES["statement"]
    menu = layout_menu(type_id, aspect, only=fixed_layout)
    fallback = default_layout_for(type_id)
    uses_icon = any(
        child.name == "icon" for f in ct.fields for child in f.children
    )

    narration_rule = narration_length_rule(target_chars)
    # 位置づけの節は、シーン単独の情報（タイトル・あらすじ）の直後に置く。
    # 何を作るか（【1】）より先に読ませて、書き出しから流れに乗せるため。
    context_block = f"{context}\n\n" if context else ""

    # 件数を持つ型だけ、ナレーションを項目に対応した区切りで書かせる。
    # こうすると「3 番目の項目を語り始めた瞬間に 3 番目が出る」ようにできる。
    #
    # 以前は 1 本のナレーションを均等配分していたが、実測すると
    # 項目の見出しが本文に出てくるのは 39%、順番どおりなのは 33% のシーンだけで、
    # ナレーションとスライドが別々に書かれていた。
    # 推測で対応づけるのではなく、最初から対応づけて書かせる。
    segments_rule = ""
    segments_key = ""
    if ct.collection:
        segments_rule = (
            "- narration_segments には、上のナレーションを項目に対応させて分けたものを入れる\n"
            "    - 1 番目は導入（項目に入る前の前置き）。不要なら空文字にする\n"
            "    - 2 番目以降が項目 1, 2, 3 … に対応する。**項目と同じ順に語ること**\n"
            "    - 連結すると narration_text とちょうど一致すること\n"
        )
        segments_key = ', "narration_segments": ["導入", "項目1について", "項目2について", "…"]'

    return f"""あなたは研修動画のスライドを作るプロの構成作家です。

このシーンは「{ct.label}」の型で作ります。
{ct.description}

シーンタイトル: {title or "無題"}
このシーンのあらすじ（意図）: {summary or "（未設定）"}

{context_block}【1】次の JSON の形で、スライドに載せる内容を作ってください。
コメント（//）は書き方の指針です。出力には含めないでください。

{schema_sketch(type_id)}

【2】あわせて、この内容に最も合う「見せ方」を次から 1 つ選び、layout に書いてください。

{menu or f'  - "{fallback}"'}

{ICON_VOCABULARY_NOTE if uses_icon else ""}

【共通ルール】
- ナレーション(narration_text)は丁寧語（です・ます調）で、{narration_rule}
- スライドの文言をそのまま読み上げるのではなく、スライドを補足して語る内容にする
- 指定した文字数の目安を必ず守る。長いと動画のスライドからはみ出します
- JSON以外の文字（前置き・解説・「以下が結果です」等）は一切出力しない
{segments_rule}
出力は次の形の JSON のみ:
{{"layout": "見せ方の値", "slide_content_json": {{ ここに【1】の内容 }}, "narration_text": "…"{segments_key}}}"""
