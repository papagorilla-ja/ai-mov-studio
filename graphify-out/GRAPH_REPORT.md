# Graph Report - ai-mov-gen  (2026-09-24)

## Corpus Check
- 155 files · ~835,184 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 62 file(s) not represented in the graph (top: .css 51, (none) 7, .woff2 2)

## Summary
- 1508 nodes · 3179 edges · 100 communities (75 shown, 25 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 257 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bfdeb3a7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- llm_service.py
- VideoEditorView.vue
- projects.py
- run_generation
- tts_service.py
- design_tokens.py
- _registry.py
- routers/scenario.py
- Scenario
- StyleConfigTab.vue
- server.py
- styles.py
- videos.py
- ScenarioRouteC.vue
- scenes.py
- pptx_import.py
- SettingsView.vue
- settings_router.py
- normalize
- SceneAssetSlot.vue
- ScenarioRouteB.vue
- decide_types_for_slides
- HomeView.vue
- schemas/__init__.py
- bg3d.js
- app.js
- _types.py
- _to_response
- applyStageClasses
- renderer.py
- package.json
- api/index.js
- schemas/scene.py
- ProjectView.vue
- generate_composition
- composition.py
- style-groups/index.js
- style.py
- ConnectionManager
- start.sh
- dependencies
- voice_corpus.py
- main.js
- SceneContentForm.vue
- LayoutPicker.vue
- renderer_server.py
- _set_sqlite_pragmas
- _run_preview_synthesis
- synthesize_scene_audio
- VoiceRecording
- lowContrast
- thumbVars
- config.py
- session_record
- audio_utils.py
- _prompts.py
- ScenarioRouteA.vue
- speakers.py
- schemas/speaker.py
- selectScene
- vue
- _field_dict
- normalize_narration_length
- get
- _ask_json
- devDependencies
- scripts
- chart_scale/spec.py
- .distance
- releaseStream
- AvatarPicker.vue
- resetTake
- stop.sh
- registry
- Path
- loadSpeakers
- finalizeSession
- hierarchy_funnel/spec.py
- hierarchy_pyramid/spec.py
- matrix_plot/spec.py
- new_project.sh
- chart_ranking/spec.py
- dialog_qa/spec.py
- hierarchy_nested/spec.py
- hierarchy_tree/spec.py
- sets_inclusion/spec.py
- table_matrix/spec.py
- table_pricing/spec.py
- modeLabel
- AI-MovGen — 研修動画の自動生成ツール
- routers/generation.py
- ナレーション原稿
- CLAUDE.md
- ref_mdi_font_css_materialdesignicons_css
- ref_vuetify_components
- ref_vuetify_directives
- ref_vuetify_styles

## God Nodes (most connected - your core abstractions)
1. `LayoutSpec` - 62 edges
2. `Scene` - 56 edges
3. `get()` - 48 edges
4. `Capacity` - 44 edges
5. `Video` - 42 edges
6. `VideoStyle` - 34 edges
7. `Scenario` - 33 edges
8. `run_generation()` - 30 edges
9. `Project` - 27 edges
10. `Base` - 24 edges

## Surprising Connections (you probably didn't know these)
- `書体が指定と違う` --references--> `find_missing_css_refs()`  [INFERRED]
  README.md → webapp/backend/services/composition.py
- `動画が静止画になる / アニメーションが効かない` --references--> `find_missing_local_refs()`  [INFERRED]
  README.md → webapp/backend/services/composition.py
- `list_models()` --references--> `get()`  [EXTRACTED]
  qwen3-tts/server.py → webapp/backend/layouts/_registry.py
- `useProjectsStore` --indirect_call--> `create()`  [INFERRED]
  webapp/frontend/src/stores/projects.js → templates/blank/bg3d.js
- `useVideosStore` --indirect_call--> `create()`  [INFERRED]
  webapp/frontend/src/stores/videos.js → templates/blank/bg3d.js

## Import Cycles
- None detected.

## Communities (100 total, 25 thin omitted)

### Community 0 - "llm_service.py"
Cohesion: 0.13
Nodes (22): httpx, re, chat_completion(), ローカル LLM（OpenAI 互換 API）に問い合わせ、応答テキストを返す。, ai_adjust_scene_design(), apply_style_prompt(), _clean_segments(), extract_outline_proposal() (+14 more)

### Community 1 - "VideoEditorView.vue"
Cohesion: 0.02
Nodes (83): webapp_frontend_src_assets_btn_bulk_generate_bg, webapp_frontend_src_assets_btn_generate_scene, webapp_frontend_src_assets_card_basic_info_bg, activeTab, applyingDesign, assetSlotCount, bulkGenConfirmDialog, bulkGenOnlyEmpty (+75 more)

### Community 2 - "projects.py"
Cohesion: 0.09
Nodes (26): contextlib, FastAPI, fastapi_middleware_cors, fastapi_responses, fastapi_staticfiles, json, pathlib, shutil (+18 more)

### Community 3 - "run_generation"
Cohesion: 0.11
Nodes (24): レンダリング中に見せる「音声なしの下見」を別ディレクトリに固める。 出力先をそのままブラウザに見せない理由: 分割レンダリングは…, write_preview_snapshot(), compute_tts_hash(), ensure_tts_ready(), TTS サーバーが合成可能な状態かを確認し、駄目なら理由を明示して例外を送出する。 既存音声の削除など、失敗すると後戻りできない処理の前に必ず呼ぶこと。…, TTS用のキャッシュ判定ハッシュを算出する, get_wav_duration(), _narration_segments() (+16 more)

### Community 4 - "tts_service.py"
Cohesion: 0.18
Nodes (13): hashlib, unicodedata, wave, _build_items(), _max_chunk_chars(), normalize_for_tts(), シーンのナレーションを Qwen3-TTS で音声化するサービス。 ■ 処理の流れ（これだけ） 1. ナレーション本文を TTS…, TTS に渡す前の軽量な正規化。読み上げに不要な表記ゆれを潰す。 (+5 more)

### Community 5 - "design_tokens.py"
Cohesion: 0.13
Nodes (25): _prepare(), Chart.js の描画スクリプトを組み立てる。 canvas は CSS 変数を解釈できないため、テーマから導出した確定色を JS…, build_theme_css(), _chars_for_seconds(), chart_palette(), contrast_ratio(), ensure_contrast(), font_stack() (+17 more)

### Community 6 - "_registry.py"
Cohesion: 0.10
Nodes (6): collections_abc, importlib, Capacity, LayoutSpec, レイアウト（見せ方）の登録・検索・自動差し替え。 1 レイアウト = 1 ディレクトリ。 layouts/sequence_horizontal/…, このレイアウトが何件まで綺麗に収まるか。 ideal は「最も収まりが良い件数の範囲」。min/max は「破綻しない範囲」。…

### Community 7 - "routers/scenario.py"
Cohesion: 0.13
Nodes (29): _blocks_to_scenes(), chat(), finalize_scenario(), from_pptx(), from_text(), get_layout_breadth(), get_scenario(), _normalize_layout() (+21 more)

### Community 8 - "Scenario"
Cohesion: 0.23
Nodes (18): get_project_dir(), get_project_dir_name(), Path, 後方互換を考慮してプロジェクトのディレクトリ名（フォルダ名）を取得する。 1. UUID ディレクトリが存在すれば UUID (project.id)…, Scenario, SceneAsset, delete_asset(), list_assets() (+10 more)

### Community 9 - "StyleConfigTab.vue"
Cohesion: 0.06
Nodes (31): applyingPrompt, aspectPreset, bgmDeleting, bgmFile, bgmUploading, breadthValue, colorsList, currentBgmName (+23 more)

### Community 10 - "server.py"
Cohesion: 0.06
Nodes (51): gc, cap_new_tokens(), device_memory_mb(), _effective_ref_path(), estimate_duration_sec(), _free_device_cache(), gap_after(), _generate_batch() (+43 more)

### Community 11 - "styles.py"
Cohesion: 0.15
Nodes (22): normalize_breadth(), UI / LLM から来た値を許可された「レイアウトの幅」に丸める。 None はそのまま返す（＝未設定。DEFAULT_BREADTH が使われる）。…, StyleTemplate, create_style_template(), delete_style_template(), get_style_options(), list_style_templates(), delete (+14 more)

### Community 12 - "videos.py"
Cohesion: 0.15
Nodes (31): Project, VideoStyle, Video, delete_project(), export_project(), get_project(), import_project(), list_projects() (+23 more)

### Community 13 - "ScenarioRouteC.vue"
Cohesion: 0.15
Nodes (10): chatContainer, emit, filteredMessages, finalize(), finalizing, inputMsg, props, scenarioStore (+2 more)

### Community 14 - "scenes.py"
Cohesion: 0.16
Nodes (32): Scene, ai_design_adjust(), apply_generated_content(), create_scene(), delete_scene(), _effective_narration_length(), generate_image_prompt(), generate_narration() (+24 more)

### Community 15 - "pptx_import.py"
Cohesion: 0.08
Nodes (39): build_outline(), emu_to_px(), extract_shape(), extract_slide(), extract_text_frame(), main(), PPTXファイルを解析し、各スライドの構成(タイトル/本文/ノート/画像有無など)を 構造化されたアウトライン(JSON +…, EMU(English Metric Units)をおおよそのピクセル値に変換する。 (+31 more)

### Community 16 - "SettingsView.vue"
Cohesion: 0.05
Nodes (36): addDialog, addForm, adding, audioBlob, audioChunks, audioUrl, canvasRef, chunkOptions (+28 more)

### Community 17 - "settings_router.py"
Cohesion: 0.24
Nodes (12): _build_schema(), _db_load(), _db_save(), get_settings(), AsyncSession, patch, app_settings テーブルからすべての設定を辞書として返す。, キーバリューを upsert（INSERT OR REPLACE）する。 (+4 more)

### Community 18 - "normalize"
Cohesion: 0.12
Nodes (18): normalize(), 任意の dict を型のスキーマに丸める。 routers/scenes.py の normalize_slide_content() を置き換えるもの。…, aspect_of(), narration_segment_starts(), 1 シーン分の HTML 断片を (レイアウト, HTML) で返す。, ナレーションの区切りが始まる秒数。無ければ None。 音声合成が済んだシーンにだけ入る。プレビューや取り込み直後は…, レイアウト選択ギャラリーのサムネイル用に、サンプル内容で描画する。 サムネイル画像を手で用意せず、実際のレイアウトビルダーに流して実物を作る。…, レイアウトのサムネイルを iframe に流し込むための、完結した HTML 文書。 スライドの CSS は :root や #stage… (+10 more)

### Community 19 - "SceneAssetSlot.vue"
Cohesion: 0.07
Nodes (31): activeSlot, assets, configForm, deleteAsset(), dragOverSlot, effectiveSlotCount, emit, fetchAssets() (+23 more)

### Community 20 - "ScenarioRouteB.vue"
Cohesion: 0.17
Nodes (11): charCount, emit, estimateLabel, finalize(), limits, previewScenes, props, scenarioStore (+3 more)

### Community 21 - "decide_types_for_slides"
Cohesion: 0.28
Nodes (9): 「この内容はどの型か」を選ばせるための一覧。 description（何の型か）だけでなく when_to_use（どんなときに選ぶか／…, type_menu(), allowed_types(), チャットのシステムプロンプト。使える型は動画の「レイアウトの幅」設定で絞る。, system_prompt_c(), decide_types_for_slides(), PPTX の複数スライドについて、内容の型をまとめて 1 回で決める。 slides は [{"index": 1, "title": "…",…, プレーンテキストからシーン分割提案の生の応答を生成する。 作るのは章立て（タイトル・あらすじ・情報の型）だけ。… (+1 more)

### Community 22 - "HomeView.vue"
Cohesion: 0.06
Nodes (24): webapp_frontend_src_assets_btn_import_zip, webapp_frontend_src_assets_btn_new_project, webapp_frontend_src_assets_btn_select_mode, webapp_frontend_src_assets_empty_projects_art, webapp_frontend_src_assets_hero_banner_art, bulkDeleteDialog, bulkDeleting, deleteDialog (+16 more)

### Community 23 - "schemas/__init__.py"
Cohesion: 0.15
Nodes (19): pydantic, create_project(), post, DisplayConfig, DisplayConfigUpdate, BaseModel, GenerationHistoryRead, GenerationStatus (+11 more)

### Community 24 - "bg3d.js"
Cohesion: 0.21
Nodes (11): buildOrbitRings(), buildParticles(), create(), makeRng(), seedFrom(), useScenesStore, applyDesignAdjust(), applySceneCode() (+3 more)

### Community 25 - "app.js"
Cohesion: 0.07
Nodes (24): ANIMS, autoFitAll(), bg3dId, clips, countUpTexts, dashboardPreview, EXITS, fitBox() (+16 more)

### Community 26 - "_types.py"
Cohesion: 0.05
Nodes (50): dataclasses, coerce_type(), 型を「レイアウトの幅」設定の範囲内に寄せる。, type_of(), _as_list(), _coerce_group(), _coerce_items(), _coerce_tree() (+42 more)

### Community 27 - "_to_response"
Cohesion: 0.26
Nodes (13): apply_style_prompt(), apply_style_template(), _apply_updates(), _get_or_create_style(), get_video_style(), AsyncSession, patch, post (+5 more)

### Community 28 - "applyStageClasses"
Cohesion: 0.32
Nodes (12): applyAiPrompt(), applyStageClasses(), applyStyleToForm(), buildPayload(), commitSave(), injectCustomCss(), injectThemeCss(), onPreviewLoaded() (+4 more)

### Community 29 - "renderer.py"
Cohesion: 0.32
Nodes (11): datetime, DeclarativeBase, sqlalchemy, sqlalchemy_orm, traceback, uuid, Base, SQLAlchemy async エンジン + セッション管理 (+3 more)

### Community 30 - "package.json"
Cohesion: 0.20
Nodes (10): axios, ref_node_url, vite, vite-plugin-vuetify, @vitejs/plugin-vue, vue-router, vuedraggable, name (+2 more)

### Community 31 - "api/index.js"
Cohesion: 0.17
Nodes (12): api, DEFAULT_TIMEOUT, errorHandler(), formatDetail(), LONG_TIMEOUT, longApi, layoutApi, scenarioApi (+4 more)

### Community 32 - "schemas/scene.py"
Cohesion: 0.31
Nodes (9): patch, update_scene(), AiDesignAdjustRequest, BaseModel, SceneBase, SceneCreate, SceneRead, SceneReorder (+1 more)

### Community 33 - "ProjectView.vue"
Cohesion: 0.13
Nodes (9): webapp_frontend_src_assets_card_thumb_default, webapp_frontend_src_assets_empty_videos_art, deleteDialog, newVideo, newVideoDialog, projectStore, route, videoStore (+1 more)

### Community 34 - "generate_composition"
Cohesion: 0.12
Nodes (20): hyperframes が見つからない, トラブルシューティング, 動画が静止画になる / アニメーションが効かない, 書体が指定と違う, 音声合成の途中で "Server disconnected" になる, _asset_to_html(), find_missing_css_refs(), find_missing_local_refs() (+12 more)

### Community 35 - "composition.py"
Cohesion: 0.10
Nodes (24): bs4, Environment, jinja2, markupsafe, icon_names(), icon_svg(), レイアウトで使うアイコン — 自作の幾何アイコン。 方針: 24×24 グリッド / stroke-width 2 / 丸端・丸継ぎ / fill なし…, 日本語キーを実在するアイコン名に解決する。未知なら None。 (+16 more)

### Community 36 - "style-groups/index.js"
Cohesion: 0.22
Nodes (8): webapp_frontend_src_assets_style_groups_background, webapp_frontend_src_assets_style_groups_basic, webapp_frontend_src_assets_style_groups_colors_typography, getStyleGroupIcon(), STYLE_GROUP_ICONS, webapp_frontend_src_assets_style_groups_motion_sound, webapp_frontend_src_assets_style_groups_presentation, getGroupIconStyle()

### Community 37 - "style.py"
Cohesion: 0.43
Nodes (7): ApplyPromptRequest, BaseModel, StyleTemplateBase, StyleTemplateCreate, StyleTemplateRead, VideoStyleRead, VideoStyleUpdate

### Community 38 - "ConnectionManager"
Cohesion: 0.33
Nodes (3): ConnectionManager, websocket_endpoint(), WebSocket

### Community 39 - "start.sh"
Cohesion: 0.12
Nodes (20): check_venv(), err(), HF_HOME, log(), MODEL_CACHE_DIR, NVM_DIR, PATH, PROJECTS_DIR_HOST (+12 more)

### Community 40 - "dependencies"
Cohesion: 0.25
Nodes (8): dependencies, axios, @mdi/font, pinia, vue, vue-router, vuedraggable, vuetify

### Community 41 - "voice_corpus.py"
Cohesion: 0.33
Nodes (6): random, build_session_items(), _pick(), 音声収集セッションで提示する文章（固定コーパス）。 以前は開始時にローカル LLM で読み上げ文を生成していたが、 35B クラスのモデルでは 5 文で約…, 収録モードに応じて、画面に提示する項目のリストを作る。 返す各項目: index … 1 始まりの通し番号 prompt ……, 先頭から順に採用し、要求数がコーパスを超える場合はシャッフルして補充する。 先頭優先にすることで、少ない収録数でも音のバランスが良い文が確実に含まれる。

### Community 42 - "main.js"
Cohesion: 0.33
Nodes (5): @mdi/font, vuetify, vuetify, router, routes

### Community 43 - "SceneContentForm.vue"
Cohesion: 0.12
Nodes (13): emit, nodes, props, addItem(), chart, chartTypes, content, listValue() (+5 more)

### Community 44 - "LayoutPicker.vue"
Cohesion: 0.06
Nodes (28): webapp_frontend_src_assets_layout_types_chart, webapp_frontend_src_assets_layout_types_contrast, webapp_frontend_src_assets_layout_types_cover, webapp_frontend_src_assets_layout_types_cycle, webapp_frontend_src_assets_layout_types_default, webapp_frontend_src_assets_layout_types_dialog, webapp_frontend_src_assets_layout_types_formula, webapp_frontend_src_assets_layout_types_hierarchy (+20 more)

### Community 45 - "renderer_server.py"
Cohesion: 0.15
Nodes (18): asyncio, find_ffmpeg(), find_hyperframes(), health(), BaseModel, on_event, post, HyperFrames レンダリングワーカー — HTTP サーバー (ホストネイティブ実行版) api… (+10 more)

### Community 46 - "_set_sqlite_pragmas"
Cohesion: 0.67
Nodes (3): listens_for, 接続ごとに SQLite のロック挙動を調整する。, _set_sqlite_pragmas()

### Community 47 - "_run_preview_synthesis"
Cohesion: 0.29
Nodes (7): バックグラウンドで TTS 合成を実行し、結果をジョブストアに保存する。, _run_preview_synthesis(), apply_speed(), Path, src の音声に読み上げ速度を掛けて dst へ書き出す。掛けたら True。 速度を TTS のキャッシュより後段で適用しているのが要点。…, derive_seed(), キー文字列から決定的なシードを導出する。 シードを固定することで、同じ原稿からは常に同じ音声が得られる。…

### Community 48 - "synthesize_scene_audio"
Cohesion: 0.33
Nodes (7): generate_silent_wav(), Path, 区切りが始まる秒数を求める。 chunk_starts は TTS サーバーが返した「各チャンクが始まる秒数」。…, 24kHz, 16-bit, モノラルの無音 WAV ファイルを指定秒数生成して保存し、バイト列を返す。, 1シーン分の TTS 音声を合成し、output_wav_path に保存して WAV バイト列を返す。 stats に dict…, segment_start_seconds(), synthesize_scene_audio()

### Community 49 - "VoiceRecording"
Cohesion: 0.19
Nodes (17): 音声収集セッションで収録した音声（収録音声ライブラリ）。 セッション完了時にここへ名前付きで保存し、話者の新規追加画面から…, VoiceRecording, delete_recording(), delete_speaker(), get_recording_audio(), list_recordings(), AsyncSession, delete (+9 more)

### Community 52 - "config.py"
Cohesion: 0.33
Nodes (5): BaseSettings, pydantic_settings, Config, アプリケーション設定 (環境変数 / デフォルト値), Settings

### Community 53 - "session_record"
Cohesion: 0.22
Nodes (13): create_speaker(), _load_session(), Path, post, UploadFile, セッション情報をメモリとディスクの両方に保存する。, セッションを取得する。メモリに無ければディスクから復元する。, resample_to_16k() (+5 more)

### Community 54 - "audio_utils.py"
Cohesion: 0.18
Nodes (14): logging, numpy, soundfile, subprocess, build_reference_audio(), normalize_level(), ndarray, 音声の後処理。参照音声（reference.wav）の作成と、読み上げ速度の適用。… (+6 more)

### Community 55 - "_prompts.py"
Cohesion: 0.18
Nodes (15): content_prompt(), default_layout_for(), _field_line(), layout_menu(), LLM プロンプトの部品を、型とレイアウトの定義から自動で組み立てる。 プロンプトに値を直書きしない（design_tokens.py と同じ方針）。…, その型に属する見せ方の候補一覧。 only を渡すと、その 1 つだけを出す。ユーザーが見せ方を固定したとき用で、 候補を絞ることで「件数の上限」が LLM…, 章立ての段階（まだ内容が無い時点）で置く見せ方。 型が宣言した default_layout を使う。以前はその型のレイアウトのうち…, 段階 2 のプロンプト。内容の生成と見せ方の選択を 1 回のやり取りで行う。 target_chars … ナレーションの目安の文字数。None… (+7 more)

### Community 56 - "ScenarioRouteA.vue"
Cohesion: 0.17
Nodes (14): assetApi, buildPreviewScenes(), emit, file, finalize(), generateFromPptx(), importResult, narrationJob (+6 more)

### Community 57 - "speakers.py"
Cohesion: 0.47
Nodes (7): scipy_signal, BaseModel, SessionFinalizeRequest, SessionStartRequest, UseRecordingRequest, VoiceRecordingRead, VoiceRecordingUpdate

### Community 58 - "schemas/speaker.py"
Cohesion: 0.53
Nodes (5): BaseModel, SpeakerBase, SpeakerCreate, SpeakerRead, SpeakerUpdate

### Community 59 - "selectScene"
Cohesion: 0.20
Nodes (11): applySlideContentFromScene(), executeBulkGen(), executeSceneGenerate(), generateImagePrompt(), generateNarration(), generateSceneContent(), handleAddScene(), handleDeleteScene() (+3 more)

### Community 60 - "vue"
Cohesion: 0.26
Nodes (10): pinia, vue, { snackbar, sidebarOpen }, uiStore, webapp_frontend_src_assets_logo, useGenerationStore, useProjectsStore, useSpeakersStore (+2 more)

### Community 61 - "_field_dict"
Cohesion: 0.50
Nodes (4): _field_dict(), list_layouts(), FieldSpec を素の dict にする（フロントの汎用フォームがこれを読む）。, 型ごとにまとめたレイアウト一覧と、型ごとの編集フォーム定義を返す。

### Community 62 - "normalize_narration_length"
Cohesion: 0.50
Nodes (4): narration_target_seconds(), normalize_narration_length(), ナレーションの長さを許可された段階に丸める。NULL は既定（標準）。, プリセットの目安の秒数（等倍で読んだ場合）。

### Community 63 - "get"
Cohesion: 0.11
Nodes (19): get(), health(), root(), Speaker, layout_sample(), AsyncSession, レイアウト選択ギャラリーのサムネイル用 HTML。 サムネイル画像は持たない。実際のレイアウトビルダーにサンプル内容を流して…, get_pptx_import_status() (+11 more)

### Community 64 - "_ask_json"
Cohesion: 0.50
Nodes (4): _ask_json(), _parse_json_reply(), LLM に JSON を返させ、パースして返す。 temperature が 0 ではないため、同じプロンプトでも壊れた JSON が返ることがある （実測で…, LLM の応答から JSON を取り出す。取り出せなければ None。 3 段階で試す。壊れ方はモデルの気分次第なので、機械的に直せる範囲だけ直す。 1.…

### Community 65 - "devDependencies"
Cohesion: 0.50
Nodes (4): devDependencies, vite, vite-plugin-vuetify, @vitejs/plugin-vue

### Community 66 - "scripts"
Cohesion: 0.50
Nodes (4): scripts, build, dev, preview

### Community 67 - "chart_scale/spec.py"
Cohesion: 0.22
Nodes (5): math, _prepare(), 値を「円の面積」に対応させる。 直径を値に比例させると、面積は値の 2 乗で増えてしまい、 差が実際よりずっと大きく見える。直径は平方根に比例させる。, _prepare(), ノードを円周に置き、すべての組を双方向の矢印でつなぐ。 循環（一巡して戻る）ではなく「互いに影響し合う」関係なので、 隣どうしではなく **全ての組**…

### Community 69 - "releaseStream"
Cohesion: 0.38
Nodes (6): closeSessionDialog(), releaseStream(), startRecording(), startWaveform(), stopRecording(), stopWaveform()

### Community 71 - "AvatarPicker.vue"
Cohesion: 0.53
Nodes (5): avatarFilename(), avatarUrl(), emit, props, select()

### Community 73 - "resetTake"
Cohesion: 0.47
Nodes (6): initCanvas(), openSessionDialog(), prevSentence(), resetTake(), startSession(), submitRecordAndNext()

### Community 74 - "stop.sh"
Cohesion: 0.70
Nodes (4): err(), log(), stop.sh script, warn()

### Community 75 - "registry"
Cohesion: 0.12
Nodes (15): collect_css(), _discover(), normalize_layout_id(), layouts/*/spec.py を読み込んで SPEC を集める。 import は遅延させている。モジュール読み込み時に走らせると、 spec.py…, 開発時にレイアウトを追加した後、再起動せずに読み直すためのもの。, DB / LLM から来た値を実在するレイアウト ID に丸める。, resolve() の結果。reason は「なぜ差し替えたか」の日本語（ログと UI に出す）。, 内容の実データを見て、実際に使うレイアウトを決める。 引数: type_id … 型（AI が段階 1 で決めたもの） content …… (+7 more)

### Community 77 - "loadSpeakers"
Cohesion: 0.50
Nodes (4): deleteSpeaker(), loadSpeakers(), saveNewSpeaker(), saveUpdatedSpeaker()

### Community 78 - "finalizeSession"
Cohesion: 0.50
Nodes (4): finalizeSession(), loadRecordings(), openAddDialog(), removeRecording()

### Community 100 - "AI-MovGen — 研修動画の自動生成ツール"
Cohesion: 0.06
Nodes (31): 1. プロジェクトと動画を作る, 1. リポジトリを取得する, 2. シーンを作る, 2. ホスト側の依存を入れる, 3. ローカル LLM を用意する, 3. 話者を設定する, 3 通りの入力からシナリオを作る, 4. TTS サーバーの仮想環境を作る (+23 more)

### Community 106 - "routers/generation.py"
Cohesion: 0.15
Nodes (23): urllib_parse, GenerationHistory, _check_and_fail_timeouts(), delete_generation(), download_subtitle(), download_video(), generate_video(), get_generation_status() (+15 more)

## Knowledge Gaps
- **307 isolated node(s):** `new_project.sh script`, `MODEL_CACHE_DIR`, `HF_HOME`, `QWEN3_TTS_MODEL_ID`, `VOICE_SAMPLES_DIR` (+302 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 726 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `トラブルシューティング` connect `generate_composition` to `AI-MovGen — 研修動画の自動生成ツール`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `AI-MovGen — 研修動画の自動生成ツール` connect `AI-MovGen — 研修動画の自動生成ツール` to `generate_composition`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `find_missing_local_refs()` connect `generate_composition` to `run_generation`, `composition.py`, `renderer.py`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 44 inferred relationships involving `Scene` (e.g. with `delete_asset()` and `list_assets()`) actually correct?**
  _`Scene` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Video` (e.g. with `_recover_stuck_generations()` and `delete_asset()`) actually correct?**
  _`Video` has 31 INFERRED edges - model-reasoned connections that need verification._
- **What connects `new_project.sh script`, `MODEL_CACHE_DIR`, `HF_HOME` to the rest of the system?**
  _307 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `llm_service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13405797101449277 - nodes in this community are weakly interconnected._