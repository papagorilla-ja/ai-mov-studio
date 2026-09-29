"""シーン生成に渡す「動画全体の文脈」。

シーンの内容やナレーションを AI に作らせるとき、そのシーンのタイトルと
あらすじだけを渡すと、LLM は毎回「ひとつの動画の冒頭」として書いてしまう。
実際に、23 シーン中 7 番目のナレーションが「こんにちは、今回は…」で始まっていた（#53）。

そこで次の 3 つを添える。
  - 位置      … 全体の何番目か。挨拶を許すのは 1 番目だけ
  - 構成      … 全シーンのタイトルとあらすじ。前後の流れと、扱う範囲の線引きが分かる
  - 元資料    … 貼り付けた原稿やチャットでの依頼。用語や語り口を揃えるため

元資料は上限の文字数（SOURCE_EXCERPT_CHARS）までしか渡さない。
貼り付け原稿は 3 万字を超えることがあり、毎回全文を渡すと
1 シーンあたり 15 秒前後遅くなる（一括生成で 23 シーンなら約 6 分）。

組み立て（build_scene_context）は DB に触れない純関数にしてある。
一括生成では DB から 1 回だけ読み、シーンごとに組み立て直す。
"""

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.scenario import Scenario
from models.scene import Scene
from models.video import Video
from services.reading import strip_markup

# 元資料の抜粋の上限（文字数、チャットと原稿の合計）。
# 日本語 1 文字 ≒ 0.6 トークンなので約 3,600 トークン。
SOURCE_EXCERPT_CHARS = 6000
# そのうちチャットでの依頼に割く上限。依頼は短いことが多く、
# 原稿の方が中身の手がかりになるので、原稿に多く残す。
CHAT_EXCERPT_CHARS = 2000
# 構成の一覧で、各シーンのあらすじを何文字まで載せるか。
# 今回のシーンのあらすじは別の欄で全文を渡すので、一覧は流れが掴めれば足りる。
OUTLINE_SUMMARY_CHARS = 60
# 直前のシーンのナレーションを何文字まで載せるか（末尾から）。
# つなぎに要るのは話の終わり方だけなので、全文は渡さない。
PREV_NARRATION_TAIL_CHARS = 160


@dataclass(frozen=True)
class SceneContext:
    """1 シーンぶんの文脈。to_prompt() でプロンプトに差し込む文章になる。"""

    video_name: str
    position: int           # 1 始まり
    total: int
    outline: tuple[str, ...]  # 構成の一覧（1 行 1 シーン。今回のシーンに印付き）
    prev_narration_tail: str
    next_title: str
    # 元資料の抜粋。(見出し, 本文) の組。無ければ空
    sources: tuple[tuple[str, str], ...]

    @property
    def is_first(self) -> bool:
        return self.position <= 1

    def to_prompt(self) -> str:
        """プロンプトに差し込む【動画全体の中での位置づけ】の節を返す。"""
        lines = ["【動画全体の中での位置づけ】"]
        if self.video_name:
            lines.append(f"動画名: {self.video_name}")
        lines.append(f"このシーンは全 {self.total} シーン中の {self.position} 番目です。")
        lines.append("")
        lines.append("動画の構成（→ が今回のシーン）:")
        lines.extend(self.outline)

        if self.prev_narration_tail:
            lines.append("")
            lines.append(f"直前のシーンのナレーション（終わりの部分）: 「{self.prev_narration_tail}」")
        if self.next_title:
            lines.append(f"次のシーン: 「{self.next_title}」")

        for label, text in self.sources:
            lines.append("")
            lines.append(f"元資料（{label}）:")
            lines.append('"""')
            lines.append(text)
            lines.append('"""')

        lines.append("")
        lines.append("【つながりのルール】")
        lines.append("- 上の構成の中の 1 シーンとして、動画全体の流れと語り口に合わせて書く")
        lines.append("- このシーンのあらすじに集中し、他のシーンが扱う話題には踏み込まない")
        if self.sources:
            lines.append("- 元資料の用語・内容に沿う。元資料と食い違うことは書かない")
        if self.is_first:
            lines.append("- 動画の冒頭のシーンなので、挨拶と動画全体の導入から始めてよい")
        else:
            lines.append(
                "- 動画の途中のシーンなので、「こんにちは」などの挨拶や、"
                "動画全体の導入・自己紹介は入れない。直前のシーンから続けて話すように始める"
            )
        return "\n".join(lines)


# ==========================================================================
# 組み立て（純関数）
# ==========================================================================

