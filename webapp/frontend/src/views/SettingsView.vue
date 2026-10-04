<template>
  <v-container class="pa-6" max-width="860">
    <div class="d-flex align-center gap-3 mb-6">
      <div class="pa-2 rounded-lg" style="background: rgba(6, 182, 212, 0.12); border: 1px solid rgba(6, 182, 212, 0.3);">
        <v-icon size="26" color="#06b6d4">mdi-tune-vertical</v-icon>
      </div>
      <div>
        <h1 class="text-h5 font-weight-black title-gradient">システム・環境設定</h1>
        <p class="text-body-2 text-medium-emphasis">LLM・音声合成エンジン（Qwen3-TTS）・レンダラーのパラメータを設定します</p>
      </div>
    </div>

    <!-- LLM 設定 -->
    <v-card class="mb-4 glass-card">
      <v-card-title class="text-body-1 font-weight-medium pa-4">ローカル LLM</v-card-title>
      <v-card-text>
        <v-text-field
          v-model="settings.local_llm_base_url"
          label="エンドポイント URL"
          hint="例: http://host.docker.internal:11434/v1"
          persistent-hint
          class="mb-3"
        />
        <v-text-field
          v-model="settings.local_llm_model"
          label="モデル名"
          hint="例: qwen3:14b"
          persistent-hint
          class="mb-3"
        />
        <v-switch
          v-model="settings.enable_think"
          label="Thinkモード（思考プロセスの生成）を有効化"
          color="primary"
          hint="オフ（デフォルト）にすると無駄な思考トークンの生成がカットされ、応答速度・パフォーマンスが劇的に向上します。"
          persistent-hint
        />
      </v-card-text>
    </v-card>

    <!-- 動画デフォルト設定 -->
    <v-card class="mb-4 glass-card">
      <v-card-title class="text-body-1 font-weight-medium pa-4">動画デフォルト設定</v-card-title>
      <v-card-text>
        <v-select
          v-model="settings.default_fps"
          :items="[20, 24, 30, 60]"
          label="フレームレート (FPS)"
          hint="低いほどレンダリングが速くなります。スライド主体の動画では24でも劣化はほぼ分かりません。"
          persistent-hint
          class="mb-3"
        />
        <v-select
          v-model="settings.render_workers"
          :items="workerOptions"
          item-title="title"
          item-value="value"
          label="レンダリング並列ワーカー数"
          hint="Chrome 1プロセスあたり約256MB。メモリ不足で停止する場合は減らしてください。"
          persistent-hint
          class="mb-3"
        />
        <v-select
          v-model="settings.render_chunk_sec"
          :items="chunkOptions"
          item-title="title"
          item-value="value"
          label="分割レンダリングの閾値"
          hint="この長さを超える動画はシーン単位で分割してレンダリングし、最後に連結します。メモリ使用量の上限を抑えられます。"
          persistent-hint
        />
      </v-card-text>
    </v-card>

    <!-- Qwen3-TTS 設定 -->
    <v-card class="mb-4 glass-card">
      <v-card-title class="text-body-1 font-weight-medium pa-4">Qwen3-TTS 設定</v-card-title>
      <v-card-text>
        <v-text-field
          v-model="settings.qwen3_tts_base_url"
          label="Qwen3-TTS エンドポイント URL"
          hint="例: http://qwen3-tts:8100"
          persistent-hint
          class="mb-3"
        />
        <v-text-field
          v-model.number="settings.tts_request_timeout"
          label="TTS タイムアウト (秒)"
          type="number"
          hint="音声合成の最大待ち時間（秒）。長いナレーションやCPU推論の場合は 1800 (30分) 以上を推奨"
          persistent-hint
        />
      </v-card-text>
    </v-card>

    <!-- HyperFrames レンダラー設定 -->
    <v-card class="mb-4 glass-card">
      <v-card-title class="text-body-1 font-weight-medium pa-4">HyperFrames レンダラー設定</v-card-title>
      <v-card-text>
        <v-text-field
          v-model.number="settings.renderer_request_timeout"
          label="動画レンダリング タイムアウト (秒)"
          type="number"
          hint="動画レンダリングの最大処理時間（秒）。長尺動画や高解像度の場合は 3600 (60分) 以上を推奨"
          persistent-hint
        />
      </v-card-text>
    </v-card>

    <!-- 話者管理 -->
    <v-card class="mb-4 glass-card">
      <v-card-title class="d-flex align-center justify-space-between text-body-1 font-weight-medium pa-4">
        <span>話者管理</span>
        <div class="d-flex gap-2">
          <v-btn size="small" color="primary" class="mr-2" prepend-icon="mdi-plus" @click="openAddDialog()">
            新しい話者を追加
          </v-btn>
          <v-btn size="small" color="secondary" prepend-icon="mdi-microphone" @click="openSessionDialog">
            音声収集セッションで作成
          </v-btn>
        </div>
      </v-card-title>
      <v-card-text>
        <!-- ローカル録音ツール（#12）。HTTP などで画面上のマイクを使えない環境向け -->
        <v-alert
          :type="micSupported ? 'info' : 'warning'"
          variant="tonal"
          density="compact"
          class="mb-4 text-body-2"
        >
          <div v-if="micSupported">
            録音ツール（HTML ファイル）を使うと、ブラウザで開くだけでこの画面の外でも録音できます。
            保存した収録データを取り込むと、収録音声ライブラリに登録されます。
          </div>
          <div v-else>
            <strong>この接続（HTTP）では、画面上でマイクを使った録音ができません。</strong><br />
            録音ツールをダウンロードして Google Chrome または Microsoft Edge で開き、
            録音して保存した収録データを取り込んでください。
          </div>
          <div class="d-flex flex-wrap gap-2 mt-2">
            <v-btn
              size="small"
              variant="flat"
              color="primary"
              prepend-icon="mdi-download"
              :loading="downloadingTool"
              @click="downloadRecorderTool"
            >
              録音ツールをダウンロード
            </v-btn>
            <v-btn size="small" variant="outlined" prepend-icon="mdi-upload" @click="openImportDialog">
              収録データを取り込む
            </v-btn>
          </div>
        </v-alert>

        <v-list class="bg-transparent pa-0">
          <v-list-item
            v-for="speaker in speakers"
            :key="speaker.id"
            class="border-bottom mb-2 pa-3 rounded-lg"
            style="background: rgba(255, 255, 255, 0.05);"
          >
            <div class="d-flex align-center justify-space-between w-100">
              <div class="d-flex align-center">
                <!-- アバター表示 -->
                <v-avatar size="40" class="mr-3">
                  <img
                    v-if="speaker.avatar_path"
                    :src="speakerAvatarUrl(speaker)"
                    :alt="speaker.name"
                    style="width: 100%; height: 100%; object-fit: cover;"
                  />
                  <v-icon v-else size="32" color="grey">mdi-account-circle</v-icon>
                </v-avatar>
                <div>
                  <div class="d-flex align-center">
                    <span class="font-weight-bold text-subtitle-1 mr-2">{{ speaker.name }}</span>
                    <v-chip size="x-small" :color="speaker.is_system ? 'primary' : 'secondary'" class="mr-1">
                      {{ speaker.is_system ? 'システム' : 'ユーザー' }}
                    </v-chip>
                    <v-chip size="x-small">{{ speaker.language }}</v-chip>
                  </div>
                  <div class="text-caption text-medium-emphasis mt-1">{{ speaker.description || '説明なし' }}</div>
                  <div class="text-caption text-medium-emphasis mt-1">
                    参照音声: <span class="font-mono text-break">{{ speaker.reference_audio_path || '未登録' }}</span>
                  </div>
                  <v-alert
                    v-if="speaker.is_system && speaker.reference_audio_path && speaker.reference_audio_path.includes('default/reference.wav')"
                    type="warning"
                    density="compact"
                    variant="tonal"
                    class="text-caption mt-1 py-1"
                    hide-details
                    icon="mdi-alert-circle-outline"
                  >
                    既定話者はダミー音声です。実音声のアップロードまたは収録を推奨します。
                  </v-alert>
                </div>
              </div>
              <div class="d-flex align-center gap-1">
                <v-btn size="small" variant="text" color="primary" @click="openEditDialog(speaker)">
                  編集
                </v-btn>
                <v-btn
                  v-if="!speaker.is_system"
                  size="small"
                  variant="text"
                  color="error"
                  @click="deleteSpeaker(speaker.id)"
                >
                  削除
                </v-btn>
              </div>
            </div>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>

    <!-- 収録音声ライブラリ -->
    <v-card class="mb-4 glass-card">
      <v-card-title class="d-flex align-center justify-space-between text-body-1 font-weight-medium pa-4">
        <span>収録音声ライブラリ</span>
        <v-chip size="x-small" variant="outlined">{{ recordings.length }} 件</v-chip>
      </v-card-title>
      <v-card-text>
        <div v-if="recordings.length === 0" class="text-caption text-medium-emphasis">
          収録音声はまだありません。「音声収集セッションで作成」で収録するか、録音ツールの収録データを取り込むと、ここに保存され話者の参照音声として選べます。
        </div>
        <v-list v-else class="bg-transparent pa-0">
          <v-list-item
            v-for="rec in recordings"
            :key="rec.id"
            class="mb-2 pa-3 rounded-lg"
            style="background: rgba(255, 255, 255, 0.05);"
          >
            <div class="d-flex align-center justify-space-between w-100">
              <div>
                <div class="font-weight-bold text-subtitle-2">{{ rec.name }}</div>
                <div class="text-caption text-medium-emphasis mt-1">
                  {{ recordingModeLabel(rec.mode) }} / {{ rec.duration_sec }}秒 / {{ rec.take_count }}テイク
                </div>
              </div>
              <div class="d-flex align-center gap-1">
                <v-btn size="small" variant="text" icon="mdi-play" @click="playRecordingLibrary(rec)" />
                <v-btn size="small" variant="text" color="error" icon="mdi-delete" @click="removeRecording(rec)" />
              </div>
            </div>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>

    <!-- 読み辞書（全体辞書） (#64) -->
    <ReadingDictionaryTable />

    <div class="d-flex justify-end mb-6">
      <v-btn color="primary" :loading="saving" @click="save">設定を保存</v-btn>
    </div>

    <!-- 話者追加ダイアログ -->
    <v-dialog v-model="addDialog" max-width="560">
      <v-card class="glass-card">
        <v-card-title class="pa-4 text-h6">話者の新規追加</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field v-model="addForm.name" label="名前" required class="mb-3" />
          <v-select v-model="addForm.language" :items="['ja', 'en']" label="言語" class="mb-3" />
          <v-textarea v-model="addForm.description" label="説明" rows="3" class="mb-3" />

          <!-- 参照音声の取得元: 収録音声ライブラリ / ファイルアップロード -->
          <div class="text-caption text-medium-emphasis mb-1">参照音声</div>
          <v-btn-toggle v-model="addForm.source" mandatory density="comfortable" class="mb-3" divided>
            <v-btn value="recording" size="small" prepend-icon="mdi-microphone">収録音声から選択</v-btn>
            <v-btn value="file" size="small" prepend-icon="mdi-upload">ファイルをアップロード</v-btn>
          </v-btn-toggle>

          <div v-if="addForm.source === 'recording'">
            <v-select
              v-model="addForm.recordingId"
              :items="recordingOptions"
              item-title="title"
              item-value="value"
              label="収録音声を選択"
              :loading="loadingRecordings"
              :no-data-text="'収録音声がありません。「音声収集セッションで作成」で収録するか、収録データを取り込んでください。'"
              class="mb-2"
            />
            <div v-if="selectedRecording" class="d-flex align-center mb-2">
              <v-btn
                size="small"
                variant="tonal"
                prepend-icon="mdi-play"
                @click="playRecordingLibrary(selectedRecording)"
              >
                試聴する
              </v-btn>
              <span class="text-caption text-medium-emphasis ml-3">
                {{ recordingModeLabel(selectedRecording.mode) }} / {{ selectedRecording.duration_sec }}秒 /
                {{ selectedRecording.take_count }}テイク
              </span>
            </div>
          </div>

          <template v-else>
            <v-file-input
              v-model="addForm.file"
              label="参照音声 (WAV/MP3/M4A/FLAC)"
              accept=".wav,.mp3,.m4a,.flac"
              show-size
            />
            <v-checkbox
              v-model="addForm.clean"
              :label="CLEAN_UPLOAD_LABEL"
              :hint="CLEAN_UPLOAD_HINT"
              persistent-hint
              density="compact"
            />
          </template>

          <div class="mt-4">
            <AvatarPicker v-model="addForm.avatar_path" />
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 d-flex justify-end">
          <v-btn variant="text" @click="addDialog = false">キャンセル</v-btn>
          <v-btn color="primary" :loading="adding" @click="saveNewSpeaker">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 話者編集ダイアログ -->
    <v-dialog v-model="editDialog" max-width="500">
      <v-card class="glass-card">
        <v-card-title class="pa-4 text-h6">話者の編集</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field v-model="editForm.name" label="名前" required class="mb-3" />
          <v-select v-model="editForm.language" :items="['ja', 'en']" label="言語" class="mb-3" />
          <v-textarea v-model="editForm.description" label="説明" rows="3" class="mb-3" />
          <div class="mt-4 mb-3">
            <AvatarPicker v-model="editForm.avatar_path" />
          </div>
          <v-file-input
            v-model="editForm.file"
            label="参照音声の変更 (任意)"
            accept=".wav,.mp3,.m4a,.flac"
            show-size
          />
          <v-checkbox
            v-model="editForm.clean"
            :label="CLEAN_UPLOAD_LABEL"
            :hint="CLEAN_UPLOAD_HINT"
            persistent-hint
            density="compact"
          />
        </v-card-text>
        <v-card-actions class="pa-4 d-flex justify-end">
          <v-btn variant="text" @click="editDialog = false">キャンセル</v-btn>
          <v-btn color="primary" :loading="updating" @click="saveUpdatedSpeaker">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 収録データの取り込みダイアログ（#12） -->
    <v-dialog v-model="importDialog" max-width="520" :persistent="importing">
      <v-card class="glass-card">
        <v-card-title class="pa-4 text-h6">収録データを取り込む</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <p class="text-body-2 mb-4">
            録音ツールで保存した収録データ（.zip）を選んでください。
            前後の無音の除去と音量の調整を行い、約20秒の参照音声に整えて収録音声ライブラリに登録します。
          </p>
          <v-file-input
            v-model="importForm.file"
            label="収録データ (.zip)"
            accept=".zip,application/zip"
            show-size
            class="mb-2"
          />
          <v-text-field
            v-model="importForm.name"
            label="収録音声の名前（任意）"
            hint="空欄なら、録音ツールで付けた名前を使います"
            persistent-hint
            :maxlength="RECORDING_NAME_MAX_LENGTH"
            counter
          />
        </v-card-text>
        <v-card-actions class="pa-4 d-flex justify-end">
          <v-btn variant="text" :disabled="importing" @click="importDialog = false">キャンセル</v-btn>
          <v-btn color="primary" :loading="importing" @click="importRecordingPackage">取り込んで話者作成へ</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 音声収集セッションダイアログ -->
    <v-dialog v-model="sessionDialog" max-width="700" persistent>
      <v-card class="glass-card">
        <v-card-title class="pa-4 text-h6 d-flex align-center">
          <v-icon color="secondary" class="mr-2">mdi-microphone</v-icon>
          🎙 音声収集セッション
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="closeSessionDialog" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <!-- Step 1: 準備（モードと本数を選ぶ。固定コーパスなので即開始できる） -->
          <div v-if="currentStep === 1" class="py-4">
            <p class="mb-4 text-center">
              マイクを使って話者の参照音声を収録します。<br />
              ノイズの少ない静かな環境で、マイクから一定の距離を保って話してください。
            </p>

            <div class="text-caption text-medium-emphasis mb-2">収録モード</div>
            <v-radio-group v-model="sessionConfig.mode" class="mb-2" density="comfortable">
              <v-radio v-for="mode in RECORDING_MODES" :key="mode.value" :value="mode.value">
                <template #label>
                  <div>
                    <div class="font-weight-medium">{{ mode.label }}</div>
                    <div class="text-caption text-medium-emphasis">{{ mode.description }}</div>
                  </div>
                </template>
              </v-radio>
            </v-radio-group>

            <v-select
              v-model="sessionConfig.itemCount"
              :items="SESSION_ITEM_COUNTS"
              label="収録する本数"
              hint="1本あたり5〜20秒程度。参照音声は自動で約20秒に整えられます。"
              persistent-hint
              class="mb-6"
              max-width="240"
            />

            <div class="text-center">
              <v-btn color="primary" size="large" :loading="startingSession" @click="startSession">
                開始する
              </v-btn>
            </div>
          </div>

          <!-- Step 2: 収録 -->
          <div v-else-if="currentStep === 2">
            <div class="d-flex align-center justify-space-between mb-4">
              <span class="font-weight-bold text-subtitle-1">
                {{ currentSentenceIndex + 1 }} / {{ sessionItems.length }}
                <v-chip size="x-small" variant="outlined" class="ml-2">{{ sessionModeLabel }}</v-chip>
              </span>
              <v-progress-linear
                :model-value="((currentSentenceIndex + 1) / sessionItems.length) * 100"
                color="secondary"
                height="8"
                rounded
                class="ml-4"
                style="width: 45%"
              />
            </div>

            <!-- チャット対話モードは吹き出し表示、それ以外はカード表示 -->
            <div v-if="currentItem?.kind === 'answer'" class="mb-4">
              <div class="d-flex align-start mb-2">
                <v-avatar size="36" color="secondary" class="mr-3">
                  <v-icon>mdi-robot-happy</v-icon>
                </v-avatar>
                <div class="chat-bubble pa-4 rounded-lg text-body-1">
                  {{ currentItem.prompt }}
                </div>
              </div>
              <div class="text-caption text-medium-emphasis text-center mt-3">
                {{ currentItem.instruction }}
              </div>
            </div>
            <div v-else class="mb-4">
              <v-card variant="outlined" class="pa-6 text-center text-h6 font-weight-medium rounded-lg">
                {{ currentItem?.prompt }}
              </v-card>
              <div class="text-caption text-medium-emphasis text-center mt-2">
                {{ currentItem?.instruction }}
              </div>
            </div>

            <!-- マイクの選択とノイズ除去の強さ（録音中は変えられない） -->
            <div class="d-flex flex-wrap align-end gap-3 mb-3">
              <v-select
                v-model="recorder.microphoneId"
                :items="microphoneOptions"
                item-title="label"
                item-value="deviceId"
                label="マイク"
                density="compact"
                hide-details
                :disabled="recorder.isBusy"
                style="min-width: 220px; flex: 1"
              />
              <div>
                <div class="text-caption text-medium-emphasis mb-1">ノイズ除去</div>
                <v-btn-toggle
                  v-model="recorder.noiseReduction"
                  mandatory
                  density="compact"
                  divided
                  :disabled="recorder.isBusy"
                >
                  <v-btn v-for="level in NOISE_REDUCTION_LEVELS" :key="level.value" :value="level.value" size="small">
                    {{ level.label }}
                  </v-btn>
                </v-btn-toggle>
              </div>
            </div>

            <!-- 波形描画 Canvas（カウントダウン中は残り秒数を重ねて表示する） -->
            <div class="d-flex justify-center mb-2">
              <div class="waveform-wrap">
                <canvas ref="canvasRef" width="400" height="80" class="rounded-lg" style="background: #000; max-width: 100%;"></canvas>
                <div v-if="recorder.phase === 'countdown'" class="countdown-overlay">{{ recorder.countdownLeft }}</div>
              </div>
            </div>
            <div class="text-caption text-center mb-4">
              <span v-if="recorder.phase === 'countdown'" class="text-warning font-weight-bold">
                話さずにお待ちください（周囲の音を測っています）
              </span>
              <span v-else-if="recorder.phase === 'recording'" class="text-error font-weight-bold">
                ● 録音中です。話してください… {{ recorder.elapsedSec }}秒
              </span>
              <span v-else-if="recorder.phase === 'processing'" class="text-medium-emphasis">ノイズを除去しています…</span>
              <span v-else-if="recorder.hasTake" class="text-medium-emphasis">
                録音済み（{{ recorder.durationSec }}秒）。再生して確認し、問題なければ次へ進んでください。
              </span>
              <span v-else class="text-medium-emphasis">
                録音ボタンを押すと、{{ COUNTDOWN_SEC }}秒のカウントダウンの後に録音が始まります。
              </span>
            </div>

            <div class="d-flex justify-center align-center gap-4 mb-4">
              <v-btn
                v-if="!recorder.isCapturing"
                color="error"
                icon="mdi-record"
                size="x-large"
                :disabled="recorder.phase === 'processing' || submittingRecord"
                @click="startRecording"
              />
              <v-btn
                v-else
                color="grey-darken-3"
                icon="mdi-stop"
                size="x-large"
                @click="stopRecording"
              />
            </div>

            <!-- 処理前後の聴き比べ -->
            <div v-if="recorder.hasTake" class="d-flex justify-center gap-2 mb-4">
              <v-btn
                size="small"
                variant="tonal"
                color="primary"
                :prepend-icon="recorder.playing === 'processed' ? 'mdi-stop' : 'mdi-play'"
                @click="togglePlayback('processed')"
              >
                ノイズ除去後
              </v-btn>
              <v-btn
                size="small"
                variant="tonal"
                :prepend-icon="recorder.playing === 'original' ? 'mdi-stop' : 'mdi-play'"
                @click="togglePlayback('original')"
              >
                元の音
              </v-btn>
            </div>

            <!-- 入力レベルの警告 -->
            <v-alert
              v-for="warning in recorder.warnings"
              :key="warning.code"
              type="warning"
              variant="tonal"
              density="compact"
              class="mb-2 text-caption"
            >
              {{ warning.message }}
            </v-alert>

            <div class="d-flex justify-space-between mt-4">
              <v-btn
                variant="outlined"
                prepend-icon="mdi-arrow-left"
                :disabled="currentSentenceIndex === 0 || recorder.isBusy"
                @click="prevSentence"
              >
                前へ
              </v-btn>
              <v-btn
                color="primary"
                append-icon="mdi-arrow-right"
                :loading="submittingRecord"
                :disabled="!recorder.hasTake || recorder.isBusy"
                @click="submitRecordAndNext"
              >
                {{ currentSentenceIndex === sessionItems.length - 1 ? '収録を完了する' : 'この録音を使用して次へ' }}
              </v-btn>
            </div>
          </div>

          <!-- Step 3: 名前を付けて収録音声として保存 -->
          <div v-else-if="currentStep === 3" class="py-4">
            <p class="mb-4 text-center">
              🎉 収録が完了しました（{{ recordedCount }}本）。<br />
              名前を付けて保存すると、続けて話者を作成できます。
            </p>
            <v-text-field
              v-model="finalizeForm.name"
              label="収録音声の名前"
              hint="例: 山田さんの声（落ち着いたトーン）"
              persistent-hint
              required
              class="mb-4"
            />
            <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
              無音の除去と音量の正規化を行い、各テイクから均等に集めて約20秒の参照音声に整えます。
            </v-alert>

            <div class="d-flex justify-end gap-2">
              <v-btn variant="text" :disabled="finalizing" @click="currentStep = 2">戻る</v-btn>
              <v-btn color="primary" :loading="finalizing" @click="finalizeSession">
                保存して話者作成へ
              </v-btn>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { api, withBase } from '@/api/index.js'
import { speakerApi } from '@/api/speaker.js'
import { COUNTDOWN_SEC, NOISE_REDUCTION_LEVELS } from '@/audio/config.js'
import { isMicrophoneSupported } from '@/audio/capture.js'
import { useVoiceTakeRecorder } from '@/composables/useVoiceTakeRecorder.js'
import {
  DEFAULT_SESSION_ITEM_COUNT,
  RECORDING_MODES,
  SESSION_ITEM_COUNTS,
  recordingModeLabel,
} from '@/constants/recordingModes.js'
import { embedRecorderData } from '@/recorder-tool/embeddedData.js'
import { saveBlobAsFile } from '@/utils/download.js'
import { useUiStore } from '@/stores/ui'
import AvatarPicker from '@/components/AvatarPicker.vue'
import ReadingDictionaryTable from '@/components/ReadingDictionaryTable.vue'

const ui = useUiStore()
const saving = ref(false)
const speakers = ref([])

// 話者アバター画像のURLを解決（サブパス運用にも対応）
const speakerAvatarUrl = (speaker) => {
  if (!speaker?.avatar_path) return ''
  const path = speaker.avatar_path.startsWith('/')
    ? speaker.avatar_path
    : `/static/avatars/${speaker.avatar_path}`
  return withBase(path)
}

const settings = reactive({
  local_llm_base_url: 'http://host.docker.internal:11434/v1',
  local_llm_model: 'qwen3:14b',
  enable_think: false,
  default_fps: 24,
  qwen3_tts_base_url: 'http://qwen3-tts:8100',
  tts_request_timeout: 1800,
  renderer_request_timeout: 3600,
  render_workers: 4,
  render_chunk_sec: 300,
})

const workerOptions = [
  { title: '自動（コア数から決定）', value: 0 },
  { title: '1 （最も省メモリ・低速）', value: 1 },
  { title: '2', value: 2 },
  { title: '4 （推奨）', value: 4 },
  { title: '6', value: 6 },
  { title: '8', value: 8 },
]

const chunkOptions = [
  { title: '分割しない', value: 0 },
  { title: '3分ごと', value: 180 },
  { title: '5分ごと（推奨）', value: 300 },
  { title: '10分ごと', value: 600 },
]

// ダイアログ & フォーム
const addDialog = ref(false)
const adding = ref(false)
const addForm = reactive({
  name: '',
  language: 'ja',
  description: '',
  // 参照音声の取得元: 'recording'（収録音声ライブラリ）/ 'file'（アップロード）
  source: 'recording',
  recordingId: null,
  file: null,
  // アップロードした音声の雑音を除去して整えるか（#10）
  clean: true,
  avatar_path: null,
})

const editDialog = ref(false)
const updating = ref(false)
const editForm = reactive({
  id: '',
  name: '',
  language: 'ja',
  description: '',
  file: null,
  clean: true,
  avatar_path: null,
})

// アップロード時の雑音除去チェックボックスの文言（追加・編集ダイアログで共用）
const CLEAN_UPLOAD_LABEL = '雑音を除去して整える（推奨）'
const CLEAN_UPLOAD_HINT = 'ノイズ除去と前後の無音・クリック音の除去、音量の調整を行います。スタジオで録った音声をそのまま使う場合は外してください。'

// 音声収集セッション関連
const sessionDialog = ref(false)
const currentStep = ref(1)
const startingSession = ref(false)
const submittingRecord = ref(false)
const finalizing = ref(false)
const sessionConfig = reactive({
  mode: RECORDING_MODES[0].value,
  itemCount: DEFAULT_SESSION_ITEM_COUNT,
})

const sessionId = ref('')
const sessionItems = ref([])          // [{ index, prompt, instruction, kind }]
const sessionModeLabel = ref('')
const currentSentenceIndex = ref(0)
const recordedCount = ref(0)

const currentItem = computed(() => sessionItems.value[currentSentenceIndex.value] || null)

// 収録音声ライブラリ
const recordings = ref([])
const loadingRecordings = ref(false)

const recordingOptions = computed(() =>
  recordings.value.map(r => ({
    value: r.id,
    title: `${r.name}（${recordingModeLabel(r.mode)} / ${r.duration_sec}秒）`,
  }))
)
const selectedRecording = computed(() =>
  recordings.value.find(r => r.id === addForm.recordingId) || null
)

// 録音（カウントダウン・端の自動カット・ノイズ除去は composable が担う。#11）
// reactive で包むと、テンプレートでもスクリプトでも .value なしで扱える
const canvasRef = ref(null)
const recorder = reactive(useVoiceTakeRecorder({ canvasRef }))
const microphoneOptions = computed(() => [
  { deviceId: '', label: '既定のマイク' },
  ...recorder.microphones,
])
// この画面でマイクを使えるか（HTTP では使えない。そのときは録音ツールを案内する）
const micSupported = isMicrophoneSupported()
// マイクを使えない接続（HTTP など）で録音しようとしたときの案内
const MIC_UNAVAILABLE_MESSAGE =
  'このブラウザ／URL ではマイクを使用できません。「録音ツールをダウンロード」から録音ツールを使うか、http://localhost:3000 または HTTPS でアクセスしてください。'

// ─── ローカル録音ツール（#12） ───
// ビルド済みの録音ツール（vite.recorder.config.js が dist/tools/ に出力する）
const RECORDER_TOOL_PATH = '/tools/voice-recorder.html'
const RECORDER_TOOL_FILE_NAME = 'ai-mov-studio-voice-recorder.html'
// 収録音声の名前の上限（サーバー側の services/recording_package.py と同じ）
const RECORDING_NAME_MAX_LENGTH = 100
const downloadingTool = ref(false)
const importDialog = ref(false)
const importing = ref(false)
const importForm = reactive({
  file: null,
  name: '',
})

// 試聴用の Audio 要素（多重再生を避けるため1つを使い回す）
let previewAudio = null

const finalizeForm = reactive({
  name: '',
})

onMounted(async () => {
  await loadSettings()
  await loadSpeakers()
  await loadRecordings()
})

async function loadSettings() {
  try {
    const { data } = await api.get('/settings')
    Object.assign(settings, data)
  } catch (e) {
    ui.notifyError('設定の取得に失敗しました: ' + e.message)
  }
}

async function loadSpeakers() {
  try {
    const { data } = await speakerApi.list()
    speakers.value = data
  } catch (e) {
    ui.notifyError('話者一覧の取得に失敗しました: ' + e.message)
  }
}

async function loadRecordings() {
  loadingRecordings.value = true
  try {
    const { data } = await speakerApi.listRecordings()
    recordings.value = data
  } catch (e) {
    ui.notifyError('収録音声の取得に失敗しました: ' + e.message)
  } finally {
    loadingRecordings.value = false
  }
}

// 収録音声の試聴
function playRecordingLibrary(rec) {
  if (!rec?.audio_url) return
  if (previewAudio) previewAudio.pause()
  previewAudio = new Audio(rec.audio_url)
  previewAudio.play().catch(e => ui.notifyError('再生に失敗しました: ' + e.message))
}

async function removeRecording(rec) {
  if (!confirm(`収録音声「${rec.name}」を削除しますか？（この音声を既に採用した話者はそのまま使えます）`)) return
  try {
    await speakerApi.deleteRecording(rec.id)
    if (addForm.recordingId === rec.id) addForm.recordingId = null
    ui.notify('収録音声を削除しました')
    await loadRecordings()
  } catch (e) {
    ui.notifyError('収録音声の削除に失敗しました: ' + e.message)
  }
}

async function save() {
  saving.value = true
  try {
    const { data } = await api.patch('/settings', settings)
    Object.assign(settings, data)
    ui.notify('設定を保存しました')
  } catch (e) {
    ui.notifyError('設定の保存に失敗しました: ' + e.message)
  } finally {
    saving.value = false
  }
}

// 新規話者追加
// presetRecording を渡すと、収録音声を選択済みの状態で開く（収録セッション完了後の遷移）
function openAddDialog(presetRecording = null) {
  addForm.name = presetRecording?.name || ''
  addForm.language = 'ja'
  addForm.description = ''
  addForm.source = presetRecording ? 'recording' : (recordings.value.length > 0 ? 'recording' : 'file')
  addForm.recordingId = presetRecording?.id || null
  addForm.file = null
  addForm.clean = true
  addForm.avatar_path = null
  addDialog.value = true
}

async function saveNewSpeaker() {
  if (!addForm.name) {
    ui.notifyError('名前は必須です')
    return
  }
  const useRecording = addForm.source === 'recording'
  if (useRecording && !addForm.recordingId) {
    ui.notifyError('収録音声を選択してください')
    return
  }
  if (!useRecording && !addForm.file) {
    ui.notifyError('参照音声ファイルを選択してください')
    return
  }

  adding.value = true
  try {
    // 1. パスを空文字で話者レコードを作成
    const { data: newSpeaker } = await speakerApi.create({
      name: addForm.name,
      description: addForm.description,
      language: addForm.language,
      reference_audio_path: '',
      is_system: false,
    })

    // 2. 参照音声を確定（収録音声ライブラリから採用 / ファイルをアップロード）
    if (useRecording) {
      await speakerApi.useRecording(newSpeaker.id, addForm.recordingId)
    } else {
      await speakerApi.uploadReference(newSpeaker.id, addForm.file, addForm.clean)
    }

    if (addForm.avatar_path) {
      await speakerApi.update(newSpeaker.id, { avatar_path: addForm.avatar_path })
    }

    ui.notify('話者を追加しました')
    addDialog.value = false
    await loadSpeakers()
  } catch (e) {
    ui.notifyError('話者の追加に失敗しました: ' + e.message)
  } finally {
    adding.value = false
  }
}

// 話者編集
function openEditDialog(speaker) {
  editForm.id = speaker.id
  editForm.name = speaker.name
  editForm.language = speaker.language
  editForm.description = speaker.description || ''
  editForm.avatar_path = speaker.avatar_path || null
  editForm.file = null
  editForm.clean = true
  editDialog.value = true
}

async function saveUpdatedSpeaker() {
  if (!editForm.name) {
    ui.notifyError('名前は必須です')
    return
  }
  updating.value = true
  try {
    // 1. メタデータを更新
    await speakerApi.update(editForm.id, {
      name: editForm.name,
      description: editForm.description,
      language: editForm.language,
      avatar_path: editForm.avatar_path,
    })

    // 2. 音声ファイルが指定されていればアップロード
    if (editForm.file) {
      await speakerApi.uploadReference(editForm.id, editForm.file, editForm.clean)
    }

    ui.notify('話者情報を更新しました')
    editDialog.value = false
    await loadSpeakers()
  } catch (e) {
    ui.notifyError('話者情報の更新に失敗しました: ' + e.message)
  } finally {
    updating.value = false
  }
}

// 話者削除
async function deleteSpeaker(id) {
  if (!confirm('本当にこの話者を削除しますか？')) return
  try {
    await speakerApi.delete(id)
    ui.notify('話者を削除しました')
    await loadSpeakers()
  } catch (e) {
    ui.notifyError('話者の削除に失敗しました: ' + e.message)
  }
}

// ─── ローカル録音ツール（#12） ───
// ツール本体に読み上げ文などを埋め込んで保存させる。
// ツールはサーバーと通信せずに動くため、ダウンロードの時点で必要なデータをすべて渡す
async function downloadRecorderTool() {
  downloadingTool.value = true
  try {
    const [toolResponse, { data: corpus }] = await Promise.all([
      fetch(withBase(RECORDER_TOOL_PATH), { cache: 'no-store' }),
      speakerApi.sessionCorpus(),
    ])
    if (!toolResponse.ok) throw new Error(`録音ツールを取得できません (${toolResponse.status})`)
    const html = embedRecorderData(await toolResponse.text(), {
      ...corpus,
      // ツールの保存画面から、取り込み先（この設定画面）へ戻れるようにする
      app_url: `${window.location.origin}${withBase('/settings')}`,
      generated_at: new Date().toISOString(),
    })
    saveBlobAsFile(new Blob([html], { type: 'text/html' }), RECORDER_TOOL_FILE_NAME)
    ui.notify('録音ツールをダウンロードしました。Google Chrome または Microsoft Edge で開いてください。', 'success', 5000)
  } catch (e) {
    ui.notifyError('録音ツールのダウンロードに失敗しました: ' + e.message)
  } finally {
    downloadingTool.value = false
  }
}

function openImportDialog() {
  importForm.file = null
  importForm.name = ''
  importDialog.value = true
}

// 収録データを取り込み、続けて話者作成ダイアログへ遷移する（収録セッション完了時と同じ導線）
async function importRecordingPackage() {
  if (!importForm.file) {
    ui.notifyError('収録データ（.zip）を選択してください')
    return
  }
  importing.value = true
  try {
    const { data: rec } = await speakerApi.importRecording(importForm.file, importForm.name.trim())
    ui.notify(`収録音声「${rec.name}」を取り込みました（${rec.duration_sec}秒）`)
    importDialog.value = false
    await loadRecordings()
    openAddDialog(rec)
  } catch (e) {
    ui.notifyError('収録データの取り込みに失敗しました: ' + e.message)
  } finally {
    importing.value = false
  }
}

// 音声収集セッション関連
function openSessionDialog() {
  currentStep.value = 1
  sessionId.value = ''
  sessionItems.value = []
  sessionModeLabel.value = ''
  currentSentenceIndex.value = 0
  recordedCount.value = 0
  recorder.reset()
  finalizeForm.name = ''
  sessionDialog.value = true
}

function closeSessionDialog() {
  if (recorder.isBusy && !confirm('録音中です。セッションを閉じてもよろしいですか？')) return
  // 録音中ならマイクを解放し、録音途中のテイクも捨てる
  recorder.reset()
  sessionDialog.value = false
}

async function startSession() {
  startingSession.value = true
  try {
    const { data } = await speakerApi.sessionStart(sessionConfig.mode, sessionConfig.itemCount)
    sessionId.value = data.session_id
    sessionItems.value = data.items
    sessionModeLabel.value = data.mode_label
    currentSentenceIndex.value = 0
    recordedCount.value = 0
    recorder.reset()
    // 波形の canvas は手順 2 で表示された時点で、composable が待機中の表示を描く
    currentStep.value = 2
  } catch (e) {
    ui.notifyError('セッションの開始に失敗しました: ' + e.message)
  } finally {
    startingSession.value = false
  }
}

// 録音開始（3 秒のカウントダウンから始まる）
async function startRecording() {
  // getUserMedia は https か localhost でしか使えない。LAN の IP 直打ちだと
  // navigator.mediaDevices が undefined になるため、原因が分かるように明示的に案内する
  if (!isMicrophoneSupported()) {
    ui.notifyError(MIC_UNAVAILABLE_MESSAGE)
    return
  }
  try {
    await recorder.start()
  } catch (e) {
    ui.notifyError(e.message)
  }
}

// 録音停止（端のカットとノイズ除去まで行う）
async function stopRecording() {
  try {
    const result = await recorder.stop()
    if (result === 'cancelled') {
      ui.notify('カウントダウン中に停止したため、録音を取り消しました', 'info')
    } else if (result === 'empty') {
      ui.notifyError('発話が録音されていません。もう一度録音してください。')
    }
  } catch (e) {
    ui.notifyError('録音の処理に失敗しました: ' + e.message)
  }
}

// ノイズ除去後 / 元の音の再生を切り替える（再生中のものを押したら止める）
function togglePlayback(kind) {
  if (recorder.playing === kind) {
    recorder.stopPlayback()
    return
  }
  recorder.play(kind).catch(e => ui.notifyError('再生に失敗しました: ' + e.message))
}

// 録音アップロードと次の項目への移行
async function submitRecordAndNext() {
  // 送るのはノイズ除去後の 16kHz WAV（短すぎる・音割れなどの警告は録音直後に表示済み）
  const wavBlob = recorder.processedWavBlob()
  if (!wavBlob) return
  submittingRecord.value = true
  try {
    const { data } = await speakerApi.sessionRecord(
      sessionId.value,
      currentSentenceIndex.value + 1,
      wavBlob,
      `take_${currentSentenceIndex.value + 1}.wav`
    )
    recordedCount.value = data.recorded_count
    recorder.discard()

    if (currentSentenceIndex.value < sessionItems.value.length - 1) {
      currentSentenceIndex.value++
    } else {
      // 全項目の収録完了 → 名前を付けて保存するステップへ
      currentStep.value = 3
    }
  } catch (e) {
    ui.notifyError('録音のアップロードに失敗しました: ' + e.message)
  } finally {
    submittingRecord.value = false
  }
}

function prevSentence() {
  if (currentSentenceIndex.value > 0) {
    currentSentenceIndex.value--
    recorder.discard()
  }
}

// 収録音声として保存し、続けて話者作成ダイアログへ遷移する
async function finalizeSession() {
  if (!finalizeForm.name) {
    ui.notifyError('収録音声の名前は必須です')
    return
  }
  finalizing.value = true
  try {
    const { data: rec } = await speakerApi.sessionFinalize(sessionId.value, {
      name: finalizeForm.name,
    })
    ui.notify(`収録音声「${rec.name}」を保存しました（${rec.duration_sec}秒）`)

    sessionDialog.value = false
    recorder.reset()
    await loadRecordings()

    // 保存した収録音声を選択済みにして「話者の新規追加」を開く
    openAddDialog(rec)
  } catch (e) {
    ui.notifyError('収録音声の保存に失敗しました: ' + e.message)
  } finally {
    finalizing.value = false
  }
}
</script>

<style scoped>
/* 波形の上にカウントダウンの数字を重ねる */
.waveform-wrap {
  position: relative;
  max-width: 100%;
}
.countdown-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  font-weight: 900;
  color: #fff;
  text-shadow: 0 0 12px rgba(0, 0, 0, 0.8);
  pointer-events: none;
}

/* チャット対話モードの質問吹き出し */
.chat-bubble {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-top-left-radius: 4px !important;
  flex: 1;
  line-height: 1.7;
}
</style>
