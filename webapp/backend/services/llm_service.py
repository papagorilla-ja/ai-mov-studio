"""ローカル LLM に頼む処理（シナリオ・シーン内容・ナレーション・デザイン）。

失敗はふつうの例外で返す。画面に出す HTTP のエラーにするのはルーター側
（routers/llm_errors.py）。
  - RuntimeError … LLM に届かなかった（llm_client.chat_completion）
  - ValueError   … 引き直しても JSON として読めなかった（_ask_json）
"""
import json
import re
from services.design_tokens import narration_target_chars
from services.llm_client import chat_completion
from schemas.scenario import ScenarioOutline
from layouts import _prompts, _types
from layouts._prompts import narration_length_rule
from layouts import _registry as layouts

# scenario.py のテンプレートなどをこちらに移行して集約
# テキスト貼り付け（Route B）のアウトライン生成。
# 以前はここで「全シーンの内容」まで 1 回の呼び出しで作らせていたが、
# その方式だと 14 型ぶんのスキーマをプロンプトに詰め込む必要があり、
# qwen3:14b では破綻する。章立てだけを作らせ、中身はシーンごとに深掘りする。
PROMPT_B_TEMPLATE = """あなたは動画の構成を作成するアシスタントです。
ユーザーから入力された「テキスト」を読み取り、論理的な意味のまとまり（シーン）ごとに分割して、
動画の章立てを作ってください。この段階では**各シーンのタイトル・あらすじ・情報の型**だけを決めます。
スライドの文面やナレーション本文はここでは作りません。

必ずインプットテキスト全体をカバーし、複数（2〜10程度）のシーンに分割してください。
1つのシーンにすべてをまとめないでください。

**情報の型（content_type）はこの一覧から選ぶこと:**
{{type_menu}}

同じ型が延々と続かないよう、内容に応じて使い分けてください。
ただし、内容に合わない型を無理に混ぜないでください。

**出力形式:**
マークダウンコードブロック（```json ... ```）で囲って、次の JSON のみを出力してください。
前置きや説明文は一切含めないでください。

{
  "scenes": [
    {
      "index": 1,
      "title": "シーンのタイトル（10〜28文字）",
      "summary": "このシーンで扱う内容のあらすじ（1〜2文）",
      "content_type": "上の一覧から選んだ型の値"
    }
  ]
}

**インプットテキスト:**
{{pasted_text}}"""



def _loads(text: str):
    """LLM が返した JSON をパースする。

    strict=False にしているのは、文字列リテラルの中に生の改行がそのまま
    入ってくることがあるため。既定の strict=True では「不正な制御文字」として
    弾かれてしまうが、実害は無いので受け入れる。
    （実測で Invalid control character による失敗を確認している）
    """
    return json.loads(text, strict=False)

def extract_outline_proposal(text: str) -> ScenarioOutline | None:
    """LLM 応答から軽量アウトライン JSON を抽出する。途中で切れていても、
    パースできる範囲の scene 要素だけを救済して返す。"""
    candidates = []
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        candidates.append(m.group(1))
    m2 = re.search(r"(\{.*\})", text, re.DOTALL)
    if m2:
        candidates.append(m2.group(1))
    for c in candidates:
        try:
            data = _loads(c)
            return ScenarioOutline.model_validate(data)
        except Exception:
            pass
    # 2) 救済: "scenes": [ ... ] の中から、閉じている { ... } オブジェクトだけを個別に拾う
    try:
        arr_start = text.index('"scenes"')
        sub = text[arr_start:]
        items = []
        for obj in re.finditer(r"\{[^{}]*\}", sub):
            try:
                items.append(_loads(obj.group(0)))
            except Exception:
                continue
        if items:
            return ScenarioOutline.model_validate({"scenes": items})
    except Exception:
        pass
    return None


def _parse_json_reply(raw: str) -> dict | None:
    """LLM の応答から JSON を取り出す。取り出せなければ None。

    3 段階で試す。壊れ方はモデルの気分次第なので、機械的に直せる範囲だけ直す。
      1. コードブロックを剥がしてそのまま
      2. 最初の { から最後の } までを抜き出して
      3. 末尾の余分なカンマ（"a": 1, } のような形）を落として
    """
    clean = raw.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1]
    if "```" in clean:
        clean = clean.split("```")[0]

    candidates = [clean.strip()]
    m = re.search(r"(\{.*\})", raw, re.DOTALL)
    if m:
        candidates.append(m.group(1))
    # 末尾カンマは LLM が最も出しやすい壊し方。落とすだけで通ることが多い。
    candidates += [re.sub(r",\s*([}\]])", r"\1", c) for c in list(candidates)]

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = _loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


