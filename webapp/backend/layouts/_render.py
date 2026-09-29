"""レイアウトの描画 — Jinja2 環境とタイミング計算。

テンプレートは「何を出すか」だけを書き、「いつ出すか」は書かない。
テンプレートは登場の *役割* を data-seq で宣言し、実際の秒数はこの
モジュールが計算して data-start / data-duration に書き込む。

    <div class="clip" data-seq="head">              … タイトル。冒頭に出る
    <li class="clip" data-seq="spread" data-seq-index="{{ loop.index0 }}">
                                                     … 項目。シーン尺に均等配分
    <p  class="clip" data-seq="tail">               … まとめ。終盤に出る

この分業にしている理由:
  - 秒数をテンプレートに書くと、40 個のテンプレートに同じ計算が散らばる
  - シーンの尺はナレーション音声の長さで決まるため、テンプレートを書く時点では分からない
  - 「均等配分」の方針を変えたくなったとき、直す場所が 1 箇所で済む
"""

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from layouts._icons import icon_svg
from layouts._registry import LAYOUT_ROOT, LayoutSpec

# ---- タイミングの定数 ----------------------------------------------------
# シーン開始から見出しが出るまで。切替直後の一瞬を避ける。
HEAD_OFFSET = 0.5
# 最初の項目が出るまで。見出しを読む間を取る。
SPREAD_LEAD = 0.9
# 末尾に残す余白。ここで退場アニメーションが完了する。
EXIT_BUFFER = 0.5
# tail 要素が出る位置（シーン尺に対する割合）。
TAIL_RATIO = 0.8
# 項目同士の最小間隔。これを下回ると同時に出たように見えて分けた意味が消える。
MIN_STEP = 0.18


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def _slot(el) -> int:
    """data-seq-index をスロット番号として読む。

    テンプレートの書き損じ（空文字・非数値・負値）で描画全体を落とさない。
    読めなければ先頭スロット扱いにする。
    """
    try:
        return max(0, int(el.get("data-seq-index") or 0))
    except (TypeError, ValueError):
        return 0


# ==========================================================================
# Jinja2 環境
# ==========================================================================

def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(LAYOUT_ROOT)),
        # 自動エスケープが今回 Jinja2 を採用した主な理由。
        # タイトルやナレーションに < や & が入っても HTML が壊れない。
        autoescape=select_autoescape(default_for_string=True, default=True),
        # 未定義変数は握りつぶさず落とす。テンプレートの打ち間違いを
        # 「空欄の動画が出来てしまう」形ではなく、その場のエラーで気づけるようにする。
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["icon"] = lambda name, cls="layout-icon": Markup(icon_svg(name, cls))
    env.filters["nl2br"] = lambda s: Markup("<br>".join(Markup.escape(s).split("\n")))
    return env


_ENV: Environment | None = None


def env() -> Environment:
    global _ENV
    if _ENV is None:
        _ENV = _build_env()
    return _ENV


# ==========================================================================
# タイミングの割り当て
# ==========================================================================

def apply_timing(html: str, scene_start: float, scene_duration: float,
                 segment_starts: list[float] | None = None) -> str:
    """data-seq の役割を実秒（data-start / data-duration）に変換する。

    全要素はシーン末尾（scene_start + scene_duration - EXIT_BUFFER）で
    揃って退場する。退場だけバラバラだと目が散るため。
    """
    frag = BeautifulSoup(html, "html.parser")
    end = scene_start + max(0.2, scene_duration - EXIT_BUFFER)

    def assign(el, start: float):
        # data-seq-offset で微差を付けられる。同じ役割の要素（アイブロウとタイトル）を
        # わずかにずらして出すためのもので、役割そのものは変えない。
        try:
            start += float(el.get("data-seq-offset") or 0)
        except ValueError:
            pass
        start = min(start, end - 0.2)
        el["data-start"] = _fmt(start)
        el["data-duration"] = _fmt(max(0.1, end - start))

    for el in frag.select('[data-seq="head"]'):
        assign(el, scene_start + HEAD_OFFSET)

    for el in frag.select('[data-seq="tail"]'):
        assign(el, scene_start + scene_duration * TAIL_RATIO)

    # data-seq-index は「何番目に出るか」ではなく「シーンのどのスロットで出るか」。
    # 同じ番号を付けた要素は同時に出る。
    # 例: 横型フローの矢印は、その矢印が指す先のステップと同じ番号を持つ。
    #     番号を単純な並び順にすると、最後の矢印だけが「何も無い方を指したまま
    #     次のステップを待つ」時間が生まれてしまう。
    #
    # スロット数はシーン全体でひとつに決める。以前は「同じ親を共有するグループ」
    # ごとに数え直していたが、図解レイアウトは位置決めの .diagram-node で
    # 要素を 1 個ずつ包むため、要素それぞれが単独のグループになってしまい、
    # slots が要素ごとに変わっていた。結果、12 秒のシーンで円環フローの 4 ノードが
    # 0.90 / 7.97 / 9.38 / 9.99 秒に出て、前半 7 秒が空白になっていた。
    # 1 シーン = 1 レイアウトなので、番号はそのテンプレートの作者が意図して
    # 振ったもの。シーン全体で通し番号として扱うのが正しい。
    spread = frag.select('[data-seq="spread"]')
    if spread:
        indices = [_slot(el) for el in spread]
        slots = max(indices) + 1
        # ナレーションの区切りが分かっていれば、その項目を語り始めた秒数で出す。
        #
        # 区切りは「導入 + 項目ぶん」で来ることが多いが、導入が無いこともある。
        # 数で見分ける。多い方（slots + 1）なら先頭が導入なので 1 つずらす。
        #   区切り 4 / スロット 3 → 導入あり。スロット i は segment_starts[i+1]
        #   区切り 4 / スロット 4 → 導入なし。スロット i は segment_starts[i]
        #
        # 足りないときは使わない。半端に使うと前半だけ声に合って後半がずれる、
        # という分かりにくい見え方になる。
        offset = 0
        if segment_starts:
            if len(segment_starts) >= slots + 1:
                offset = 1
            elif len(segment_starts) < slots:
                segment_starts = None
        usable = max(0.0, scene_duration - SPREAD_LEAD - EXIT_BUFFER)
        step = max(MIN_STEP, usable / slots)
        for el, idx in zip(spread, indices):
            if segment_starts:
                assign(el, scene_start + segment_starts[idx + offset])
            else:
                assign(el, scene_start + SPREAD_LEAD + idx * step)

    # 役割を持たない .clip（テンプレートの書き忘れ）を放置すると、
    # app.js が data-start を読めずアニメーション対象から外れ、
    # 「その要素だけ最初から出っぱなし」という分かりにくい崩れ方をする。
    for el in frag.select(".clip"):
        if not el.get("data-start"):
            assign(el, scene_start + HEAD_OFFSET)

    return "".join(str(c) for c in frag.contents)