def build_scene_context(
    scene: Scene,
    all_scenes: list[Scene],
    scenario: Scenario | None,
    video_name: str = "",
) -> SceneContext:
    """シーンの文脈を組み立てる。all_scenes は同じシナリオの全シーン（順不同で可）。"""
    ordered = sorted(all_scenes, key=lambda s: s.index)
    # index は歯抜けになりうる（削除後など）。位置は並び順で数える。
    pos = next((i for i, s in enumerate(ordered) if s.id == scene.id), 0)
    prev_scene = ordered[pos - 1] if pos > 0 else None
    next_scene = ordered[pos + 1] if pos + 1 < len(ordered) else None

    return SceneContext(
        video_name=video_name or "",
        position=pos + 1,
        total=len(ordered),
        outline=tuple(_outline_line(i + 1, s, s.id == scene.id) for i, s in enumerate(ordered)),
        # ルビ・間の書式（#60）は LLM には不要なので、表記だけにして渡す
        prev_narration_tail=_tail(strip_markup(prev_scene.narration_text) if prev_scene else "",
                                  PREV_NARRATION_TAIL_CHARS),
        next_title=(next_scene.title or "") if next_scene else "",
        sources=_source_sections(scenario, position=pos + 1, total=len(ordered)),
    )


def _outline_line(no: int, scene: Scene, current: bool) -> str:
    summary = _clip(" ".join((scene.outline_summary or "").split()), OUTLINE_SUMMARY_CHARS)
    mark = "→" if current else " "
    return f"{mark} {no}. {scene.title or '無題'}" + (f" — {summary}" if summary else "")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _tail(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else "…" + text[-limit:]


def _source_sections(scenario: Scenario | None, *, position: int,
                     total: int) -> tuple[tuple[str, str], ...]:
    """元資料の抜粋を (見出し, 本文) の組で返す。渡すものが無ければ空。

    source_type では片方に絞らない。動画を作った時点でシナリオは "paste" で作られ、
    その後のチャットは同じシナリオに履歴として足される。そのため
    「原稿を貼ってからチャットで直した」動画は、原稿とチャットの両方を持つ。
    """
    if scenario is None:
        return ()
    sections: list[tuple[str, str]] = []

    chat = _chat_requests(scenario.chat_messages)
    if chat:
        sections.append(("企画チャットでのユーザーの依頼", chat))

    # pptx の source_content はファイル名しか入っていない。
    # スライドの中身は各シーンのあらすじに取り込み済みなので、構成の一覧で足りる。
    text = "" if scenario.source_type == "pptx" else (scenario.source_content or "").strip()
    budget = SOURCE_EXCERPT_CHARS - len(chat)
    if text:
        if len(text) <= budget:
            sections.append(("貼り付けた原稿", text))
        else:
            sections.append((f"貼り付けた原稿 {len(text):,} 字のうち、このシーンの位置に当たる部分",
                             _window(text, position, total, budget)))
    return tuple(sections)


def _chat_requests(raw: str | None) -> str:
    """チャット履歴から、ユーザーの発言だけを箇条書きにして返す。

    履歴には system（構成の一覧やアシスタントへの指示）とアシスタントの提案が混ざる。
    提案は既に構成へ反映済みなので、テーマ・対象者・トーンといった
    「依頼の意図」が入っているユーザーの発言だけを渡す。
    最初の依頼にテーマが書かれていることが多いので、先頭から残す。
    """
    try:
        messages = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ""
    if not isinstance(messages, list):
        return ""
    said = [str(m.get("content") or "").strip() for m in messages
            if isinstance(m, dict) and m.get("role") == "user"]
    return _clip("\n".join(f"- {t}" for t in said if t), CHAT_EXCERPT_CHARS)


def _window(text: str, position: int, total: int, size: int) -> str:
    """長い原稿から、シーンの位置に比例した場所を size 文字だけ切り出す。

    先頭から切るだけだと、後半のシーンに冒頭の話ばかり渡すことになる。
    シーンの並びは原稿の並びに沿って作られるので、
    「全体の何割目のシーンか」を原稿の同じ割合の位置に当てる。
    """
    center = int(len(text) * (position - 0.5) / max(1, total))
    start = max(0, min(len(text) - size, center - size // 2))
    end = start + size
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


# ==========================================================================
# DB から読む
# ==========================================================================

async def load_context_sources(
    scenario_id: str, db: AsyncSession,
) -> tuple[list[Scene], Scenario | None, str]:
    """文脈の材料（全シーン・シナリオ・動画名）をまとめて読む。

    一括生成ではこれを 1 回だけ呼び、シーンごとに build_scene_context で組み立てる。
    シーンのオブジェクトは生成のたびに書き換わるので、直前のシーンの
    ナレーションは常に最新（今回の一括生成で作ったもの）が使われる。
    """
    scenes = (await db.execute(
        select(Scene).where(Scene.scenario_id == scenario_id).order_by(Scene.index)
    )).scalars().all()
    scenario = (await db.execute(
        select(Scenario).where(Scenario.id == scenario_id)
    )).scalars().first()
    video_name = ""
    if scenario is not None:
        video_name = (await db.execute(
            select(Video.name).where(Video.id == scenario.video_id)
        )).scalars().first() or ""
    return list(scenes), scenario, video_name


async def load_scene_context(scene: Scene, db: AsyncSession) -> SceneContext:
    """シーン 1 つぶんの文脈を DB から読んで組み立てる。"""
    scenes, scenario, video_name = await load_context_sources(scene.scenario_id, db)
    return build_scene_context(scene, scenes, scenario, video_name)