async def _ask_json(prompt: str, *, system: str | None = None, attempts: int = 2) -> dict:
    """LLM に JSON を返させ、パースして返す。

    temperature が 0 ではないため、同じプロンプトでも壊れた JSON が返ることがある
    （実測で 4 回に 1 回程度）。決定的な失敗ではないので、駄目なら引き直す。
    引き直しても駄目なときだけ例外にする。黙って空を返すと、
    「シーンだけ中身が無い動画」が正常終了で出来上がってしまう。
    """
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    last_raw = ""
    for attempt in range(1, attempts + 1):
        last_raw = await chat_completion(messages=messages, provider="local")
        parsed = _parse_json_reply(last_raw)
        if parsed is not None:
            if attempt > 1:
                print(f"[llm] JSON の取得に {attempt} 回目で成功しました")
            return parsed
        print(f"[llm] JSON として読めない応答でした（{attempt}/{attempts} 回目）")

    raise ValueError(
        "LLM が JSON として読める応答を返しませんでした"
        f"（{attempts} 回試行）。応答の先頭: {last_raw.strip()[:200]!r}"
    )


async def generate_scene_content(
    title: str,
    summary: str,
    layout_type: str,
    *,
    aspect: str = "16:9",
    avoid: tuple[str, ...] = (),
    narration_length: str | None = None,
    layout_pinned: bool = False,
    context: str = "",
) -> dict:
    """シーンの内容を生成し、使う見せ方を確定させる。

    段階 2（内容の生成＋見せ方の選択）と段階 3（件数・縦横比・連続の検査と
    自動差し替え）をまとめて行う。呼び出し側はレイアウトの知識を持たなくてよい。
    context は動画全体の中での位置づけ（SceneContext.to_prompt()）。

    戻り値:
        {"layout": …, "slide_content_json": {…}, "narration_text": …, "layout_reason": …}
    """
    type_id = layouts.type_of(layout_type)
    # 見せ方が固定されているときは、候補をその 1 つに絞って渡す。
    # 一覧を全部見せると、LLM が別の見せ方を選んだうえで
    # その件数に合わせた内容を書いてしまい、固定した見せ方に収まらなくなる。
    prompt = _prompts.content_prompt(
        type_id, title, summary, aspect=aspect,
        target_chars=narration_target_chars(narration_length),
        fixed_layout=layout_type if layout_pinned else None,
        context=context,
    )
    parsed = await _ask_json(prompt)

    # slide_content_json を包み忘れて、中身を直に返してくることがある
    raw_content = parsed.get("slide_content_json")
    if not isinstance(raw_content, dict):
        raw_content = {k: v for k, v in parsed.items()
                       if k not in ("narration_text", "layout", "slide_content_json")}

    content = _types.normalize(type_id, raw_content)
    if not content.get("title"):
        content["title"] = title or ""

    # 段階 3: 実データの件数を見て、収まるレイアウトへ寄せる。
    # 固定されているときは LLM の選択を採らない（固定した意味がなくなるため）。
    proposed = layout_type if layout_pinned else (parsed.get("layout") or layout_type)
    resolution = layouts.resolve(
        type_id, content, proposed,
        aspect=aspect, avoid=avoid, pinned=layout_pinned,
    )

    narration = str(parsed.get("narration_text") or "")
    segments = _clean_segments(parsed.get("narration_segments"), narration)

    return {
        "layout": resolution.layout_id,
        "slide_content_json": content,
        "narration_text": narration,
        "narration_segments": segments,
        "layout_reason": resolution.reason,
    }


def _clean_segments(raw, narration: str) -> list[str]:
    """ナレーションの区切りを、本文から切り出し直して返す。

    LLM が返した区切りの文字列をそのまま使わない。連結しても本文にならない
    ことが多いため（実測では 4 回中 3 回、**冒頭の導入文が落ちていた**）。
    そのまま TTS に渡すと、落ちたぶんが読み上げられない動画になる。

    代わりに「各区切りが本文のどこから始まるか」だけを使い、区切りは本文から
    切り出す。こうすると連結は必ず本文と一致する。
      - 先頭に余りがあれば、それを導入として足す
      - 末尾の余りは最後の区切りに含める

    位置が見つからない区切りが 1 つでもあれば、対応づけを諦めて空を返す。
    ずれた区切りで要素を出すと、語られていない項目が先に出てしまう。
    """
    if not isinstance(raw, list) or len(raw) < 2 or not narration:
        return []

    # 空白・改行を除いた索引で照合する。LLM は区切りの前後に空白を入れがち。
    kept, orig_index = [], []
    for i, ch in enumerate(narration):
        if not ch.isspace():
            kept.append(ch)
            orig_index.append(i)
    flat = "".join(kept)

    starts: list[int] = []      # 本文（元の文字列）での開始位置
    cursor = 0
    for seg in raw:
        needle = "".join(str(seg or "").split())
        if not needle:
            continue            # 空の区切り（導入が不要なときなど）は飛ばす
        pos = flat.find(needle, cursor)
        if pos < 0:
            print("[llm] narration_segments が本文に見つからないため使いません")
            return []
        starts.append(orig_index[pos])
        cursor = pos + len(needle)

    if len(starts) < 2:
        return []

    # 先頭の余り（導入）を足してから、開始位置で本文を切り分ける
    bounds = ([0] if starts[0] > 0 else []) + starts
    out = [narration[a:b] for a, b in zip(bounds, bounds[1:])] + [narration[bounds[-1]:]]
    return out