# 「シーンの最後まで出ていた」とみなす幅（秒）。最も遅く消える要素との差がこれ以内なら、
# その要素もシーンの最後まで出すつもりで置かれたものとして扱う。
CUSTOM_END_TOLERANCE = 0.3


def place_custom_html(html: str, scene_start: float, scene_duration: float) -> str:
    """カスタム HTML（AI デザイン調整・コード編集）の時刻を、動画の中の時刻に直す（#93）。

    カスタム HTML の data-start / data-duration は「シーンの頭からの秒数」で書く
    （編集画面に出す HTML がシーンの頭を 0 秒として作られており、AI にもそう指示している）。
    一方 app.js は、動画の先頭からの秒数として読む。以前はそのまま埋め込んでいたため、
    2 番目以降のシーンでは要素がシーンより前に出て消えてしまい、何も表示されなかった。

    編集した時点のシーンの長さと、今のシーンの長さは違いうる（音声を合成すると
    文字数からの見積もりより長くも短くもなる）。そこで、編集した時点で
    最後まで出ていた要素（最も遅く消える要素と同時に消えるもの）は、
    今のシーンの最後まで出す。途中で消えるように置いた要素は、その時刻のまま。
    """
    frag = BeautifulSoup(html, "html.parser")
    timed = []
    for el in frag.select("[data-start]"):
        try:
            start = float(el["data-start"])
            duration = float(el.get("data-duration", "nan"))
        except (TypeError, ValueError):
            continue
        if duration == duration:          # NaN（data-duration 無し）でない
            timed.append((el, start, duration))
    if not timed:
        return html

    last_end = max(start + duration for _, start, duration in timed)
    # 自動生成のレイアウト（apply_timing）と同じく、末尾に退場の余白を残す
    scene_end = max(0.2, scene_duration - EXIT_BUFFER)
    for el, start, duration in timed:
        start = min(max(start, 0.0), scene_end - 0.1)
        end = start + duration
        if last_end - end <= CUSTOM_END_TOLERANCE or end > scene_end:
            end = scene_end
        el["data-start"] = _fmt(scene_start + start)
        el["data-duration"] = _fmt(max(0.1, end - start))
    return "".join(str(c) for c in frag.contents)


# ==========================================================================
# 描画
# ==========================================================================

def render(
    spec: LayoutSpec,
    content: dict,
    *,
    scene_start: float,
    scene_duration: float,
    aspect: str = "16:9",
    count: int = 0,
    extra: dict | None = None,
    segment_starts: list[float] | None = None,
) -> str:
    """レイアウト 1 枚ぶんの HTML 断片を返す（<div class="slide"> の中身）。"""
    ctx = dict(extra or {})
    if spec.prepare:
        # レイアウト固有の前処理（グラフのスクリプト生成など）。
        # 失敗してもそのレイアウトが素の状態で描かれるだけで、動画生成は止めない。
        try:
            ctx.update(spec.prepare(content, ctx))
        except Exception as e:  # noqa: BLE001
            print(f"[layouts] {spec.id} の prepare が失敗: {e}")

    template = env().get_template(f"{spec.id}/template.html")
    html = template.render(
        c=content,
        s=spec,
        count=count,
        aspect=aspect,
        **ctx,
    )
    return apply_timing(html, scene_start, scene_duration, segment_starts)