async def generate_image_prompt(title: str, summary: str, layout_type: str,
                                slide_content: dict | None, image_description: str = "") -> dict:
    """外部の画像生成AI に貼り付けるプロンプトを作る。日本語プロンプトと日本語の意図説明を返す。"""
    prompt = f"""あなたは画像生成AI（Gemini / DALL-E / Midjourney 等）向けのプロンプト作成の専門家です。
研修動画のスライドに載せる画像を作るためのプロンプトを作成してください。

スライドタイトル: {title or "無題"}
このシーンのあらすじ: {summary or "（未設定）"}
レイアウト: {layout_type}
スライドに置きたい画像の内容: {image_description or "（指定なし）"}
スライドの内容: {json.dumps(slide_content, ensure_ascii=False) if slide_content else "なし"}

【プロンプトの条件】
- 日本語で書く（Gemini など日本語対応の画像生成AIに貼り付けて使う）
- 被写体・構図・画風・色調・ライティング・雰囲気を具体的に指定する
- 動画スライドの背景／挿絵として使うため、画像内に文字を入れないよう明示する
  （「文字・ロゴ・ウォーターマークは入れない」ことを明記する）
- 横長（16:9）で使うため、横長構図であることと、余白（被写体を中央〜片側に寄せる等）の指定を含める
- 研修資料にふさわしい、落ち着いた品位のある画風にする
- 実在の人物名・商標・特定作品の模倣は指定しない

出力は次のJSONのみ（前置き・解説なし）:
{{"image_prompt": "日本語の画像生成プロンプト", "note": "どんな画像を狙ったかの日本語の補足（40〜80字）"}}"""

    parsed = await _ask_json(prompt)
    return {
        "image_prompt": parsed.get("image_prompt") or "",
        "note": parsed.get("note") or ""
    }


async def generate_bgm_prompt(
    video_title: str,
    scenario_summary: str,
    scenes: list[dict],
    total_duration_sec: float,
    style_info: dict | None = None,
) -> dict:
    """動画のシナリオ・シーン構成・尺・デザインスタイルを理解し、
    動画に合うBGMを作成するための日本語プロンプトを生成する。
    """
    style_info = style_info or {}
    total_min = int(total_duration_sec // 60)
    total_sec_rem = int(total_duration_sec % 60)
    duration_str = f"約{total_min}分{total_sec_rem}秒 ({int(total_duration_sec)}秒)" if total_min > 0 else f"約{int(total_duration_sec)}秒"

    scene_bullets = []
    for s in scenes:
        idx = s.get("index", "?")
        stitle = s.get("title") or "無題"
        ssummary = s.get("summary") or ""
        sdur = s.get("duration_sec", 0)
        scene_bullets.append(f"- Scene {idx}: {stitle}（約{sdur}秒） - {ssummary}")
    scenes_text = "\n".join(scene_bullets) if scene_bullets else "（シーン情報なし）"

    prompt = f"""あなたは映像音楽のサウンドプロデューサーおよび音楽生成AI向けのプロンプト作成の専門家です。
以下の動画のテーマ・シナリオ・シーン展開・想定尺・ビジュアルトーンを理解し、この動画に最も調和するBGMを作成するためのプロンプトを【すべて日本語】で生成してください。

【動画の情報】
- 動画タイトル: {video_title or "無題"}
- シナリオ・あらすじ: {scenario_summary or "（未設定）"}
- 想定総再生時間: {duration_str}
- ビジュアル・トーン:
  - 背景モチーフ: {style_info.get("background_motif") or "grid"}
  - 動きの性格: {style_info.get("motion_character") or "standard"}
  - 装飾スタイル: {style_info.get("decor_style") or "glass"}

【シーン構成】
{scenes_text}

【プロンプト作成の条件】
1. **すべて日本語で記述する**: 英語ではなく日本語でプロンプトを作成してください。
2. **インストゥルメンタル（歌声・ボーカルなし）の明記**: ナレーション動画のBGMとして使用するため、完全インストゥルメンタル（歌声・ボーカル・コーラスなし）であることを明記する。
3. **具体的な音楽要素の指定**: 楽曲スタイル・ジャンル、ムード・雰囲気、テンポ（BPM）、楽器構成（ピアノ、アコースティックギター、シンセパッド等）を具体的に日本語で指定する。
4. **動画の尺と構成展開**: 動画全体の想定尺（{duration_str}）に合わせ、オープニングから展開、結び（フェードアウト）までの展開構成を記載する。
5. **音響的配慮**: 人の声（ナレーション）の聞き取りやすさを最優先し、主音域と衝突しにくい落ち着いた音色や音量バランスを指示する。
6. **狙いと解説**: なぜこの曲調やテンポが動画のシナリオや展開にふさわしいのか、理由を日本語で簡潔に解説する。

出力は次のJSONのみ（前置き・解説なし）:
{{
  "bgm_prompt": "音楽生成AI（Suno / Udio 等）や音楽制作にそのまま使える日本語プロンプト全文（【楽曲スタイル】【テンポ・リズム】【ムード・雰囲気】【楽器構成】【楽曲構成と想定尺】【狙いと解説】などの見出しで整理された日本語テキスト）",
  "description": "BGMの狙い・特徴・動画シナリオとの調和についての簡潔な日本語解説（100〜200文字程度）",
  "recommended_duration": "{duration_str}"
}}"""

    parsed = await _ask_json(prompt)

    bgm_prompt = parsed.get("bgm_prompt") or ""
    description = parsed.get("description") or ""
    rec_duration = parsed.get("recommended_duration") or duration_str

    if not bgm_prompt and description:
        bgm_prompt = f"【BGM作成用プロンプト】\n想定尺: {rec_duration}\n完全インストゥルメンタル（歌声なし）。\n\n【狙いと解説】\n{description}"

    return {
        "bgm_prompt": bgm_prompt,
        "description": description,
        "recommended_duration": rec_duration,
    }


async def generate_narration(
    title: str,
    slide_content: dict | str | None,
    summary: str = "",
    *,
    target_chars: int | None = None,
    context: str = "",
) -> str:
    """スライドの内容に合わせて、ナレーションだけを作り直す。

    「AI でシーン内容を作成」でナレーションだけにチェックを入れたときの経路。
    長さは内容生成と同じ narration_length_rule で伝える。以前はここだけ
    「300〜500文字」の決め打ちで、「短め」を選んでも 70 秒ほどになっていた（#53）。
    """
    # シーンの slide_content_json は JSON 文字列のまま来る。
    # そのまま json.dumps すると、エスケープだらけの 1 本の文字列として渡ってしまう。
    if isinstance(slide_content, str):
        try:
            slide_content = json.loads(slide_content) if slide_content.strip() else None
        except ValueError:
            pass  # 読めなければ文字列のまま渡す（何も無いよりは手がかりになる）
    slide_text = (json.dumps(slide_content, ensure_ascii=False)
                  if isinstance(slide_content, dict) else (slide_content or "なし"))
    context_block = f"\n{context}\n" if context else ""

    prompt = f"""あなたは研修動画のナレーション原稿を書くプロの構成作家です。
以下のスライドに付けるナレーションを書いてください。

スライドタイトル: {title or "無題のシーン"}
このシーンのあらすじ: {summary or "なし"}
スライド内容: {slide_text}
{context_block}
【出力ルール】
- 口語体・丁寧語（です・ます調）で、{narration_length_rule(target_chars)}
- 指定した文字数の目安を必ず守る
- スライドの文言をそのまま読み上げず、スライドを補足して語る
- ナレーションのテキストのみ返す（説明・見出し・JSON 不要）"""

    reply = await chat_completion(messages=[{"role": "user", "content": prompt}], provider="local")
    return reply.strip()


async def suggest_readings(text: str) -> list:
    """ナレーションの中で、TTS が読み間違えやすい語とその読みを LLM に挙げさせる（#60）。

    返すのは LLM の生の一覧。検査（本文にあるか・読みが仮名か）は
    services.reading.clean_ai_readings が行う。
    """
    prompt = f"""あなたは日本語ナレーションの読み上げ原稿を校正する専門家です。
次のナレーションを音声合成で読み上げます。音声合成が**読み間違えやすい語**だけを挙げ、
正しい読みをひらがなで書いてください。

【挙げる語】
- 固有名詞（人名・地名・作品名・製品名・組織名）
- 難読語、複数の読み方がある語（例: 「上手」「分別」「生物」）で、文脈から読みが決まるもの
- 数字と単位・記号の組み合わせで、読み方に迷うもの（例: 「3階」「1〜2名」）
- アルファベットの略語で、読み方が決まっているもの（例: 「AI」→「えーあい」）

【挙げない語】
- 誰でも普通に読める一般的な語（挙げすぎると確認の手間が増えるだけ）
- すでにひらがな・カタカナだけで書かれている語

【書き方】
- surface にはナレーションに**書かれているとおりの表記**を、そのまま抜き出す（言い換えない）
- reading はひらがなだけで書く（漢字・記号・括弧を混ぜない）
- 該当する語が無ければ空の配列にする

ナレーション:
---
{text}
---

出力は次の形の JSON のみ（前置き・解説なし）:
{{"readings": [{{"surface": "表記", "reading": "よみ"}}]}}"""
    parsed = await _ask_json(prompt)
    return parsed.get("readings") or []


def _format_options(options: list[dict]) -> str:
    """LLM に見せる選択肢の一覧を「値: 説明」の箇条書きにする。"""
    return "\n".join(f'  - "{o["value"]}": {o["description"]}' for o in options)


async def apply_style_prompt(current_style_dict: dict, style_prompt: str) -> dict:
    """現在のスタイルに指示プロンプトを適用して新しいデザイン設定一式を生成する。

    配色だけを返させると「和風にして」の指示に対して色だけ変わり、背景は
    グリッド・カードはグラスのまま、という嚙み合わない結果になる。
    そのため背景モチーフ・装飾スタイル・組版・切替まで一括で選ばせる。
    選択肢は design_tokens.py から流し込み、プロンプト内に値を直書きしない。
    """
    from services.design_tokens import (
        BACKGROUND_MOTIFS,
        DECOR_STYLES,
        DEFAULTS,
        FONT_CHOICES,
        TRANSITIONS,
        TYPE_SCALES,
    )

    font_list = "\n".join(f'  - "{o["value"]}": {o["description"]}' for o in FONT_CHOICES)

    prompt_text = f"""あなたはクリエイティブなフロントエンドデザイナーです。
ユーザーから「研修動画のデザイン指示」を受け取り、それに合わせたデザイン設定一式を提案してください。

**配色の条件:**
- color_primary, color_secondary, color_accent, color_bg, color_text_primary を16進数カラーコード（例: #ffffff）で返してください。
- color_bg と color_text_primary のコントラスト比を必ず 7:1 以上確保してください。ここが不足すると本文が読めなくなります。
- 背景を明るくする場合は文字色を必ず濃くしてください（逆も同様）。

**フォント（この一覧の値をそのまま使うこと。他の名前は使用不可）:**
{font_list}

**背景モチーフ background_motif（この一覧の値のみ）:**
{_format_options(BACKGROUND_MOTIFS)}

**装飾スタイル decor_style（この一覧の値のみ）:**
{_format_options(DECOR_STYLES)}

**組版 type_scale（この一覧の値のみ）:**
{_format_options(TYPE_SCALES)}

**シーン切替 transition（この一覧の値のみ）:**
{_format_options(TRANSITIONS)}

**出力形式:**
前置きや解説は一切出力せず、以下の JSON のみを出力してください。

{{
  "color_primary": "メインカラー",
  "color_secondary": "サブカラー",
  "color_accent": "アクセントカラー",
  "color_bg": "背景カラー",
  "color_text_primary": "テキストカラー",
  "font_heading": "見出しフォント名",
  "font_body": "本文フォント名",
  "background_motif": "背景モチーフの値",
  "decor_style": "装飾スタイルの値",
  "type_scale": "組版の値",
  "transition": "シーン切替の値"
}}

現在の設定:
- color_primary: {current_style_dict.get("color_primary") or DEFAULTS["color_primary"]}
- color_bg: {current_style_dict.get("color_bg") or DEFAULTS["color_bg"]}
- color_text_primary: {current_style_dict.get("color_text_primary") or DEFAULTS["color_text_primary"]}
- background_motif: {current_style_dict.get("background_motif") or DEFAULTS["background_motif"]}
- decor_style: {current_style_dict.get("decor_style") or DEFAULTS["decor_style"]}

デザイン指示: {style_prompt}"""

    return await _ask_json(prompt_text)


async def decide_types_for_slides(
    slides: list[dict],
    breadth: str | None = None,
) -> dict[int, str]:
    """PPTX の複数スライドについて、内容の型をまとめて 1 回で決める。

    slides は [{"index": 1, "title": "…", "bullets": ["…"], "body": "…"}, …]。
    戻り値は {スライド番号: 型 id}。決められなかったものは入らない。

    1 スライド 1 回ではなく全部まとめて聞くのは 2 つの理由から。
      - 24 スライドで 24 回呼ぶと数分かかる
      - 前後の文脈が見えるので「同じ型が延々続く」のを避けられる

    型を取り違えても動画生成は止まらない（呼び出し側が既定へ落とす）ため、
    失敗しても例外にせず空の辞書を返す。
    """
    if not slides:
        return {}

    lines = []
    for s in slides:
        bullets = s.get("bullets") or []
        parts = [f'{s["index"]}. 「{s.get("title") or "無題"}」']
        if bullets:
            parts.append("  箇条書き: " + " / ".join(b[:40] for b in bullets[:6]))
        body = (s.get("body") or "").strip()
        if body:
            parts.append(f"  本文: {body[:120]}")
        lines.append("\n".join(parts))

    prompt = f"""あなたは研修動画の構成を作るプロです。
PowerPoint から取り込んだスライドを 1 枚ずつ読み、それぞれ「情報の型」を選んでください。

**型の一覧:**
{_prompts.type_menu(layouts.allowed_types(breadth))}

**スライド:**
{chr(10).join(lines)}

**判断のしかた:**
- 箇条書きの数ではなく、**項目どうしの関係**で決めてください。
  順番に意味があるなら順序、上下関係があるなら階層、回り続けるなら循環です。
- 同じ型が 3 枚以上続かないようにしてください。ただし内容に合わない型を
  無理に混ぜないでください。

**出力形式:**
次の JSON のみを出力してください。前置き・解説は不要です。
{{"types": [{{"index": 1, "content_type": "型の値"}}, …]}}"""

    try:
        parsed = await _ask_json(prompt)
    except Exception as e:  # noqa: BLE001
        print(f"[pptx] 型の判定に失敗しました（既定のまま進めます）: {e}")
        return {}

    out: dict[int, str] = {}
    for item in parsed.get("types") or []:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        tid = str(item.get("content_type") or "").strip()
        if tid in _types.CONTENT_TYPES:
            out[idx] = tid
    return out


async def generate_slide_narration(
    slide_title: str,
    bullets: list[str],
    table_summary: str,
    visual_summary: str,
    notes: str,
    prev_title: str,
    *,
    target_chars: int | None = None,
    is_first: bool = False,
) -> str:
    """PPTX の1スライド分の情報からナレーション文（プレーンテキスト）を生成する。

    ノートがあればそれを土台に整えるだけにし、無ければ他の情報から新規生成する。
    JSON を使わずプレーンテキストで受け取ることで、パース失敗の余地を無くす。

    target_chars … 新規生成するときの目安の文字数（動画の既定の長さ）。
                   ノートを整えるときは使わない（書き手の分量を尊重する）。
    is_first     … 動画の 1 枚目か。挨拶を許すのは 1 枚目だけ。
    """
    bullets_text = "\n".join(f"- {b}" for b in bullets) if bullets else "（なし）"
    context_lines = [
        f"スライドタイトル: {slide_title or '（無題）'}",
        f"箇条書き:\n{bullets_text}",
    ]
    if table_summary:
        context_lines.append(f"表の内容: {table_summary}")
    if visual_summary:
        context_lines.append(f"画像・図解の内容: {visual_summary}")
    if prev_title:
        context_lines.append(f"直前のスライドのタイトル: {prev_title}（話の接続を自然にすること）")
    context = "\n".join(context_lines)

    if notes and len(notes.strip()) >= 20:
        prompt = f"""以下は研修動画のスライドに付いている「発表者ノート」です。
内容や意味を変えずに、動画のナレーションとして自然に読み上げられる、丁寧語（です・ます調）の文章に整えてください。

【発表者ノート】
{notes}

【スライド情報（参考）】
{context}

【出力ルール】
- 前置き・見出し・箇条書き記号（-, ・, 1. など）は一切付けない
- 整えた本文だけをプレーンテキストで出力する
- ノートに無い情報を新たに付け加えない"""
    else:
        opening_rule = (
            "- 動画の冒頭のスライドなので、挨拶と動画全体の導入から始めてよい"
            if is_first else
            "- 動画の途中のスライドなので、「こんにちは」などの挨拶や動画全体の導入は入れない。"
            "直前のスライドから続けて話すように始める"
        )
        prompt = f"""あなたは研修動画のナレーション原稿を書くプロの構成作家です。
以下のスライド情報をもとに、丁寧語（です・ます調）のナレーション原稿を書いてください。
長さは{narration_length_rule(target_chars)}です。

【スライド情報】
{context}

【出力ルール】
- 前置き・見出し・箇条書き記号（-, ・, 1. など）は一切付けない
- ナレーション本文だけをプレーンテキストで出力する
- スライドの文言をそのまま読み上げず、内容を補足しながら語る
- 指定した文字数の目安を必ず守る
{opening_rule}"""

    raw = await chat_completion(messages=[{"role": "user", "content": prompt}], provider="local")
    text = raw.strip()
    # 先頭に付きがちな "ナレーション:" 等のラベル行や Markdown 記号を除去
    text = re.sub(r"^(ナレーション|narration)\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```[a-z]*\n?|```$", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"^[-・*]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


# ---- 貼り付けテキストの見積もり -------------------------------------------
# いずれも実測値。画面側はこれを /scenario/paste-limits 経由で受け取る。
TOKENS_PER_CHAR_JA = 0.60     # 日本語の 1 文字あたりのトークン数
PROMPT_TOKENS_PER_SEC = 1190  # プロンプトの前処理速度

# 貼り付けを受け付ける上限。LM Studio 側のコンテキスト（既定 262,144）を
# 本当に超える水準だけを弾く。研修資料を丸ごと貼る使い方を残したいので、
# 「長いと遅い」は画面側の目安表示で伝え、ここでは拒否しない。
#
# 20 万字 ≒ 12 万トークン。テンプレートと出力の余地を差し引いても、
# これを超えるならコンテキスト設定を下げている環境で確実に破綻する。
MAX_PASTE_CHARS = 200_000


async def split_text_to_scenes(text: str, breadth: str | None = None) -> str:
    """プレーンテキストからシーン分割提案の生の応答を生成する。

    作るのは章立て（タイトル・あらすじ・情報の型）だけ。
    スライドの中身は後工程（generate_scene_content）で型ごとに深掘りする。
    """
    if len(text) > MAX_PASTE_CHARS:
        # ここで弾かないと、LLM 側のコンテキスト超過が
        # 「ローカル LLM の呼び出しに失敗しました」としか出ず原因が分からない。
        raise ValueError(
            f"貼り付けたテキストが長すぎます（{len(text):,} 文字）。"
            f"{MAX_PASTE_CHARS:,} 文字以下に分けてから実行してください。"
        )

    prompt = (PROMPT_B_TEMPLATE
              .replace("{{type_menu}}", _prompts.type_menu(layouts.allowed_types(breadth)))
              .replace("{{pasted_text}}", text))
    try:
        llm_response = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたは動画シナリオを生成するアシスタントです。"
                        "ユーザーの指示に従い、指定された JSON フォーマットのみを返してください。"
                        "前置き・解説・マークダウンのコードブロック以外のテキストは出力しないでください。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            provider="local"
        )
        return llm_response
    except Exception as e:
        raise RuntimeError(f"LLM 呼び出しに失敗しました: {e}")


async def send_chat_message(messages: list[dict]) -> str:
    """AIチャット（壁打ち）の返答を生成する"""
    return await chat_completion(messages=messages, provider="local")


SCENE_HTML_GROUNDING_PROMPT = """あなたは HyperFrames という動画レンダリングフレームワーク向けに、
1つのスライド（シーン）の HTML/CSS 断片を編集するアシスタントです。
以下のルールを厳密に守ってください。

【出力対象】
1つのスライドの中身の断片のみを返します。<html>/<head>/<body>、
data-composition-id を持つルート要素、GSAP のタイムライン登録スクリプト
（window.__timelines への登録）は含めないでください
（このアプリでは全シーン共通のアニメーション制御スクリプトが既に1つ用意されているため不要です）。

【必須ルール】
- 利用できる既製クラス: slide-eyebrow / slide-title / slide-body-area / body-card / body-text /
  bullet-list / bullet-item / bullet-num / bullet-content / card-grid(.cols-2|.cols-3) /
  info-card / info-card-index / info-card-title / info-card-text /
  comparison-cols / comparison-col(.left|.right) / comparison-col-head / comparison-vs /
  section-title / section-rule / section-subtitle / data-table / deco-orb(.deco-orb-1|.deco-orb-2)
  → まずこれらの組み合わせで構成し、必要な差分だけ style 属性や css で足すこと。
- アニメーション・表示制御の対象にしたい要素には必ず class="clip" を付与する
- class="clip" を持つ要素には data-start（スライド内の相対開始秒）と
  data-duration（表示継続秒）を必ず付与する（スライド全体の開始時刻ではなく相対値でよい）
- 複数のカードや箇条書きを出すときは、要素ごとに data-start を 0.2〜0.3 秒ずつずらして
  順番に登場させること（一斉に出さない）
- レイヤーの重なり順を変えたい場合のみ data-track-index を使う（省略可。大きいほど手前）
- React 等のフレームワークは使わず、プレーンな HTML/CSS のみ。<script> は
  グラフ描画（Chart.js。既にページ全体で読み込み済み）以外の用途では使わないこと
- 独自CSSを追加する場合、セレクタは必ず指定された scene_dom_id 配下にスコープすること
  （他のシーンに影響を与えないため）
- 「(中略)」「...は省略」等の不完全な出力は禁止
- 前置き・説明文なしで、指定したJSON形式のみを返すこと

【よくあるミス】
- class="clip" を付け忘れる → 要素が表示されない
- data-start/data-duration を付け忘れる → タイミング制御ができない
- 独自に <script> でタイムラインを再登録してしまう → 既存の制御と衝突するため不要

【Few-shot例】
例1: 本文をカードで見せる（text_only）
指示: 本文が味気ないので、カードで見せて装飾を足してください

出力:
{"html": "<div class=\"deco-orb deco-orb-1\"></div>\n<div class=\"clip slide-eyebrow\" data-start=\"0.50\" data-duration=\"9.50\">Scene 03</div>\n<h1 class=\"clip slide-title\" data-start=\"0.65\" data-duration=\"9.35\">なぜ今、縄文なのか？</h1>\n<div class=\"slide-body-area\">\n  <div class=\"clip body-card\" data-start=\"0.95\" data-duration=\"9.05\">\n    <p class=\"body-text\">持続可能な資源利用や多様な定住形態が、現代の環境・社会課題にどのような示唆を与えるかを論じます。</p>\n  </div>\n</div>", "css": ""}

例2: 箇条書きを番号バッジ付きカードにして順番に出す（bullet_list）
指示: 箇条書きをカードにして、順番に出てくるようにしてください

出力:
{"html": "<div class=\"deco-orb deco-orb-2\"></div>\n<div class=\"clip slide-eyebrow\" data-start=\"0.50\" data-duration=\"9.50\">Key Points</div>\n<h1 class=\"clip slide-title\" data-start=\"0.65\" data-duration=\"9.35\">衰退説の再検討</h1>\n<div class=\"slide-body-area\">\n  <div class=\"bullet-list\">\n    <div class=\"clip bullet-item\" data-start=\"0.95\" data-duration=\"9.05\"><div class=\"bullet-num\">1</div><div class=\"bullet-content\"><p>寒冷化と人口減少の時期は必ずしも一致していない</p></div></div>\n    <div class=\"clip bullet-item\" data-start=\"1.20\" data-duration=\"8.80\"><div class=\"bullet-num\">2</div><div class=\"bullet-content\"><p>地域ごとに異なる適応戦略が確認されている</p></div></div>\n    <div class=\"clip bullet-item\" data-start=\"1.45\" data-duration=\"8.55\"><div class=\"bullet-num\">3</div><div class=\"bullet-content\"><p>単一要因ではなく複合的な社会変動として捉える</p></div></div>\n  </div>\n</div>", "css": ""}

例3: 3つのトピックをカードグリッドで並べる（card_panel）
指示: 3つの手法をカードで横に並べて見せてください

出力:
{"html": "<div class=\"deco-orb deco-orb-1\"></div>\n<div class=\"clip slide-eyebrow\" data-start=\"0.50\" data-duration=\"9.50\">Methods</div>\n<h1 class=\"clip slide-title\" data-start=\"0.65\" data-duration=\"9.35\">現代考古学の手法</h1>\n<div class=\"slide-body-area\">\n  <div class=\"card-grid cols-3\">\n    <div class=\"clip info-card\" data-start=\"0.95\" data-duration=\"9.05\"><div class=\"info-card-index\">01</div><div class=\"info-card-title\">年代測定</div><p class=\"info-card-text\">放射性炭素年代測定により、遺物の年代を高精度で特定します。</p></div>\n    <div class=\"clip info-card\" data-start=\"1.20\" data-duration=\"8.80\"><div class=\"info-card-index\">02</div><div class=\"info-card-title\">残留物分析</div><p class=\"info-card-text\">土器に残る有機物から、当時の食生活を科学的に復元します。</p></div>\n    <div class=\"clip info-card\" data-start=\"1.45\" data-duration=\"8.55\"><div class=\"info-card-index\">03</div><div class=\"info-card-title\">同位体分析</div><p class=\"info-card-text\">人骨の同位体比から、移動経路や食性の変化を追跡します。</p></div>\n  </div>\n</div>", "css": ""}
"""


async def ai_adjust_scene_design(current_html: str, current_css: str, instruction: str, scene_dom_id: str, style_vars: dict) -> dict:
    """シーン単位のAIデザイン調整。"""
    user_prompt = f"""このシーンの scene_dom_id は "{scene_dom_id}" です。
現在のスタイル変数（配色）: {json.dumps(style_vars, ensure_ascii=False)}

現在のHTML断片:
```html
{current_html}
```

現在のカスタムCSS（未設定なら空）:
```css
{current_css}
```

ユーザーからの調整指示: {instruction}

上記のルールに従い、更新後のHTML断片とCSSを次のJSON形式のみで返してください。
{{"html": "...", "css": "..."}}
"""
    parsed = await _ask_json(user_prompt, system=SCENE_HTML_GROUNDING_PROMPT)
    # 以前は読み取れないと元の HTML をそのまま返しており、「調整した」ことになって
    # 何も変わらなかった。html が無ければ失敗として知らせる
    if not parsed.get("html"):
        raise ValueError("AI の応答に html がありませんでした")
    return {
        "html": parsed["html"],
        "css": parsed.get("css") if parsed.get("css") is not None else current_css,
    }
