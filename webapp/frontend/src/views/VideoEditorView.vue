<template>
  <v-container fluid class="pa-0 editor-root-container" style="height: 100vh; display: flex; flex-direction: column;">
    <!-- ─── エディタトップヘッダー ─── -->
    <v-toolbar density="compact" class="glass-panel editor-top-bar px-2" color="transparent">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        title="プロジェクト画面へ戻る"
        @click="$router.back()"
      />
      <v-btn
        :icon="sidebarOpen ? 'mdi-dock-left' : 'mdi-dock-window'"
        variant="text"
        size="small"
        :title="sidebarOpen ? 'サイドバーを隠す (Ctrl+B)' : 'サイドバーを表示 (Ctrl+B)'"
        class="mr-2"
        @click="ui.toggleSidebar"
      />
      
      <div class="d-flex align-center gap-2 mr-4">
        <img :src="logoUrl" alt="Logo" class="editor-logo-img" />
        <div>
          <div class="text-subtitle-2 font-weight-bold editor-title text-truncate" style="max-width: 320px;">
            {{ videosStore.currentVideo?.name ?? '動画編集' }}
          </div>
        </div>
      </div>

      <div class="d-flex align-center gap-2">
        <!-- 動画ステータスバッジ -->
        <v-chip
          :color="statusColor(videosStore.currentVideo?.status)"
          size="x-small"
          class="font-weight-bold px-2"
          variant="flat"
        >
          <span v-if="videosStore.currentVideo?.status === 'generating'" class="status-pulse-dot mr-1"></span>
          {{ videoStatusLabel(videosStore.currentVideo?.status) }}
        </v-chip>

        <!-- 再生時間バッジ -->
        <v-chip size="x-small" variant="tonal" color="info" v-if="videosStore.currentVideo?.duration_sec">
          <v-icon size="12" class="mr-1">mdi-timer-outline</v-icon>
          {{ videosStore.currentVideo.duration_sec.toFixed(1) }}s
        </v-chip>
      </div>

      <v-spacer />

      <!-- ヘッダークイックガイド -->
      <div class="text-caption text-medium-emphasis mr-2 d-none d-md-flex align-center">
        <v-icon size="14" color="#06b6d4" class="mr-1">mdi-movie-edit-outline</v-icon>
        Studio Timeline Editor
      </div>
    </v-toolbar>

    <!-- ─── 制作ワークフロー・ステッパータブ ─── -->
    <v-tabs
      v-model="activeTab"
      @update:model-value="onUserTabChange"
      class="editor-stepper-tabs glass-panel"
      bg-color="transparent"
      density="comfortable"
      color="primary"
    >
      <v-tab value="scenario" class="stepper-tab">
        <span class="step-num">1</span>
        <v-icon size="16" class="mr-1">mdi-script-text-outline</v-icon>
        <span>シナリオ作成</span>
      </v-tab>
      <v-tab value="scenes" class="stepper-tab">
        <span class="step-num">2</span>
        <v-icon size="16" class="mr-1">mdi-view-carousel-outline</v-icon>
        <span>シーン編集</span>
      </v-tab>
      <v-tab value="style" class="stepper-tab">
        <span class="step-num">3</span>
        <v-icon size="16" class="mr-1">mdi-palette-outline</v-icon>
        <span>デザインスタイル</span>
      </v-tab>
      <v-tab value="output" class="stepper-tab">
        <span class="step-num">4</span>
        <v-icon size="16" class="mr-1">mdi-movie-play-outline</v-icon>
        <span>動画レンダリング出力</span>
      </v-tab>
    </v-tabs>

    <!-- 初期データ読み込み中（チラつき防止） -->
    <div v-if="initialLoading" class="d-flex flex-column align-center justify-center py-16" style="flex: 1;">
      <v-progress-circular indeterminate size="48" width="3" color="primary" class="mb-4" />
      <span class="text-body-2 text-medium-emphasis">プロジェクトデータを読み込み中...</span>
    </div>

    <!-- タブコンテンツ -->
    <v-window v-else v-model="activeTab" style="flex: 1; overflow-y: auto;">
      <!-- シナリオタブ -->
      <v-window-item value="scenario">
        <v-container class="pa-6" max-width="960">
          <div class="mb-6 text-center">
            <h2 class="text-h6 font-weight-bold mb-2">動画シナリオの作成・生成</h2>
            <p class="text-body-2 text-medium-emphasis">動画のシナリオを作成・解析する方法を以下から選択してください。</p>
            
            <v-btn-toggle
              v-model="scenarioRoute"
              mandatory
              color="primary"
              variant="outlined"
              class="mt-4 glass-card"
            >
              <v-btn value="pptx" prepend-icon="mdi-presentation">PPTXから取り込む</v-btn>
              <v-btn value="text" prepend-icon="mdi-text-box-plus-outline">テキスト貼り付け</v-btn>
              <v-btn value="chat" prepend-icon="mdi-chat-processing-outline">AIチャットで作成</v-btn>
            </v-btn-toggle>
          </div>

          <!-- 各ルートのコンポーネント -->
          <v-card class="mb-6 glass-card overflow-hidden">
            <ScenarioRouteA v-if="scenarioRoute === 'pptx'" :video-id="videoId" @finalized="onScenarioFinalized" />
            <ScenarioRouteB v-if="scenarioRoute === 'text'" :video-id="videoId" @finalized="onScenarioFinalized" />
            <ScenarioRouteC v-if="scenarioRoute === 'chat'" :video-id="videoId" @finalized="onScenarioFinalized" />
          </v-card>

          <!-- 確定済みの現在のシナリオ（シーン一覧） -->
          <v-card class="pa-4 glass-card">
            <div class="d-flex align-center justify-between mb-4">
              <span class="text-subtitle-1 font-weight-bold">🎬 現在のシーン構成 ({{ scenesStore.scenes.length }})</span>
              <v-spacer />
              <v-btn
                prepend-icon="mdi-playlist-edit"
                size="small"
                color="secondary"
                variant="outlined"
                @click="activeTab = 'scenes'"
              >
                詳細エディタで編集する
              </v-btn>
            </div>
            
            <v-list class="bg-transparent" v-if="scenesStore.scenes.length">
              <v-card
                v-for="element in scenesStore.scenes"
                :key="element.id"
                variant="outlined"
                class="mb-3 glass-card border-thin scene-card"
              >
                <v-card-text class="pa-3 d-flex align-center">
                  <!-- ミニサムネイル -->
                  <div class="scene-thumb rounded flex-shrink-0 mr-3" :class="`thumb-${element.layout_type}`">
                    <v-icon size="16" color="white">{{ layoutIcon(element.layout_type) }}</v-icon>
                  </div>

                  <div class="flex-grow-1 min-width-0">
                    <div class="d-flex align-center mb-1">
                      <span class="text-caption font-weight-bold text-primary mr-2">Scene {{ element.index }}</span>
                      <v-chip
                        :color="layoutColor(element.layout_type)"
                        size="x-small"
                        label
                        variant="flat"
                        class="px-1"
                        style="font-size: 9px; height: 16px;"
                      >
                        {{ layoutLabel(element.layout_type) }}
                      </v-chip>
                    </div>
                    <div class="text-subtitle-2 font-weight-bold text-truncate">{{ element.title || '無題のシーン' }}</div>
                  </div>
                  <v-btn icon="mdi-delete-outline" color="error" variant="text" size="small" class="ml-2" @click.stop="handleDeleteScene(element.id)" />
                </v-card-text>
              </v-card>
            </v-list>
            <div v-else class="text-center py-8 text-medium-emphasis text-caption">
              現在、シーンはありません。上のいずれかの方法でシナリオを作成・生成してください。
            </div>
          </v-card>
        </v-container>
      </v-window-item>

      <!-- シーンタブ -->
      <v-window-item value="scenes" style="height: 100%;">
        <v-row no-gutters style="height: 100%;">
          <!-- 左側: シーン一覧 (タイムライン) -->
          <v-col cols="12" md="4" class="border-e d-flex flex-column cyber-scenes-col" style="height: 100%; max-height: calc(100vh - 112px);">
            <!-- 動画全体の共通設定カード -->
            <div class="pa-3 border-b glass-panel-compact">
              <div class="d-flex align-center justify-space-between mb-2">
                <span class="text-caption font-weight-bold d-flex align-center gap-1 text-white">
                  <v-icon size="15" color="#f59e0b">mdi-tune-vertical</v-icon>
                  この動画の共通設定
                </span>
                <v-btn
                  to="/settings"
                  target="_blank"
                  size="x-small"
                  variant="text"
                  color="medium-emphasis"
                  class="px-1 text-caption text-none"
                  append-icon="mdi-open-in-new"
                  title="話者の追加や音声の録音は設定画面で行います"
                >
                  話者管理
                </v-btn>
              </div>

              <!-- 話者が未登録の場合のアラート -->
              <div v-if="!speakersStore.speakers.length" class="text-caption text-warning mb-2 d-flex align-center gap-1 pa-1 rounded" style="background: rgba(245, 158, 11, 0.1);">
                <v-icon size="14" color="warning">mdi-alert-circle-outline</v-icon>
                <span>話者が未登録です。<router-link to="/settings" class="text-warning font-weight-bold text-decoration-underline">設定で追加</router-link></span>
              </div>

              <v-row dense class="button-gap-row mb-2">
                <v-col cols="6">
                  <v-select
                    v-model="videoDefaultNarrationLength"
                    :items="videoNarrationLengthOptions"
                    label="既定の長さ"
                    density="compact"
                    hide-details
                    variant="outlined"
                    class="compact-select text-caption"
                    @update:model-value="onVideoDefaultNarrationLengthChange"
                  />
                </v-col>
                <v-col cols="6">
                  <v-select
                    v-model="defaultSpeakerId"
                    :items="speakerOptions.filter(o => o.value !== null)"
                    label="既定の話者"
                    density="compact"
                    hide-details
                    variant="outlined"
                    class="compact-select text-caption"
                    @update:model-value="onDefaultSpeakerChange"
                  />
                </v-col>
              </v-row>

              <!-- 対話(chat_dialog)シーンがある場合のみ表示する既定話者B -->
              <div v-if="hasChatDialogInVideo" class="mb-2">
                <v-select
                  v-model="defaultSpeakerBId"
                  :items="speakerOptions.filter(o => o.value !== null)"
                  label="既定の話者 B (対話用)"
                  density="compact"
                  hide-details
                  variant="outlined"
                  class="compact-select text-caption"
                  hint="chat_dialog シーンの B 役に適用される動画既定値"
                  @update:model-value="onDefaultSpeakerBChange"
                />
              </div>

              <!-- 左ペイン大型ボタン: 「⚡ AI で全生成」 (暖色・スピード感・2周り大型) -->
              <v-btn
                block
                height="60"
                class="btn-bulk-generate-main rich-action-btn mt-1"
                :loading="scenesStore.bulkGenLoading"
                :disabled="!scenesStore.scenes.length"
                @click="openBulkGenConfirmDialog"
              >
                <!-- スピード感のある暖色AI背景画像レイヤー (パーティクルフリー・光のライン) -->
                <div class="btn-bulk-bg-wrap">
                  <img :src="btnBulkGenerateBgUrl" alt="" class="btn-bulk-bg-img" />
                  <div class="btn-bulk-bg-overlay"></div>
                </div>

                <div class="d-flex align-center justify-center w-100 btn-bulk-content">
                  <v-icon size="26" color="#fef08a" class="mr-2 icon-pulse">mdi-lightning-bolt</v-icon>
                  <div class="d-flex flex-column text-left">
                    <span class="btn-bulk-title">⚡ AI で全シーンを一括生成</span>
                    <span class="btn-bulk-subtitle">全スライド＆ナレーションを高速自動構築</span>
                  </div>
                </div>
              </v-btn>
            </div>

            <!-- シーン構成ヘッダー -->
            <div class="pa-3 border-b d-flex justify-between align-center glass-panel">
              <div class="d-flex align-center gap-2">
                <v-icon size="16" color="#06b6d4">mdi-view-sequential-outline</v-icon>
                <span class="text-caption font-weight-bold text-white">シーン構成</span>
                <v-chip size="x-small" color="cyan" variant="tonal" class="font-weight-bold px-2">
                  {{ scenesStore.scenes.length }}
                </v-chip>
              </div>
              <v-spacer />
              <v-btn
                prepend-icon="mdi-plus"
                size="small"
                color="primary"
                variant="flat"
                class="font-weight-bold px-3 btn-add-scene"
                @click="handleAddScene"
              >
                シーン追加
              </v-btn>
            </div>
            
            <div class="overflow-y-auto flex-grow-1 pa-3 cyber-scenes-list-container">
              <v-list class="bg-transparent" v-if="scenesStore.scenes.length">
                <!-- ドラッグ＆ドロップ -->
                <draggable
                  v-model="scenesStore.scenes"
                  item-key="id"
                  handle=".drag-handle"
                  @end="onDragEnd"
                  class="v-list"
                >
                  <template #item="{ element, index }">
                    <v-card
                      variant="flat"
                      class="mb-3 drag-item glass-card scene-card cursor-pointer"
                      :class="{ 'scene-card-selected': selectedScene?.id === element.id }"
                      @click="selectScene(element)"
                    >
                      <v-card-text class="pa-3 d-flex align-center">
                        <v-icon class="drag-handle cursor-grab flex-shrink-0 mr-2" color="medium-emphasis" size="18">mdi-drag</v-icon>

                        <!-- ミニサムネイル -->
                        <div class="scene-thumb rounded flex-shrink-0 mr-3" :class="`thumb-${element.layout_type}`">
                          <v-icon size="18" color="white">{{ layoutIcon(element.layout_type) }}</v-icon>
                        </div>

                        <!-- テキスト情報 -->
                        <div class="flex-grow-1 min-width-0">
                          <div class="d-flex align-center mb-1">
                            <span
                              class="text-caption font-weight-bold mr-2"
                              :class="selectedScene?.id === element.id ? 'text-primary' : 'text-medium-emphasis'"
                            >
                              Scene {{ element.index }}
                            </span>
                            <v-chip
                              :color="layoutColor(element.layout_type)"
                              size="x-small"
                              label
                              variant="flat"
                              class="px-1"
                              style="font-size: 9px; height: 16px;"
                            >
                              {{ layoutLabel(element.layout_type) }}
                            </v-chip>

                            <!-- 音声崩れ警告アイコン (#63) -->
                            <v-tooltip
                              v-if="element.narration_audio_warning"
                              location="top"
                              max-width="320"
                            >
                              <template #activator="{ props: tooltipProps }">
                                <v-icon
                                  v-bind="tooltipProps"
                                  color="warning"
                                  size="16"
                                  class="ml-1 cursor-help"
                                  @click.stop
                                >
                                  mdi-alert
                                </v-icon>
                              </template>
                              <span class="text-caption">{{ element.narration_audio_warning }}</span>
                            </v-tooltip>
                          </div>
                          <div class="text-subtitle-2 font-weight-bold text-truncate" :title="element.title || '無題のシーン'">
                            {{ element.title || '無題のシーン' }}
                          </div>
                        </div>

                        <!-- 操作ボタン -->
                        <div class="d-flex flex-column align-center flex-shrink-0 ml-2">
                          <v-btn icon="mdi-chevron-up" variant="text" density="compact" size="small"
                            :disabled="index === 0" @click.stop="moveIndex(element, index, -1)" />
                          <v-btn icon="mdi-chevron-down" variant="text" density="compact" size="small"
                            :disabled="index === scenesStore.scenes.length - 1" @click.stop="moveIndex(element, index, 1)" />
                        </div>
                        <v-btn icon="mdi-delete-outline" color="error" variant="text" size="small" class="ml-1"
                          @click.stop="handleDeleteScene(element.id)" />
                      </v-card-text>
                    </v-card>
                  </template>
                </draggable>
              </v-list>
              <div v-else class="text-center py-16 text-medium-emphasis">
                シーンがありません。追加ボタンから作成してください。
              </div>
            </div>
          </v-col>

          <!-- 右側: シーン詳細編集 -->
          <v-col cols="12" md="8" class="pa-6 overflow-y-auto" style="height: 100%; max-height: calc(100vh - 112px);">
            <div v-if="selectedScene" class="d-flex flex-column gap-4 pb-16">
              <div class="d-flex align-center mb-2">
                <span class="text-h6 font-weight-bold">シーン詳細 (Scene {{ selectedScene.index }})</span>
              </div>
              <!-- 処理中インジケーター -->
              <div v-if="processingLabel" class="d-flex align-center gap-2 mb-3 text-body-2 text-medium-emphasis">
                <v-progress-circular size="14" width="2" indeterminate color="primary" />
                <span>{{ processingLabel }}</span>
              </div>

              <!-- 一括生成中の編集制限案内（#85） -->
              <v-alert
                v-if="scenesStore.bulkGenLoading"
                type="info"
                variant="tonal"
                density="comfortable"
                icon="mdi-information-outline"
                class="mb-3"
              >
                <div class="font-weight-bold">一括生成中のため編集できません</div>
                <div class="text-caption">完了したシーンから順に反映されます。シーンを切り替えて閲覧することは可能です。</div>
              </v-alert>

              <!-- 音声崩れ警告（#57, #63） -->
              <v-alert
                v-if="selectedScene?.narration_audio_warning"
                type="warning"
                variant="tonal"
                density="compact"
                icon="mdi-alert"
                class="mb-3 text-caption"
              >
                <div class="font-weight-bold mb-1">音声に関する警告</div>
                <div>{{ selectedScene.narration_audio_warning }}</div>
              </v-alert>

              <fieldset
                :disabled="scenesStore.bulkGenLoading"
                :style="scenesStore.bulkGenLoading ? 'opacity: 0.7; pointer-events: none;' : ''"
                style="border: none; padding: 0; margin: 0; min-width: 0;"
              >
                <!-- ─── 基本情報カード（特別扱い・設定帯） ─── -->
                <v-card class="pa-4 mb-4 glass-card basic-info-special-card overflow-hidden position-relative">
                  <!-- 背景画像 + オーバーレイ -->
                  <div class="basic-info-bg-wrap">
                    <img :src="cardBasicInfoBgUrl" alt="" class="basic-info-bg-img" />
                    <div class="basic-info-bg-overlay"></div>
                  </div>

                  <div class="basic-info-content position-relative">
                    <!-- ヘッダー部 -->
                    <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-2">
                      <div class="d-flex align-center gap-2">
                        <v-chip color="primary" size="small" variant="flat" class="font-weight-bold">
                          Scene {{ selectedScene?.index }}
                        </v-chip>
                        <h3 class="text-h6 font-weight-bold text-white mb-0">基本情報</h3>
                      </div>
                      <v-chip v-if="editForm.layout_pinned" size="small" color="secondary" variant="tonal" class="d-flex align-center gap-1">
                        <v-icon size="12">mdi-pin</v-icon>
                        見せ方固定中
                      </v-chip>
                      <v-chip v-else size="small" color="info" variant="tonal" class="d-flex align-center gap-1">
                        <v-icon size="12">mdi-dice-5-outline</v-icon>
                        見せ方おまかせ
                      </v-chip>
                    </div>

                    <!-- シーンタイトル -->
                    <v-text-field
                      v-model="editForm.title"
                      label="シーンタイトル"
                      density="comfortable"
                      variant="outlined"
                      class="mb-3"
                      :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                    />

                    <!-- あらすじ（意図）: 常に表示し、readonly 解除 -->
                    <v-textarea
                      v-model="editForm.outline_summary"
                      label="あらすじ（意図）"
                      rows="2"
                      variant="outlined"
                      density="comfortable"
                      hint="AI がスライド内容やナレーションを作成する際の手がかりになります（空欄でも作成可能）"
                      persistent-hint
                      class="mb-3"
                      :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                    />

                    <!-- 見せ方（レイアウト） -->
                    <div class="mb-3">
                      <div class="d-flex align-center justify-space-between mb-1">
                        <span class="text-caption text-medium-emphasis">見せ方（レイアウト）</span>
                        <v-btn
                          v-if="editForm.layout_pinned"
                          size="x-small"
                          variant="text"
                          color="info"
                          prepend-icon="mdi-restore"
                          :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                          @click="resetLayoutToAuto"
                        >
                          おまかせに戻す
                        </v-btn>
                      </div>
                      <v-btn
                        block variant="outlined" class="justify-start layout-select-btn"
                        :prepend-icon="layoutIcon(editForm.layout_type)"
                        append-icon="mdi-view-grid-plus-outline"
                        :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                        @click="layoutPickerOpen = true"
                      >
                        <span class="text-body-2">{{ layoutLabel(editForm.layout_type) }}</span>
                        <v-chip size="x-small" variant="tonal" class="ml-2">
                          {{ currentTypeDef?.label || '' }}
                        </v-chip>
                        <v-spacer />
                        <v-chip size="x-small" :color="editForm.layout_pinned ? 'secondary' : 'info'" variant="flat" class="mr-1">
                          {{ editForm.layout_pinned ? '固定' : 'おまかせ' }}
                        </v-chip>
                      </v-btn>
                      <div class="text-caption text-medium-emphasis mt-1">
                        {{ currentLayoutDef?.when_to_use || '' }}
                      </div>
                    </div>

                    <LayoutPicker
                      v-model:open="layoutPickerOpen"
                      v-model="editForm.layout_type"
                      :item-count="currentItemCount"
                      :video-id="videoId"
                      @select="handleLayoutSelected"
                    />

                    <!-- layout_reason アラート -->
                    <v-alert
                      v-if="editForm.layout_reason"
                      type="info"
                      variant="tonal"
                      density="compact"
                      class="mb-3 text-caption"
                      icon="mdi-information-outline"
                    >
                      {{ editForm.layout_reason }}
                    </v-alert>

                    <!-- ナレーション長 & 話者 -->
                    <v-row dense class="mb-2 button-gap-row">
                      <v-col cols="12" sm="6">
                        <v-select
                          v-model="editForm.narration_length"
                          :items="sceneNarrationLengthOptions"
                          label="ナレーションの長さ"
                          density="comfortable"
                          variant="outlined"
                          hint="シーン個別の長さ。既定で動画設定を継承します"
                          persistent-hint
                          :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                          @update:model-value="onSceneNarrationLengthChange"
                        />
                      </v-col>
                      <v-col cols="12" sm="6">
                        <v-select
                          v-model="editForm.speaker_id"
                          :items="sceneSpeakerOptions"
                          label="話者"
                          density="comfortable"
                          variant="outlined"
                          hint="シーン個別の話者。既定で動画設定を継承します"
                          persistent-hint
                          :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                          @update:model-value="onSceneSpeakerChange"
                        />
                      </v-col>
                    </v-row>

                    <v-select
                      v-if="editForm.layout_type === 'chat_dialog'"
                      v-model="editForm.speaker_b_id"
                      :items="sceneSpeakerBOptions"
                      label="話者 B (対話の B 役)"
                      density="comfortable"
                      variant="outlined"
                      hint="chat_dialog レイアウトで B ラベルの行を担当する話者。既定で動画設定を継承します"
                      persistent-hint
                      class="mb-3"
                      :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                      @update:model-value="onSceneSpeakerBChange"
                    />

                    <!-- 主ボタン: 「✨ AI でシーン内容を作成」大型リッチボタン -->
                    <div class="mt-4 pt-3 border-t border-opacity-15">
                      <v-btn
                        block
                        size="large"
                        height="48"
                        class="btn-generate-scene-main rich-action-btn"
                        :loading="contentGenLoading"
                        :disabled="contentGenLoading || scenesStore.bulkGenLoading"
                        @click="openGenerateModal"
                      >
                        <img :src="btnGenerateSceneUrl" alt="" class="rich-btn-icon mr-2" />
                        <span class="text-subtitle-1 font-weight-bold">✨ AI でシーン内容を作成</span>
                      </v-btn>
                    </div>
                  </div>
                </v-card>

              <!-- ─── 詳細欄 (折り畳みアコーディオン) ─── -->
              <v-expansion-panels v-model="expandedPanels" multiple class="cyber-expansion-panels mb-4">
                <!-- パネル 1: スライドの内容（生成後に調整） -->
                <v-expansion-panel value="slide" class="glass-card mb-2">
                  <v-expansion-panel-title class="font-weight-bold text-subtitle-2">
                    <div class="d-flex align-center gap-2">
                      <v-icon color="#06b6d4" size="18">mdi-card-text-outline</v-icon>
                      <span>スライドの内容（生成後に調整）</span>
                    </div>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text class="pt-2">
                    <SceneContentForm
                      v-model="slideContent"
                      :type-def="currentTypeDef"
                      :field-notes="currentLayoutDef?.field_notes || {}"
                    />
                    <v-textarea
                      v-if="slideContent.image_prompt_note"
                      v-model="slideContent.image_prompt_note"
                      label="画像の狙い（AI の補足）"
                      rows="2" readonly persistent-hint
                      hint="画像生成 AI に渡した意図の控え"
                      class="mb-3"
                    />
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- パネル 2: ナレーション -->
                <v-expansion-panel value="narration" class="glass-card mb-2">
                  <v-expansion-panel-title class="font-weight-bold text-subtitle-2">
                    <div class="d-flex align-center gap-2">
                      <v-icon color="#a855f7" size="18">mdi-account-voice</v-icon>
                      <span>ナレーション</span>
                    </div>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text class="pt-2">
                    <!-- 選択ツールバー (読み・間) (#74) -->
                    <NarrationToolbar
                      v-if="selectedScene"
                      :scene-id="selectedScene.id"
                      :project-id="videosStore.currentVideo?.project_id"
                      :textarea-el="narrationTextareaEl"
                      v-model="editForm.narration_text"
                      @reading-registered="onReadingRegistered"
                    />

                    <v-textarea
                      ref="narrationTextareaRef"
                      v-model="editForm.narration_text"
                      label="ナレーションテキスト"
                      rows="5"
                      class="mb-2"
                    />

                    <!-- 書式の警告 (#74) -->
                    <v-alert
                      v-if="inspectProblems.length > 0"
                      type="warning"
                      density="compact"
                      variant="tonal"
                      class="mb-2 text-caption"
                    >
                      <div class="font-weight-bold mb-1 d-flex align-center gap-1">
                        <v-icon size="16">mdi-alert-circle-outline</v-icon>
                        <span>書式の警告 ({{ inspectProblems.length }}件)</span>
                      </div>
                      <ul class="pl-4 mb-0">
                        <li v-for="(p, i) in inspectProblems" :key="i">
                          {{ p.line }} 行目 {{ p.column }} 文字目: {{ p.message }}
                        </li>
                      </ul>
                    </v-alert>

                    <div class="d-flex align-center justify-between text-caption mt-1">
                      <span class="text-medium-emphasis">
                        {{ plainNarrationLength }} 文字 &nbsp;/&nbsp; 約 {{ estimatedDuration }} 秒
                      </span>
                      <v-chip
                        :color="narrationChipColor"
                        size="x-small"
                        label
                        variant="tonal"
                      >
                        {{ narrationLengthHint }}
                      </v-chip>
                    </div>

                    <!-- ─── プレビュー音声セクション (#83) ─── -->
                    <div class="preview-audio-section mt-3 pt-3 border-t border-opacity-10">
                      <div class="d-flex align-center flex-wrap gap-2 mb-2">
                        <v-btn
                          :prepend-icon="previewButtonIcon"
                          :color="previewButtonColor"
                          :variant="previewButtonVariant"
                          size="small"
                          :loading="previewLoading"
                          @click="handlePlayPreview"
                        >
                          {{ previewButtonLabel }}
                        </v-btn>
                        <!-- 作成中の進み具合（経過秒数） -->
                        <span v-if="previewLoading" class="text-caption text-medium-emphasis d-flex align-center gap-1">
                          <v-progress-circular size="14" width="2" indeterminate color="primary" />
                          <span>音声合成中... ({{ previewElapsedSec }}秒)</span>
                        </span>
                      </div>

                      <!-- プレビュー音声プレイヤー -->
                      <v-card
                        v-if="scenesStore.previewAudioUrl && !previewLoading"
                        class="pa-3 mb-2 d-flex align-center gap-3 border-primary border-opacity-50 glass-card"
                        rounded
                        style="background: rgba(var(--v-theme-primary), 0.05); border: 1px solid rgb(var(--v-theme-primary));"
                      >
                        <div class="d-flex flex-column" style="min-width: 140px;">
                          <span class="text-caption font-weight-bold text-primary">プレビュー音声</span>
                          <span class="text-caption text-medium-emphasis" v-if="previewAudioDuration">
                            長さ: {{ previewAudioDuration.toFixed(1) }} 秒
                          </span>
                        </div>
                        <audio
                          :src="scenesStore.previewAudioUrl"
                          ref="previewAudioPlayer"
                          controls
                          autoplay
                          style="height: 32px; flex: 1; min-width: 200px;"
                          @loadedmetadata="handleAudioLoaded"
                        />
                      </v-card>

                      <!-- プレビューエラー (手動で閉じるまで消えない永続表示) -->
                      <v-alert
                        v-if="previewError"
                        type="error"
                        variant="tonal"
                        closable
                        density="compact"
                        class="mb-2 text-caption"
                        @click:close="previewError = null"
                      >
                        <div class="font-weight-bold mb-1">プレビュー音声の生成に失敗しました</div>
                        <div style="white-space: pre-wrap; word-break: break-all;">{{ previewError }}</div>
                      </v-alert>
                    </div>

                    <!-- 読みの確認欄 (#64, #74) -->
                    <SceneReadingChecker
                      ref="readingCheckerRef"
                      v-if="selectedScene"
                      :scene="selectedScene"
                      :project-id="videosStore.currentVideo?.project_id"
                      :current-narration="editForm.narration_text"
                      @update:narration="val => { editForm.narration_text = val }"
                    />
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- パネル 3: 画像・アセット -->
                <v-expansion-panel value="assets" class="glass-card mb-2">
                  <v-expansion-panel-title class="font-weight-bold text-subtitle-2">
                    <div class="d-flex align-center gap-2">
                      <v-icon color="#ec4899" size="18">mdi-image-multiple-outline</v-icon>
                      <span>画像・アセット</span>
                    </div>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text class="pt-2">
                    <div class="d-flex align-center justify-between mb-2">
                      <span class="text-subtitle-2 font-weight-bold">画像生成プロンプト</span>
                      <v-btn prepend-icon="mdi-image-plus" size="small" color="secondary" variant="outlined"
                             :loading="imagePromptLoading" @click="generateImagePrompt">
                        AI でプロンプトを生成
                      </v-btn>
                    </div>
                    <div class="text-caption text-medium-emphasis mb-3">
                      生成したプロンプトを画像生成AIに貼り付け、できた画像を下の「アセット」から
                      アップロードするとスライドに反映されます。
                    </div>

                    <template v-if="selectedScene?.image_prompt">
                      <v-textarea :model-value="selectedScene.image_prompt" readonly rows="4"
                                  class="font-mono mb-2" density="compact" hide-details />
                      <div class="d-flex align-center gap-2 mb-3">
                        <v-btn size="small" color="primary" prepend-icon="mdi-content-copy" @click="copyImagePrompt">
                          プロンプトをコピー
                        </v-btn>
                        <span v-if="slideContent.image_prompt_note" class="text-caption text-medium-emphasis">
                          {{ slideContent.image_prompt_note }}
                        </span>
                      </div>
                    </template>
                    <div v-else class="text-caption text-medium-emphasis py-2 mb-3">
                      まだ生成されていません。「AI でプロンプトを生成」を押してください。
                    </div>

                    <SceneAssetSlot
                      v-if="selectedScene"
                      :scene-id="selectedScene.id"
                      :slot-count="assetSlotCount"
                      :show-captions="isMediaLayout"
                      :captions="slotCaptions"
                      @update:captions="applySlotCaptions"
                    />
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- パネル 4: AI デザイン調整 -->
                <v-expansion-panel value="design" class="glass-card mb-2">
                  <v-expansion-panel-title class="font-weight-bold text-subtitle-2">
                    <div class="d-flex align-center gap-2">
                      <v-icon color="#10b981" size="18">mdi-palette-outline</v-icon>
                      <span>AI デザイン調整</span>
                    </div>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text class="pt-2">
                    <div class="d-flex gap-2 align-center">
                      <v-text-field v-model="designPrompt" placeholder="例: グラフをもっと大きく、背景に光の演出を追加して" hide-details density="compact" />
                      <v-btn color="secondary" :loading="applyingDesign" @click="applyDesignAdjust">AI で調整</v-btn>
                    </div>
                    <div v-if="selectedScene?.custom_html" class="text-caption text-medium-emphasis mt-2 d-flex align-center">
                      <v-icon size="14" class="mr-1">mdi-pencil</v-icon> このシーンはカスタムコードで上書きされています
                      <v-spacer />
                      <v-btn size="x-small" variant="text" color="warning" @click="resetSceneCustomCode">自動生成に戻す</v-btn>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- パネル 5: コードを表示・編集（上級者向け） -->
                <v-expansion-panel value="code" class="glass-card mb-2">
                  <v-expansion-panel-title class="font-weight-bold text-subtitle-2">
                    <div class="d-flex align-center gap-2">
                      <v-icon color="#6366f1" size="18">mdi-code-tags</v-icon>
                      <span>コード編集（上級者向け）</span>
                    </div>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text class="pt-2">
                    <div class="d-flex align-center justify-end mb-2 gap-2">
                      <v-btn size="small" variant="text" @click="loadSceneCode">読み込み</v-btn>
                      <v-btn size="small" variant="text" @click="codeEditMode = !codeEditMode">
                        {{ codeEditMode ? '編集中' : '編集する' }}
                      </v-btn>
                    </div>
                    <v-textarea v-model="codeHtml" label="HTML" rows="6" class="font-mono mb-2" :readonly="!codeEditMode" density="compact" />
                    <v-textarea v-model="codeCss" label="CSS (このシーン専用、任意)" rows="4" class="font-mono mb-3" :readonly="!codeEditMode" density="compact" />
                    <div class="d-flex gap-2">
                      <v-btn size="small" color="primary" :disabled="!codeEditMode" @click="applySceneCode">適用</v-btn>
                      <v-btn size="small" variant="outlined" @click="refreshCodePreview">プレビューを更新</v-btn>
                    </div>
                    <iframe v-if="codePreviewUrl" :src="codePreviewUrl" style="width:100%; height:360px; border:1px solid rgba(255,255,255,0.1); margin-top:12px; border-radius:6px;" />
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
              </fieldset>
            </div>
            <div v-else class="text-center py-16 text-medium-emphasis">
              左側のシーン一覧から編集するシーンを選択してください。
            </div>
          </v-col>
        </v-row>

        <!-- ─── シーン詳細 フロート操作バー (プレビュー & 保存) (#84) ─── -->
        <div
          v-if="selectedScene"
          class="scene-floating-actions"
        >
          <v-btn
            prepend-icon="mdi-eye"
            color="secondary"
            variant="elevated"
            class="floating-action-btn font-weight-bold"
            :loading="sceneModalPreviewLoading"
            :disabled="scenesStore.bulkGenLoading"
            @click="handleSceneModalPreview"
          >
            プレビュー
          </v-btn>
          <v-badge
            :model-value="hasUnsavedSceneChanges"
            color="warning"
            dot
            floating
            offset-x="4"
            offset-y="4"
          >
            <v-btn
              prepend-icon="mdi-content-save"
              color="success"
              variant="elevated"
              class="floating-action-btn font-weight-bold"
              :loading="saveLoading"
              :disabled="saveLoading || scenesStore.bulkGenLoading"
              @click="handleSaveScene"
            >
              保存
            </v-btn>
          </v-badge>
        </div>
      </v-window-item>



      <!-- スタイルタブ -->
      <v-window-item value="style">
        <StyleConfigTab :video-id="videoId" />
      </v-window-item>

      <!-- 出力タブ -->
      <v-window-item value="output">
        <v-container class="pa-6">
          <!-- 生成ステータス -->
          <v-card class="pa-6 mb-6 glass-card">
            <div class="d-flex align-center mb-4">
              <div>
                <h3 class="text-h6 font-weight-bold">動画の生成</h3>
                <p class="text-body-2 text-medium-emphasis">シーン音声の合成、タイムライン計算、動画レンダリングを一括実行します。</p>
              </div>
              <v-spacer />
              <v-btn
                color="secondary"
                size="large"
                prepend-icon="mdi-monitor-eye"
                variant="outlined"
                class="mr-3"
                :loading="slidePreviewLoading"
                @click="handleSlidePreview"
              >
                スライドプレビュー
              </v-btn>
              <v-btn
                v-if="isGenerating"
                color="error"
                size="large"
                prepend-icon="mdi-stop-circle-outline"
                variant="tonal"
                class="mr-3"
                :loading="generationStore.loading"
                @click="handleCancelGeneration"
              >
                生成を中止
              </v-btn>
              <v-btn
                color="primary"
                size="large"
                prepend-icon="mdi-play-circle"
                :disabled="isGenerating"
                @click="openGenerateDialog"
              >
                動画を生成
              </v-btn>
            </div>

            <!-- 生成オプションダイアログ -->
            <v-dialog v-model="generateDialog" max-width="520">
              <v-card class="glass-card">
                <v-card-title class="pa-4 text-h6">動画の生成</v-card-title>
                <v-card-text class="pa-4 pt-0">
                  <v-checkbox
                    v-model="generateOptions.regenerateAudio"
                    color="primary"
                    hide-details
                    label="音声を再作成する"
                  />
                  <div class="text-caption text-medium-emphasis mt-1 ml-8">
                    内容・話者・参照音声が変わったシーンは、指定しなくても作り直されます。
                    声の出来が気に入らないなど、それ以外の理由で全シーンを合成し直したいときに指定してください。
                    <br />
                    チェックしない場合は、内容が変わっていないシーンの音声を再利用して高速に生成します。
                  </div>
                  <v-alert
                    v-if="generateOptions.regenerateAudio"
                    type="info"
                    variant="tonal"
                    density="compact"
                    class="mt-3 text-caption"
                  >
                    全シーンの音声を合成し直すため、生成に時間がかかります。
                  </v-alert>
                </v-card-text>
                <v-card-actions class="pa-4 d-flex justify-end">
                  <v-btn variant="text" @click="generateDialog = false">キャンセル</v-btn>
                  <v-btn color="primary" :loading="generationStore.loading" @click="handleGenerate">
                    生成を開始
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-dialog>

            <!-- 進捗表示 -->
            <div v-if="generationStore.currentProgress" class="mt-4 border-t pt-4">
              <div class="d-flex align-center mb-2 flex-wrap gap-2">
                <span
                  class="text-subtitle-2 font-weight-bold"
                  :class="generationStore.currentProgress.status === 'failed' ? 'text-error' : (generationStore.currentProgress.status === 'cancelled' ? 'text-medium-emphasis' : '')"
                >
                  ステータス: {{ getProgressStepLabel(generationStore.currentProgress) }}
                </span>
                <v-spacer />
                <div class="d-flex align-center text-caption text-medium-emphasis">
                  <span v-if="generationStore.currentProgress.elapsed_sec != null">
                    経過時間: {{ formatDurationSeconds(generationStore.currentProgress.elapsed_sec) }}
                  </span>
                  <span v-if="generationStore.currentProgress.stage_eta_sec != null" class="ml-3">
                    この段階の残り 約 {{ formatDurationSeconds(generationStore.currentProgress.stage_eta_sec) }}
                  </span>
                  <span class="ml-3 font-weight-bold">
                    {{ (generationStore.currentProgress.progress * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
              <v-progress-linear
                :model-value="generationStore.currentProgress.progress * 100"
                :color="generationStore.currentProgress.status === 'failed' ? 'error' : (generationStore.currentProgress.status === 'cancelled' ? 'grey' : 'primary')"
                height="10"
                :striped="isGenerating && generationStore.currentProgress?.progress < 1.0"
                rounded
              />
              <v-alert
                v-if="generationStore.currentProgress.status === 'failed'"
                type="error"
                variant="tonal"
                class="mt-3"
                density="compact"
              >
                {{ generationStore.currentProgress.error || generationStore.currentProgress.message || '動画生成中にエラーが発生しました。' }}
              </v-alert>
              <v-alert
                v-else-if="generationStore.currentProgress.status === 'cancelled'"
                type="info"
                variant="tonal"
                class="mt-3"
                density="compact"
              >
                動画の生成を中止しました。
              </v-alert>
              <v-alert
                v-else-if="generationStore.currentProgress.status === 'completed'"
                type="success"
                variant="tonal"
                class="mt-3"
                density="compact"
              >
                動画の生成が正常に完了しました！生成履歴からプレビュー・再生できます。
              </v-alert>

              <!-- 音声崩れ警告（#57, #63）: 完了した回の履歴にあるときだけ出す（生成中は前回の警告を出さない） -->
              <v-alert
                v-if="!isGenerating && latestAudioWarnings.length"
                type="warning"
                variant="tonal"
                class="mt-3 text-caption"
                density="compact"
                icon="mdi-alert"
              >
                <div class="font-weight-bold mb-1">
                  {{ latestAudioWarnings.map(w => `シーン ${w.scene_index}`).join('、') }} の音声が崩れている可能性があります。シーン編集で音声を作り直してください。
                </div>
                <div v-for="w in latestAudioWarnings" :key="w.scene_id" class="text-caption text-medium-emphasis">
                  ・シーン {{ w.scene_index }}（{{ w.title }}）: {{ w.message }}
                </div>
              </v-alert>

              <!-- 段階の文言は常に出す -->
              <p v-if="generationStore.currentProgress.message" class="text-body-2 mt-2 text-medium-emphasis">
                {{ generationStore.currentProgress.message }}
              </p>

              <!-- レンダリング待ちの間に流す下見。
                   音声もBGMも無いアニメーションだけを 1 周だけ再生する。
                   出来上がりを待つ間に「何が出来てくるか」が見えるようにするもの。 -->
              <div v-if="generationStore.previewUrl" class="mt-4">
                <div class="d-flex align-center mb-2">
                  <v-icon size="16" class="mr-2">mdi-play-box-outline</v-icon>
                  <span class="text-caption font-weight-medium">仕上がりの下見</span>
                  <v-spacer />
                  <span class="text-caption text-medium-emphasis">音声・BGM なし</span>
                </div>
                <div class="preview-frame">
                  <iframe
                    :src="generationStore.previewUrl"
                    title="仕上がりの下見"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                  />
                </div>
              </div>
            </div>
          </v-card>

          <!-- 履歴 -->
          <v-card class="pa-4 glass-card">
            <v-card-title class="font-weight-bold px-2 mb-4">生成履歴</v-card-title>
            <v-table v-if="generationStore.histories.length">
              <thead>
                <tr>
                  <th>サムネイル</th>
                  <th>開始時間</th>
                  <th>ステータス</th>
                  <th>動画尺</th>
                  <th>ファイルサイズ</th>
                  <th class="text-right">アクション</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="h in generationStore.histories" :key="h.id">
                  <td style="width: 80px;">
                    <img
                      v-if="h.thumbnail_path"
                      :src="`/${h.thumbnail_path}`"
                      style="width: 72px; height: 40px; object-fit: cover; border-radius: 6px;"
                      :alt="`thumbnail-${h.id}`"
                    />
                    <div
                      v-else
                      style="width: 72px; height: 40px; background: rgba(128,128,128,0.2); border-radius: 6px; display: flex; align-items: center; justify-content: center;"
                    >
                      <v-icon size="18" color="grey">mdi-image-off</v-icon>
                    </div>
                  </td>
                  <td>{{ formatDate(h.started_at) }}</td>
                  <td>
                    <div class="d-flex align-center gap-1 flex-wrap">
                      <v-tooltip v-if="h.status === 'failed' && h.error_message" location="top" max-width="360">
                        <template #activator="{ props: tooltipProps }">
                          <v-chip
                            v-bind="tooltipProps"
                            :color="statusColor(h.status)"
                            size="x-small"
                            class="font-weight-bold cursor-help"
                          >
                            {{ historyStatusLabel(h.status) }}
                            <v-icon end size="12">mdi-help-circle-outline</v-icon>
                          </v-chip>
                        </template>
                        <span class="text-caption">{{ h.error_message }}</span>
                      </v-tooltip>
                      <v-chip
                        v-else
                        :color="statusColor(h.status)"
                        size="x-small"
                        class="font-weight-bold"
                      >
                        {{ historyStatusLabel(h.status) }}
                      </v-chip>
                      <v-tooltip v-if="h.audio_warnings?.length" location="top" max-width="320">
                        <template #activator="{ props: tooltipProps }">
                          <v-chip
                            v-bind="tooltipProps"
                            color="warning"
                            size="x-small"
                            variant="tonal"
                            class="cursor-help"
                            prepend-icon="mdi-alert"
                          >
                            音声警告 ({{ h.audio_warnings.length }})
                          </v-chip>
                        </template>
                        <div class="text-caption">
                          <div v-for="w in h.audio_warnings" :key="w.scene_id">
                            ・シーン {{ w.scene_index }}: {{ w.message }}
                          </div>
                        </div>
                      </v-tooltip>
                    </div>
                  </td>
                  <td>{{ h.duration_sec ? `${h.duration_sec.toFixed(1)} 秒` : '-' }}</td>
                  <td>{{ h.file_size_bytes ? formatBytes(h.file_size_bytes) : '-' }}</td>
                  <td class="text-right">
                    <v-btn
                      v-if="h.status === 'completed'"
                      prepend-icon="mdi-play-circle"
                      color="primary"
                      variant="outlined"
                      size="small"
                      class="mr-2"
                      @click="openVideoPlayer(h.id)"
                    >
                      再生
                    </v-btn>
                    <v-btn
                      v-if="h.status === 'completed'"
                      prepend-icon="mdi-download"
                      color="success"
                      variant="flat"
                      size="small"
                      :href="generationStore.downloadUrl(h.id)"
                      target="_blank"
                    >
                      ダウンロード
                    </v-btn>
                    <v-btn
                      v-if="h.status === 'completed'"
                      prepend-icon="mdi-subtitles-outline"
                      color="secondary"
                      variant="outlined"
                      size="small"
                      class="ml-2"
                      :href="`/api/v1/generations/${h.id}/subtitle.srt`"
                      target="_blank"
                    >
                      字幕 SRT
                    </v-btn>
                    <v-btn
                      v-if="h.status !== 'running'"
                      icon="mdi-delete-outline"
                      color="error"
                      variant="text"
                      size="small"
                      class="ml-2"
                      @click="confirmDeleteHistory(h)"
                    />
                  </td>
                </tr>
              </tbody>
            </v-table>
            <div v-else class="text-center py-8 text-medium-emphasis">
              生成履歴がありません。
            </div>
          </v-card>
        </v-container>
      </v-window-item>
    </v-window>

    <!-- インアプリ動画プレイヤー -->
    <v-dialog v-model="playerDialog" max-width="960" @after-leave="playerSrc = ''">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2">mdi-play-circle</v-icon>
          動画プレビュー
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="playerDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0 bg-black">
          <video
            v-if="playerSrc"
            :src="playerSrc"
            controls
            autoplay
            style="width: 100%; max-height: 70vh; display: block;"
          />
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- スライド HTML プレビュー -->
    <v-dialog
      v-model="slidePreviewDialog"
      max-width="1100"
      @after-leave="slidePreviewUrl = ''"
    >
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2">mdi-monitor-eye</v-icon>
          スライドプレビュー
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="slidePreviewDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0" style="background: #000;">
          <iframe
            v-if="slidePreviewUrl"
            :src="slidePreviewUrl"
            style="width: 100%; aspect-ratio: 16/9; border: none; display: block;"
            title="スライドプレビュー"
          />
        </v-card-text>
        <v-card-actions class="pa-3">
          <span class="text-caption text-medium-emphasis">
            ※ 音声未合成のシーンは無音で表示されます。スライドのレイアウトと文字を確認するためのものです。
          </span>
          <v-spacer />
          <v-btn size="small" variant="text" @click="slidePreviewDialog = false">閉じる</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── シーン画面プレビュー モーダル (#84) ─── -->
    <v-dialog
      v-model="sceneModalPreviewDialog"
      max-width="1100"
      @after-leave="sceneModalPreviewUrl = ''"
    >
      <v-card class="glass-card">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2" color="secondary">mdi-eye</v-icon>
          <span>シーン画面プレビュー {{ selectedScene ? `(Scene ${selectedScene.index})` : '' }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="sceneModalPreviewDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-0" style="background: #000;">
          <iframe
            v-if="sceneModalPreviewUrl"
            :src="sceneModalPreviewUrl"
            style="width: 100%; aspect-ratio: 16/9; border: none; display: block;"
            title="シーン画面プレビュー"
          />
        </v-card-text>
        <v-card-actions class="pa-3 d-flex align-center flex-wrap">
          <span class="text-caption text-medium-emphasis">
            ※ 音声が未合成のシーンは、見積もりの長さで無音で表示されます。
          </span>
          <v-spacer />
          <v-btn size="small" variant="text" @click="sceneModalPreviewDialog = false">閉じる</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── AI でシーン内容を作成 モーダル ─── -->
    <v-dialog v-model="generateModalOpen" max-width="500" persistent>
      <v-card class="glass-card pa-4">
        <v-card-title class="d-flex align-center gap-2 text-h6 font-weight-bold pa-0 mb-3">
          <img :src="btnGenerateSceneUrl" alt="" class="rich-btn-icon" style="width: 28px; height: 28px;" />
          AI でシーン内容を作成
        </v-card-title>
        
        <v-card-text class="pa-0 mb-4">
          <p class="text-body-2 text-medium-emphasis mb-3">
            設定した基本情報（あらすじ、見せ方、長さ、話者）をもとに、シーンの内容を再構築します。
          </p>

          <v-card variant="outlined" class="pa-3 mb-3 border-thin" style="background: rgba(255, 255, 255, 0.03);">
            <div class="text-caption font-weight-bold text-medium-emphasis mb-2">作成する対象を選択してください:</div>
            <v-checkbox
              v-model="generateIncludeSlide"
              label="スライド表示テキスト"
              color="primary"
              density="compact"
              hide-details
              class="mb-1"
            />
            <v-checkbox
              v-model="generateIncludeNarration"
              label="ナレーション"
              color="secondary"
              density="compact"
              hide-details
            />
          </v-card>

          <!-- 上書き注意アラート -->
          <v-alert
            v-if="hasExistingContent"
            type="warning"
            variant="tonal"
            density="compact"
            icon="mdi-alert-outline"
            class="text-caption mb-0"
          >
            入力済みの内容がある場合、チェックを入れた項目は上書きされます。
          </v-alert>
        </v-card-text>

        <v-card-actions class="pa-0 justify-end gap-2">
          <v-btn
            variant="text"
            color="medium-emphasis"
            :disabled="generateModalLoading"
            @click="generateModalOpen = false"
          >
            キャンセル
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            class="px-4 font-weight-bold"
            :loading="generateModalLoading"
            :disabled="!generateIncludeSlide && !generateIncludeNarration"
            @click="executeSceneGenerate"
          >
            作成する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── AI で全生成 確認モーダル ─── -->
    <v-dialog v-model="bulkGenConfirmDialog" max-width="500">
      <v-card class="glass-card pa-4">
        <v-card-title class="d-flex align-center gap-2 text-h6 font-weight-bold pa-0 mb-3">
          <v-icon color="#f59e0b">mdi-lightning-bolt</v-icon>
          ⚡ AI で全シーンを一括生成
        </v-card-title>
        
        <v-card-text class="pa-0 mb-4">
          <p class="text-body-2 mb-3">
            動画全体のすべてのシーンに対して、AI がスライド内容とナレーションを自動生成します。
          </p>

          <v-card variant="outlined" class="pa-3 mb-3 border-thin" style="background: rgba(255, 255, 255, 0.03);">
            <div class="text-caption font-weight-bold text-medium-emphasis mb-2">現在の動画共通設定:</div>
            <div class="d-flex align-center justify-space-between text-body-2 mb-1">
              <span class="text-medium-emphasis">既定の長さ:</span>
              <span class="font-weight-bold text-white">{{ currentVideoLengthLabel }}</span>
            </div>
            <div class="d-flex align-center justify-space-between text-body-2">
              <span class="text-medium-emphasis">既定の話者:</span>
              <span class="font-weight-bold text-white">{{ currentDefaultSpeakerName }}</span>
            </div>
            <div class="text-xxs text-medium-emphasis mt-2">
              ※各シーンで個別の長さや話者が指定されている場合は、シーン個別設定が優先されます。
            </div>
          </v-card>

          <v-radio-group v-model="bulkGenOnlyEmpty" density="compact" hide-details>
            <v-radio :value="true" label="未生成（内容が空）のシーンのみ生成する" color="primary" class="mb-1" />
            <v-radio :value="false" label="すべてのシーンを上書き再生成する" color="warning" />
          </v-radio-group>
        </v-card-text>

        <v-card-actions class="pa-0 justify-end gap-2">
          <v-btn variant="text" color="medium-emphasis" @click="bulkGenConfirmDialog = false">
            キャンセル
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            class="px-4 font-weight-bold"
            :loading="scenesStore.bulkGenLoading"
            @click="executeBulkGen"
          >
            生成を開始
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, watch, computed, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import draggable from 'vuedraggable'
import { useVideosStore } from '@/stores/videos'
import { useScenesStore } from '@/stores/scenes'
import { useSpeakersStore } from '@/stores/speakers'
import { useGenerationStore } from '@/stores/generation'
import StyleConfigTab from '@/components/StyleConfigTab.vue'
import SceneAssetSlot from '@/components/SceneAssetSlot.vue'
import SceneReadingChecker from '@/components/SceneReadingChecker.vue'
import NarrationToolbar from '@/components/NarrationToolbar.vue'
import { readingApi } from '@/api/reading'

import ScenarioRouteA from '@/components/ScenarioRouteA.vue'
import ScenarioRouteB from '@/components/ScenarioRouteB.vue'
import ScenarioRouteC from '@/components/ScenarioRouteC.vue'
import { useScenarioStore } from '@/stores/scenario'
import { scenarioApi } from '@/api/scenario'
import LayoutPicker from '@/components/LayoutPicker.vue'
import SceneContentForm from '@/components/SceneContentForm.vue'
import { useLayoutsStore } from '@/stores/layouts'
import { layoutApi } from '@/api/layout'
import { styleApi } from '@/api/style'
import { useUiStore } from '@/stores/ui'
import { api } from '@/api/index.js'
import logoUrl from '@/assets/logo.jpg'
import cardBasicInfoBgUrl from '@/assets/card_basic_info_bg.jpg'
import btnGenerateSceneUrl from '@/assets/btn_generate_scene.jpg'
import btnBulkGenerateBgUrl from '@/assets/btn_bulk_generate_bg.jpg'

const route = useRoute()
const videoId = route.params.videoId

const videosStore = useVideosStore()
const scenesStore = useScenesStore()
const speakersStore = useSpeakersStore()
const generationStore = useGenerationStore()
const scenarioStore = useScenarioStore()
const ui = useUiStore()
const { sidebarOpen } = storeToRefs(ui)

// 初期表示タブ（データロード完了時にシーン数に応じて自動決定。ロード中はチラつき防止のため未選択）
const activeTab = ref(null)
// 初期データ読み込み中フラグ（チラつき防止）
const initialLoading = ref(true)
// ロード完了前にユーザーが手動でタブ操作したかを追跡するフラグ
const userInteractedTab = ref(false)

// ユーザーの手動タブ操作ハンドラ
const onUserTabChange = () => {
  userInteractedTab.value = true
}
const selectedScene = ref(null)
const previewLoading = ref(false)
const previewError = ref(null)
const previewElapsedSec = ref(0)
const previewAudioDuration = ref(0)
const previewAudioPlayer = ref(null)
const lastPreviewSnapshot = ref(null)
const currentReadingText = ref('')
const playerDialog = ref(false)
const playerSrc = ref('')
const saveLoading = ref(false)
// 動画生成の実行オプション
const generateDialog = ref(false)
const generateOptions = reactive({ regenerateAudio: false })
const defaultSpeakerId = ref(null)
const defaultSpeakerBId = ref(null)
const slidePreviewDialog = ref(false)
const slidePreviewUrl = ref('')
const slidePreviewLoading = ref(false)
const sceneModalPreviewDialog = ref(false)
const sceneModalPreviewUrl = ref('')
const sceneModalPreviewLoading = ref(false)

const scenarioRoute = ref('pptx')
const contentGenLoading = ref(false)

// ─── ナレーションの長さプリセット ───
const narrationLengths = ref([
  { value: 'short', label: '短め', seconds: 15, description: '約 15 秒（約 90 字）。要点だけを伝える。テンポの良い動画に' },
  { value: 'standard', label: '標準', seconds: 30, description: '約 30 秒（約 180 字）。研修動画で扱いやすい長さ。迷ったらこれ' },
  { value: 'long', label: 'やや長め', seconds: 45, description: '約 45 秒（約 270 字）。背景や理由まで説明したいときに' },
  { value: 'extra_long', label: '長め', seconds: 60, description: '約 60 秒（約 360 字）。1 シーンで込み入った話を扱うときに' },
])

const videoDefaultNarrationLength = ref('standard')

const videoNarrationLengthOptions = computed(() => {
  return narrationLengths.value.map(item => ({
    title: `${item.label} (約${item.seconds}秒)`,
    value: item.value
  }))
})

const currentVideoLengthLabel = computed(() => {
  const current = videosStore.currentStyle?.narration_length || videoDefaultNarrationLength.value || 'standard'
  const matched = narrationLengths.value.find(l => l.value === current)
  return matched ? `${matched.label} (約${matched.seconds}秒 / ${matched.seconds * 6}字)` : '標準 (約30秒)'
})

const currentDefaultSpeakerName = computed(() => {
  const spId = defaultSpeakerId.value
  if (!spId) return '未設定'
  const sp = speakersStore.speakers.find(s => s.id === spId)
  return sp ? sp.name : '未設定'
})

const sceneNarrationLengthOptions = computed(() => {
  const current = videosStore.currentStyle?.narration_length || videoDefaultNarrationLength.value || 'standard'
  const matched = narrationLengths.value.find(l => l.value === current)
  const defaultTitle = matched ? `${matched.label} (約${matched.seconds}秒)` : '標準'
  return [
    { title: `既定に従う (動画設定: ${defaultTitle})`, value: null },
    ...narrationLengths.value.map(item => ({
      title: `${item.label} (約${item.seconds}秒)`,
      value: item.value
    }))
  ]
})

const sceneSpeakerOptions = computed(() => {
  const defaultName = currentDefaultSpeakerName.value
  const options = [{ title: `既定に従う (動画設定: ${defaultName})`, value: null }]
  speakersStore.speakers.forEach(s => {
    options.push({ title: s.name, value: s.id })
  })
  return options
})

const currentDefaultSpeakerBName = computed(() => {
  const spId = defaultSpeakerBId.value
  if (!spId) return '未設定'
  const sp = speakersStore.speakers.find(s => s.id === spId)
  return sp ? sp.name : '未設定'
})

const sceneSpeakerBOptions = computed(() => {
  const defaultName = currentDefaultSpeakerBName.value
  const options = [{ title: `既定に従う (動画設定: ${defaultName})`, value: null }]
  speakersStore.speakers.forEach(s => {
    options.push({ title: s.name, value: s.id })
  })
  return options
})

const hasChatDialogInVideo = computed(() => {
  return scenesStore.scenes.some(s => s.layout_type === 'chat_dialog')
})

// ─── 生成中判定 ───
const isGenerating = computed(() => {
  return generationStore.currentProgress?.status === 'running' || videosStore.currentVideo?.status === 'generating'
})

// ─── 最新の生成における音声警告 (#63) ───
// 完了した回の履歴にあるときだけ出す（生成中は前回の警告を出さない）
const latestAudioWarnings = computed(() => {
  if (isGenerating.value) return []
  const latest = generationStore.histories[0]
  if (latest && latest.status === 'completed' && Array.isArray(latest.audio_warnings)) {
    return latest.audio_warnings
  }
  return []
})

// ─── 全生成確認モーダル ───
const bulkGenConfirmDialog = ref(false)
const bulkGenOnlyEmpty = ref(true)

// ─── AI でシーン内容を作成モーダル ───
const generateModalOpen = ref(false)
const generateIncludeSlide = ref(true)
const generateIncludeNarration = ref(true)
const generateModalLoading = ref(false)

const hasExistingContent = computed(() => {
  const hasSlide = slideContent.value && Object.keys(slideContent.value).length > 0 && JSON.stringify(slideContent.value) !== '{}'
  const hasNarr = Boolean(editForm.narration_text && editForm.narration_text.trim())
  return hasSlide || hasNarr
})

// ─── 詳細欄アコーディオン開閉制御 ───
const expandedPanels = ref(['slide', 'narration'])

const designPrompt = ref('')
const applyingDesign = ref(false)
const codeEditMode = ref(false)
const codeHtml = ref('')
const codeCss = ref('')
const codePreviewUrl = ref('')

const imagePromptLoading = ref(false)
const rawSlideContent = ref({})

const editForm = reactive({
  title: '',
  layout_type: 'text_only',
  layout_pinned: false,
  layout_reason: '',
  narration_length: null,
  narration_text: '',
  outline_summary: '',
  speaker_id: null,
  speaker_b_id: null
})

// スライドの内容。型のスキーマに沿った形（/api/v1/layouts が配る定義と対）で、
// バックエンドが normalize 済みのものをそのまま持つ。
// 以前はレイアウト別のフラットな項目（left_title, chartLabels …）を平置きしていたが、
// レイアウトが増えるたびにここへ項目を足す必要があり、
// レイアウトを切り替えると入力が消える原因にもなっていた。
const slideContent = ref({})
const layoutPickerOpen = ref(false)

const layoutsStore = useLayoutsStore()
const currentLayoutDef = computed(() => layoutsStore.byId[editForm.layout_type] || null)
const currentTypeDef = computed(() => layoutsStore.typeById[currentLayoutDef.value?.type] || null)
// レイアウトの自動差し替え判定と、ギャラリーの「いまの内容で使える」表示に使う件数
const currentItemCount = computed(() => {
  const path = currentTypeDef.value?.collection
  if (!path) return 0
  const node = path.split('.').reduce((acc, key) => (acc ? acc[key] : undefined), slideContent.value)
  return Array.isArray(node) ? node.length : 0
})

// アイコンと色はレイアウト（40 種）ではなく「型」（14 種）に紐づける。
// レイアウトを足しても、その型の見た目をそのまま受け継ぐので追記が要らない。
const TYPE_ICONS = {
  statement: 'mdi-text-short',      list: 'mdi-format-list-bulleted',
  sequence: 'mdi-arrow-right-bold-outline', contrast: 'mdi-compare',
  hierarchy: 'mdi-triangle-outline', cycle: 'mdi-autorenew',
  matrix: 'mdi-view-grid-outline',  sets: 'mdi-circle-multiple-outline',
  table: 'mdi-table',               chart: 'mdi-chart-bar',
  formula: 'mdi-function-variant',  media: 'mdi-image',
  dialog: 'mdi-chat-processing',    cover: 'mdi-format-header-1',
}
const TYPE_COLORS = {
  statement: 'blue-grey', list: 'teal',     sequence: 'indigo',  contrast: 'cyan',
  hierarchy: 'amber',     cycle: 'green',   matrix: 'deep-purple', sets: 'purple',
  table: 'brown',         chart: 'pink',    formula: 'lime',     media: 'blue',
  dialog: 'light-green',  cover: 'orange',
}

function layoutType(id) {
  return layoutsStore.byId[id]?.type || ''
}
function layoutIcon(id) {
  return TYPE_ICONS[layoutType(id)] ?? 'mdi-layers'
}
function layoutLabel(id) {
  return layoutsStore.byId[id]?.label ?? id
}
function layoutColor(id) {
  return TYPE_COLORS[layoutType(id)] ?? 'grey'
}

/**
 * ギャラリーでレイアウトを選んだとき。
 *
 * 同じ型の中なら内容はそのまま使えるので何もしない。
 * 型をまたぐときはサーバー側で移し替え、表示されなくなる件数があれば確認する。
 */
async function handleLayoutSelected(layout) {
  editForm.layout_pinned = true
  if (selectedScene.value) {
    selectedScene.value.layout_pinned = true
  }
  const fromLayout = selectedScene.value?.layout_type || 'text_only'
  if (layoutType(fromLayout) === layout.type) {
    if (selectedScene.value && editForm.layout_type !== fromLayout) {
      await scenesStore.update(selectedScene.value.id, { layout_type: editForm.layout_type, layout_pinned: true })
      selectedScene.value.layout_type = editForm.layout_type
    }
    return
  }
  try {
    const { data } = await layoutApi.convert(fromLayout, layout.id, slideContent.value)
    if (data.lost_count > 0) {
      const ok = window.confirm(
        `「${layout.label}」は ${layout.max} 件までのため、${data.lost_count} 件が表示されなくなります。\n` +
        'このまま切り替えますか？（保存するまでは元に戻せます）'
      )
      if (!ok) {
        editForm.layout_type = fromLayout
        return
      }
    }
    slideContent.value = data.content
    if (selectedScene.value) {
      await scenesStore.update(selectedScene.value.id, { layout_type: editForm.layout_type, layout_pinned: true })
      selectedScene.value.layout_type = editForm.layout_type
    }
  } catch (e) {
    ui.notifyError('レイアウトの切り替えに失敗しました: ' + (e.response?.data?.detail || e.message))
    editForm.layout_type = fromLayout
  }
}


// ---- 画像スロットとレイアウトの対応 ----
//
// media 型のレイアウトは画像を「内容」として受け取り、必要枚数を capacity で
// 宣言している（1 枚のものから 4 枚のギャラリーまで）。それ以外の型では
// 素材は絶対配置の添え物なので、従来どおりの既定枠数を出す。

const DEFAULT_ASSET_SLOTS = 3

const isMediaLayout = computed(() => currentLayoutDef.value?.type === 'media')

const assetSlotCount = computed(() => {
  const def = currentLayoutDef.value
  if (!def || def.type !== 'media' || def.any_count) return DEFAULT_ASSET_SLOTS
  return def.max || DEFAULT_ASSET_SLOTS
})

// キャプションはスライド内容 (images[]) が持つ。スロット N が images[N-1] に対応する。
const slotCaptions = computed(() =>
  (Array.isArray(slideContent.value.images) ? slideContent.value.images : [])
    .map((img) => (img && img.caption) || '')
)

function applySlotCaptions(list) {
  if (!Array.isArray(slideContent.value.images)) slideContent.value.images = []
  const images = slideContent.value.images
  list.forEach((caption, idx) => {
    while (images.length <= idx) images.push({ src: '', caption: '' })
    images[idx].caption = caption
  })
}


const speakerOptions = computed(() => {
  const options = [{ title: 'デフォルト (オーバーライドなし)', value: null }]
  speakersStore.speakers.forEach(s => {
    options.push({ title: s.name, value: s.id })
  })
  return options
})

// ナレーションツールバー・書式点検・読み辞書連携 (#74)
const narrationTextareaRef = ref(null)
const narrationTextareaEl = ref(null)
const readingCheckerRef = ref(null)

const updateNarrationTextareaEl = () => {
  nextTick(() => {
    if (narrationTextareaRef.value) {
      narrationTextareaEl.value =
        narrationTextareaRef.value.$el?.querySelector('textarea') ||
        narrationTextareaRef.value.textarea ||
        null
    } else {
      narrationTextareaEl.value = null
    }
  })
}

watch(narrationTextareaRef, () => {
  updateNarrationTextareaEl()
}, { immediate: true })

watch(expandedPanels, () => {
  updateNarrationTextareaEl()
})

function onReadingRegistered() {
  readingCheckerRef.value?.fetchReading?.()
  if (selectedScene.value?.id) {
    readingApi.getSceneReading(selectedScene.value.id).then(({ data }) => {
      if (data?.text) {
        currentReadingText.value = data.text
      }
    }).catch(() => {})
  }
}

// ─── プレビュー音声作成・再作成の判定 (#83) ───
const effectiveSpeakerA = computed(() => {
  return editForm.speaker_id || defaultSpeakerId.value || null
})

const effectiveSpeakerB = computed(() => {
  return editForm.speaker_b_id || defaultSpeakerBId.value || null
})

const effectiveNarrationSpeed = computed(() => {
  return videosStore.currentStyle?.narration_speed ?? 1.0
})

const hasUnsavedNarrationChanges = computed(() => {
  if (!selectedScene.value) return false
  if ((editForm.narration_text || '') !== (selectedScene.value.narration_text || '')) return true
  if ((editForm.speaker_id || null) !== (selectedScene.value.speaker_id || null)) return true
  if ((editForm.speaker_b_id || null) !== (selectedScene.value.speaker_b_id || null)) return true
  return false
})

// シーン全体の未保存変更があるか (#84)
const hasUnsavedSceneChanges = computed(() => {
  if (!selectedScene.value) return false
  const s = selectedScene.value
  if ((editForm.title || '') !== (s.title || '')) return true
  if (editForm.layout_type !== s.layout_type) return true
  if (editForm.layout_pinned !== (s.layout_pinned ?? false)) return true
  if (editForm.narration_length !== s.narration_length) return true
  if ((editForm.narration_text || '') !== (s.narration_text || '')) return true
  if ((editForm.outline_summary || '') !== (s.outline_summary || '')) return true
  if ((editForm.speaker_id || null) !== (s.speaker_id || null)) return true
  if ((editForm.speaker_b_id || null) !== (s.speaker_b_id || null)) return true

  // スライド内容の比較
  if (s.slide_content_json) {
    try {
      const savedSlide = JSON.parse(s.slide_content_json)
      const currentSlide = { ...slideContent.value, title: slideContent.value.title ?? editForm.title }
      if (JSON.stringify(currentSlide) !== JSON.stringify(savedSlide)) return true
    } catch (_) {}
  }
  return false
})

const isNarrationChanged = computed(() => {
  if (!scenesStore.previewAudioUrl || !lastPreviewSnapshot.value) return false
  if (lastPreviewSnapshot.value.sceneId !== selectedScene.value?.id) return true

  // 1. 未保存のナレーション・話者変更
  if (hasUnsavedNarrationChanges.value) return true

  // 2. 読み上げ用テキスト（辞書変更・修正含む）
  const readingText = readingCheckerRef.value?.readingData?.text ?? currentReadingText.value
  if (readingText && lastPreviewSnapshot.value.readingText && readingText !== lastPreviewSnapshot.value.readingText) {
    return true
  }

  // 3. 話者A
  if (effectiveSpeakerA.value !== lastPreviewSnapshot.value.speakerA) return true

  // 4. 話者B
  if (effectiveSpeakerB.value !== lastPreviewSnapshot.value.speakerB) return true

  // 5. 話速
  if (effectiveNarrationSpeed.value !== lastPreviewSnapshot.value.speed) return true

  return false
})

const previewButtonLabel = computed(() => {
  if (!scenesStore.previewAudioUrl) {
    return 'プレビュー音声を作る'
  }
  if (isNarrationChanged.value) {
    return 'プレビュー音声を作り直す'
  }
  return 'プレビュー再生'
})

const previewButtonIcon = computed(() => {
  if (!scenesStore.previewAudioUrl) {
    return 'mdi-waveform'
  }
  if (isNarrationChanged.value) {
    return 'mdi-refresh'
  }
  return 'mdi-play-circle-outline'
})

const previewButtonVariant = computed(() => {
  if (isNarrationChanged.value || !scenesStore.previewAudioUrl) {
    return 'tonal'
  }
  return 'outlined'
})

const previewButtonColor = computed(() => {
  if (isNarrationChanged.value) {
    return 'primary'
  }
  return 'secondary'
})

const RUBY_RE = /[｜|]([^｜|《》\n]+?)《([^《》\n]+?)》/g
const PAUSE_RE = /[［\[]間(?:\s*[:：]\s*(\d+(?:\.\d+)?))?\s*[］\]]/g

function stripMarkupClient(text) {
  if (!text) return ''
  return text.replace(RUBY_RE, '$1').replace(PAUSE_RE, '')
}

function calculatePauseSeconds(text) {
  if (!text) return 0
  let total = 0
  const re = new RegExp(PAUSE_RE.source, 'g')
  let m
  while ((m = re.exec(text)) !== null) {
    const raw = m[1]
    const sec = raw !== undefined ? parseFloat(raw) : 0.5
    total += Math.max(0.0, Math.min(5.0, isNaN(sec) ? 0.5 : sec))
  }
  return total
}

const inspectProblems = ref([])
const backendPlainLength = ref(null)
let inspectDebounceTimer = null

function cancelInspectDebounce() {
  if (inspectDebounceTimer) {
    clearTimeout(inspectDebounceTimer)
    inspectDebounceTimer = null
  }
}

async function runInspect(text) {
  if (!text || !text.trim()) {
    inspectProblems.value = []
    backendPlainLength.value = 0
    return
  }
  try {
    const res = await readingApi.inspectMarkup(text)
    inspectProblems.value = res.data?.problems || []
    if (res.data?.plain_length !== undefined) {
      backendPlainLength.value = res.data.plain_length
    }
  } catch (err) {
    console.error('Failed to inspect narration markup:', err)
  }
}

watch(() => editForm.narration_text, (newText) => {
  backendPlainLength.value = stripMarkupClient(newText).length
  cancelInspectDebounce()
  if (!newText || !newText.trim()) {
    inspectProblems.value = []
    return
  }
  inspectDebounceTimer = setTimeout(() => {
    runInspect(newText)
  }, 500)
})

const plainNarrationLength = computed(() => {
  const text = editForm.narration_text || ''
  if (!text) return 0
  if (backendPlainLength.value !== null) {
    return backendPlainLength.value
  }
  return stripMarkupClient(text).length
})

// ナレーション長の推定（記号を除外した純文字数 14文字 ≒ 1秒 + 間の秒数）(#74)
const estimatedDuration = computed(() => {
  const len = plainNarrationLength.value
  const pauseSec = calculatePauseSeconds(editForm.narration_text)
  if (len === 0 && pauseSec === 0) return 0
  return Math.round((len / 14) + pauseSec)
})

const isDummySpeakerSelected = computed(() => {
  const activeSpeakerId = editForm.speaker_id || defaultSpeakerId.value
  if (!activeSpeakerId) return false
  const sp = speakersStore.speakers.find(s => s.id === activeSpeakerId)
  return sp?.is_system && sp?.reference_audio_path?.includes('default/reference.wav')
})

const narrationLengthHint = computed(() => {
  const sec = estimatedDuration.value
  if (sec === 0) return '未入力'
  if (sec < 20) return `約 ${sec} 秒（短め）`
  if (sec <= 35) return `約 ${sec} 秒（適切）`
  return `約 ${sec} 秒（長め）`
})

const narrationChipColor = computed(() => {
  const sec = estimatedDuration.value
  if (sec === 0) return 'default'
  if (sec < 20) return 'warning'
  if (sec <= 35) return 'success'
  return 'error'
})

// 現在実行中の処理名（シーン詳細パネルのステータスインジケーター用）
const processingLabel = computed(() => {
  if (scenesStore.bulkGenLoading) {
    const { done, total, currentTitle } = scenesStore.bulkGenProgress
    return `全シーンの AI 内容を一括生成中... (${done}/${total}${currentTitle ? ' - ' + currentTitle : ''})`
  }
  if (previewLoading.value) {
    const sec = previewElapsedSec.value
    return sec > 0
      ? `音声プレビューを合成中...（バックグラウンド処理、経過 ${sec} 秒）`
      : '音声プレビューを合成中...（バックグラウンド処理）'
  }
  if (contentGenLoading.value) return 'AIスライド内容を生成中...'
  if (saveLoading.value) return 'シーンを保存中...'
  if (scenesStore.loading) return 'シーンデータを更新中...'
  return null
})

// 動画全体の共通設定変更
async function onVideoDefaultNarrationLengthChange(val) {
  videoDefaultNarrationLength.value = val
  try {
    await videosStore.updateStyle(videoId, { narration_length: val })
  } catch (e) {
    ui.notifyError('既定のナレーション長の更新に失敗しました: ' + e.message)
  }
}

async function onDefaultSpeakerChange(val) {
  defaultSpeakerId.value = val
  try {
    await videosStore.updateStyle(videoId, { default_speaker_id: val })
  } catch (e) {
    ui.notifyError('既定の話者の更新に失敗しました: ' + e.message)
  }
}

async function onDefaultSpeakerBChange(val) {
  defaultSpeakerBId.value = val
  try {
    await videosStore.updateStyle(videoId, { default_speaker_b_id: val })
  } catch (e) {
    ui.notifyError('既定の話者 B の更新に失敗しました: ' + e.message)
  }
}

// 全生成確認モーダル
function openBulkGenConfirmDialog() {
  if (!scenesStore.scenes.length) return
  bulkGenConfirmDialog.value = true
}

async function executeBulkGen() {
  bulkGenConfirmDialog.value = false
  try {
    await scenesStore.generateAllContent(videoId, bulkGenOnlyEmpty.value, (statusData) => {
      const completedIds = statusData.completed_scene_ids || []
      if (selectedScene.value && completedIds.includes(selectedScene.value.id)) {
        const updated = scenesStore.scenes.find(s => s.id === selectedScene.value.id)
        if (updated) {
          selectedScene.value = { ...updated }
          applySlideContentFromScene(updated)
        }
      }
    })
    if (scenesStore.scenes.length) {
      const currentId = selectedScene.value?.id
      const latest = scenesStore.scenes.find(s => s.id === currentId) || scenesStore.scenes[0]
      selectScene(latest, { preservePanels: true })
    }
  } catch (e) {
    // notifyError is handled in store
  }
}

// シーン個別設定ハンドラ
async function onSceneNarrationLengthChange(val) {
  if (!selectedScene.value) return
  editForm.narration_length = val
  try {
    await scenesStore.update(selectedScene.value.id, { narration_length: val })
    selectedScene.value.narration_length = val
  } catch (e) {
    ui.notifyError('ナレーション長の更新に失敗しました: ' + e.message)
  }
}

async function onSceneSpeakerChange(val) {
  if (!selectedScene.value) return
  editForm.speaker_id = val
  try {
    await scenesStore.update(selectedScene.value.id, { speaker_id: val })
    selectedScene.value.speaker_id = val
  } catch (e) {
    ui.notifyError('話者の更新に失敗しました: ' + e.message)
  }
}

async function onSceneSpeakerBChange(val) {
  if (!selectedScene.value) return
  editForm.speaker_b_id = val
  try {
    await scenesStore.update(selectedScene.value.id, { speaker_b_id: val })
    selectedScene.value.speaker_b_id = val
  } catch (e) {
    ui.notifyError('話者 B の更新に失敗しました: ' + e.message)
  }
}

async function resetLayoutToAuto() {
  if (!selectedScene.value) return
  editForm.layout_pinned = false
  try {
    await scenesStore.update(selectedScene.value.id, { layout_pinned: false })
    selectedScene.value.layout_pinned = false
    ui.notify('見せ方を「おまかせ」に戻しました（次回AI生成時に最適なレイアウトが自動選択されます）')
  } catch (e) {
    ui.notifyError('おまかせへの変更に失敗しました: ' + e.message)
  }
}

// AI でシーン内容を作成 モーダル
function openGenerateModal() {
  if (!selectedScene.value) return
  generateIncludeSlide.value = true
  generateIncludeNarration.value = true
  generateModalOpen.value = true
}

async function executeSceneGenerate() {
  if (!selectedScene.value) return
  if (!generateIncludeSlide.value && !generateIncludeNarration.value) return

  generateModalLoading.value = true
  contentGenLoading.value = true
  try {
    // まず最新の基本情報を保存（あらすじ、タイトル、見せ方、長さ、話者）
    await scenesStore.update(selectedScene.value.id, {
      title: editForm.title,
      outline_summary: editForm.outline_summary,
      narration_length: editForm.narration_length,
      speaker_id: editForm.speaker_id,
      speaker_b_id: editForm.speaker_b_id,
    })

    const existingNarration = editForm.narration_text || ''

    if (generateIncludeSlide.value && generateIncludeNarration.value) {
      // 両方生成
      const { data } = await scenarioApi.generateSceneContent(selectedScene.value.id)
      applySlideContentFromScene(data)
      const idx = scenesStore.scenes.findIndex(s => s.id === data.id)
      if (idx !== -1) scenesStore.scenes[idx] = data
      selectedScene.value = data
    } else if (generateIncludeSlide.value && !generateIncludeNarration.value) {
      // スライドのみ生成（ナレーションは既存のものを復元して維持）
      const { data } = await scenarioApi.generateSceneContent(selectedScene.value.id)
      await scenesStore.update(selectedScene.value.id, { narration_text: existingNarration })
      data.narration_text = existingNarration
      applySlideContentFromScene(data)
      const idx = scenesStore.scenes.findIndex(s => s.id === data.id)
      if (idx !== -1) scenesStore.scenes[idx] = data
      selectedScene.value = data
    } else if (!generateIncludeSlide.value && generateIncludeNarration.value) {
      // ナレーションのみ生成
      const { data } = await scenarioApi.generateNarration(selectedScene.value.id)
      editForm.narration_text = data.narration_text
      selectedScene.value.narration_text = data.narration_text
      const idx = scenesStore.scenes.findIndex(s => s.id === data.id)
      if (idx !== -1) scenesStore.scenes[idx] = { ...scenesStore.scenes[idx], narration_text: data.narration_text }
    }

    ui.notify('AI でシーン内容を作成しました。')
    generateModalOpen.value = false
    
    // 生成完了後は詳細欄を展開
    expandedPanels.value = ['slide', 'narration']
  } catch (e) {
    ui.notifyError('シーン内容の作成に失敗しました: ' + (e.response?.data?.detail || e.message))
  } finally {
    generateModalLoading.value = false
    contentGenLoading.value = false
  }
}

onMounted(async () => {
  initialLoading.value = true
  try {
    // スタイル選択肢（ナレーションの長さなど）を取得
    try {
      const { data: optData } = await styleApi.listOptions()
      if (optData?.narration_lengths) {
        narrationLengths.value = optData.narration_lengths
      }
    } catch (e) {
      console.warn('style-options の取得に失敗しました', e)
    }

    // レイアウトのカタログ（型・見せ方・編集フォームの項目定義）。
    // 画面のあちこちで参照するので、シーンを選ぶ前に読み込んでおく。
    await layoutsStore.fetchCatalog()
    await videosStore.fetchOne(videoId)
    await videosStore.fetchStyle(videoId)
    await scenesStore.fetchAll(videoId)
    await speakersStore.fetchAll()
    await generationStore.fetchHistories(videoId)
    await generationStore.fetchGenerationStatus(videoId)
    
    // シナリオの初期読み込み
    await scenarioStore.fetchScenario(videoId)

    defaultSpeakerId.value = videosStore.currentStyle?.default_speaker_id || null
    defaultSpeakerBId.value = videosStore.currentStyle?.default_speaker_b_id || null
    videoDefaultNarrationLength.value = videosStore.currentStyle?.narration_length || 'standard'

    if (scenesStore.scenes.length) {
      selectScene(scenesStore.scenes[0])
      updateNarrationTextareaEl()
    }

    // ユーザーがロード中に手動でタブを切り替えていなければ、シーン数に応じて初期タブを決定
    // シーン 0 件: 「シナリオ作成」(scenario) / シーン 1 件以上: 「シーン編集」(scenes)
    if (!userInteractedTab.value) {
      activeTab.value = scenesStore.scenes.length === 0 ? 'scenario' : 'scenes'
    }
  } catch (err) {
    ui.notifyError('プロジェクトデータの初期読み込みに失敗しました: ' + (err.message || err))
    if (!userInteractedTab.value) {
      activeTab.value = 'scenario'
    }
  } finally {
    initialLoading.value = false
  }
})

// シナリオ確定後のコールバック
const onScenarioFinalized = async () => {
  await scenesStore.fetchAll(videoId)
  if (scenesStore.scenes.length) {
    selectScene(scenesStore.scenes[0])
  }
  activeTab.value = 'scenes'
}

function handleAudioLoaded(e) {
  previewAudioDuration.value = e.target.duration
}

watch(selectedScene, (scene) => {
  if (scenesStore.previewAudioUrl) {
    URL.revokeObjectURL(scenesStore.previewAudioUrl)
    scenesStore.previewAudioUrl = ''
  }
  lastPreviewSnapshot.value = null
  previewError.value = null
  currentReadingText.value = ''
  previewAudioDuration.value = 0
  updateNarrationTextareaEl()
  if (scene?.narration_text) {
    runInspect(scene.narration_text)
  } else {
    inspectProblems.value = []
    backendPlainLength.value = 0
  }
})

watch(activeTab, async (newTab) => {
  if (newTab === 'scenario') {
    await scenarioStore.fetchScenario(videoId)
  }
})

onBeforeUnmount(() => {
  cancelInspectDebounce()
  generationStore.disconnectWebSocket()
})


function applySlideContentFromScene(scene) {
  if (!scene) return
  editForm.title = scene.title ?? editForm.title
  editForm.layout_type = scene.layout_type || editForm.layout_type
  editForm.layout_pinned = scene.layout_pinned ?? false
  editForm.layout_reason = scene.layout_reason || ''
  editForm.narration_length = scene.narration_length ?? null
  editForm.narration_text = scene.narration_text || ''
  editForm.outline_summary = scene.outline_summary || ''
  editForm.speaker_id = scene.speaker_id || null
  editForm.speaker_b_id = scene.speaker_b_id || null

  // 内容はバックエンドが型のスキーマへ正規化済み。画面側でほぐし直さない
  // （ほぐすとレイアウトごとの分岐が復活し、型を増やすたびにここが膨らむ）。
  let parsed = {}
  if (scene.slide_content_json) {
    try {
      parsed = JSON.parse(scene.slide_content_json) || {}
    } catch (e) {
      console.warn('slide_content_json のパースに失敗しました', e)
    }
  }
  rawSlideContent.value = parsed
  slideContent.value = { ...parsed }
}

async function generateImagePrompt() {
  if (!selectedScene.value) return
  imagePromptLoading.value = true
  try {
    const { data } = await scenarioApi.generateImagePrompt(selectedScene.value.id)
    selectedScene.value = data
    const idx = scenesStore.scenes.findIndex(s => s.id === data.id)
    if (idx !== -1) scenesStore.scenes[idx] = data
    applySlideContentFromScene(data)
    ui.notify('画像生成プロンプトを作成しました。')
  } catch (e) {
    ui.notifyError('画像プロンプトの生成に失敗しました: ' + e.message)
  } finally {
    imagePromptLoading.value = false
  }
}

async function copyImagePrompt() {
  const text = selectedScene.value?.image_prompt || ''
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ui.notify('プロンプトをコピーしました。')
  } catch (e) {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    ui.notify('プロンプトをコピーしました。')
  }
}

function selectScene(scene, { preservePanels = false } = {}) {
  const latestScene = scenesStore.scenes.find(s => s.id === scene?.id) || scene
  selectedScene.value = latestScene

  designPrompt.value = ''
  codeEditMode.value = false
  codeHtml.value = ''
  codeCss.value = ''
  codePreviewUrl.value = ''

  applySlideContentFromScene(scene)

  if (!preservePanels) {
    // 初期開閉状態：生成前（スライド内容とナレーションが空）なら閉じ、内容があれば開く
    const hasSlide = scene.slide_content_json && scene.slide_content_json.length > 2 && scene.slide_content_json !== '{}'
    const hasNarr = Boolean(scene.narration_text && scene.narration_text.trim())
    if (hasSlide || hasNarr) {
      expandedPanels.value = ['slide', 'narration']
    } else {
      expandedPanels.value = []
    }
  }
}

async function applyDesignAdjust() {
  if (!designPrompt.value.trim() || !selectedScene.value) return
  applyingDesign.value = true
  try {
    await scenesStore.applyDesignAdjust(selectedScene.value.id, designPrompt.value)
    ui.notify('AI によるデザイン調整を適用しました')
    designPrompt.value = ''
    await loadSceneCode()
    await refreshCodePreview()
  } catch (e) {
    ui.notifyError('AIデザイン調整に失敗しました: ' + e.message)
  } finally {
    applyingDesign.value = false
  }
}

async function loadSceneCode() {
  if (!selectedScene.value) return
  const { html, css } = await scenesStore.fetchEffectiveCode(selectedScene.value.id)
  codeHtml.value = html
  codeCss.value = css
}

async function applySceneCode() {
  if (!selectedScene.value) return
  await scenesStore.update(selectedScene.value.id, { custom_html: codeHtml.value, custom_css: codeCss.value })
  ui.notify('コードを保存しました')
  await refreshCodePreview()
}

async function resetSceneCustomCode() {
  if (!selectedScene.value) return
  await scenesStore.update(selectedScene.value.id, { custom_html: null, custom_css: null })
  ui.notify('自動生成に戻しました')
  await loadSceneCode()
  await refreshCodePreview()
}

async function refreshCodePreview() {
  if (!videoId) return
  const sceneId = selectedScene.value?.id
  const url = sceneId ? `/videos/${videoId}/preview?scene_id=${sceneId}` : `/videos/${videoId}/preview`
  const { data } = await api.post(url)
  // preview_url にはプレビュー用フラグとキャッシュ回避のクエリが含まれているため、そのまま使う
  // scene_id を渡したときは今のシーンから表示される scene_preview_url を優先 (#84)
  codePreviewUrl.value = data.scene_preview_url || data.preview_url
}

async function confirmDeleteHistory(h) {
  const label = formatDate(h.started_at)
  if (!window.confirm(`${label} の生成履歴を削除しますか？（元に戻せません）`)) return
  try {
    await generationStore.remove(h.id)
  } catch (e) {
    ui.notifyError('削除に失敗しました: ' + e.message)
  }
}

async function handleAddScene() {
  const payload = {
    title: '新しいシーン',
    layout_type: 'text_only',
    narration_text: 'ここにナレーションテキストを入力してください。'
  }
  const newScene = await scenesStore.create(videoId, payload)
  selectScene(newScene)
}

async function handleDeleteScene(sceneId) {
  await scenesStore.remove(sceneId)
  if (selectedScene.value?.id === sceneId) {
    if (scenesStore.scenes.length) {
      selectScene(scenesStore.scenes[0])
    } else {
      selectedScene.value = null
    }
  }
}

async function handleSaveScene() {
  if (!selectedScene.value || scenesStore.bulkGenLoading) return
  saveLoading.value = true
  try {
    // レイアウト別の組み立てはしない。フォームが型のスキーマどおりの形を保っている。
    const slideJsonObj = { ...slideContent.value, title: slideContent.value.title ?? editForm.title }

    const payload = {
      title: editForm.title,
      layout_type: editForm.layout_type,
      layout_pinned: editForm.layout_pinned,
      narration_length: editForm.narration_length,
      narration_text: editForm.narration_text,
      outline_summary: editForm.outline_summary,
      speaker_id: editForm.speaker_id,
      speaker_b_id: editForm.speaker_b_id,
      slide_content_json: JSON.stringify(slideJsonObj)
    }

    const updated = await scenesStore.update(selectedScene.value.id, payload)
    if (updated) {
      selectedScene.value = updated
      applySlideContentFromScene(updated)
      // 読み上げテキストの同期
      try {
        const { data } = await readingApi.getSceneReading(updated.id)
        if (data?.text) {
          currentReadingText.value = data.text
        }
      } catch (_) {}
    }
    ui.notify('シーンを保存しました')
  } catch (err) {
    console.error('シーン保存に失敗しました:', err)
  } finally {
    saveLoading.value = false
  }
}

async function onDragEnd() {
  // 並び替え処理
  // 変更後のインデックスをAPIに送信
  for (let idx = 0; idx < scenesStore.scenes.length; idx++) {
    const s = scenesStore.scenes[idx]
    if (s.index !== idx + 1) {
      await scenesStore.reorder(s.id, idx + 1)
    }
  }
  await scenesStore.fetchAll(videoId)
}

async function moveIndex(scene, currentIndex, direction) {
  const newIndex = currentIndex + direction + 1 // 1-indexed
  await scenesStore.reorder(scene.id, newIndex)
  await scenesStore.fetchAll(videoId)
}

async function handlePlayPreview() {
  if (!selectedScene.value) return

  // プレビュー音声が作成済みで、かつ変更がない場合は合成し直さずにプレイヤーで再生 (#83)
  if (scenesStore.previewAudioUrl && !isNarrationChanged.value) {
    if (previewAudioPlayer.value) {
      previewAudioPlayer.value.currentTime = 0
      try {
        await previewAudioPlayer.value.play()
      } catch (e) {
        console.warn('プレビュー音声再生エラー:', e)
      }
    }
    return
  }

  // ナレーションテキストの未入力チェック
  if (!editForm.narration_text?.trim()) {
    previewError.value = 'ナレーションテキストが未入力です。テキストを入力してから作成してください。'
    return
  }

  // 未保存の変更があるときは、先に保存してから作る（#83: 保存済みの本文で合成するため）
  if (hasUnsavedNarrationChanges.value || saveLoading.value) {
    await handleSaveScene()
  }

  previewError.value = null  // 前回のエラーをクリア
  previewElapsedSec.value = 0
  previewLoading.value = true
  try {
    const sceneId = selectedScene.value.id
    await scenesStore.playPreview(sceneId, (sec) => {
      previewElapsedSec.value = sec
    })

    // 最新の読み上げ用テキストを取得してスナップショットに保存
    let rText = readingCheckerRef.value?.readingData?.text || ''
    if (!rText) {
      try {
        const { data } = await readingApi.getSceneReading(sceneId)
        rText = data?.text || ''
      } catch (err) {
        console.warn('読みテキスト取得エラー:', err)
      }
    }
    currentReadingText.value = rText

    lastPreviewSnapshot.value = {
      sceneId: sceneId,
      readingText: rText,
      speakerA: effectiveSpeakerA.value,
      speakerB: effectiveSpeakerB.value,
      speed: effectiveNarrationSpeed.value,
    }
  } catch (e) {
    previewError.value = e.message
  } finally {
    previewLoading.value = false
  }
}


// 生成オプションを選んでから開始する（既定は音声を再利用する高速モード）
function openGenerateDialog() {
  generateOptions.regenerateAudio = false
  generateDialog.value = true
}

async function handleGenerate() {
  generateDialog.value = false
  await generationStore.generate(videoId, generateOptions.regenerateAudio)
}

async function handleCancelGeneration() {
  if (confirm('実行中の動画生成を中止しますか？')) {
    await generationStore.cancel(videoId)
  }
}

async function handleSlidePreview() {
  slidePreviewLoading.value = true
  try {
    const { data } = await api.post(`/videos/${videoId}/preview`)
    slidePreviewUrl.value = data.preview_url
    slidePreviewDialog.value = true
  } catch (e) {
    ui.notifyError('プレビューの生成に失敗しました: ' + e.message)
  } finally {
    slidePreviewLoading.value = false
  }
}

async function handleSceneModalPreview() {
  if (!selectedScene.value) return
  sceneModalPreviewLoading.value = true
  try {
    // 未保存の変更があれば先に保存する（#84）
    if (hasUnsavedSceneChanges.value || saveLoading.value) {
      await handleSaveScene()
    }
    const sceneId = selectedScene.value.id
    const { data } = await api.post(`/videos/${videoId}/preview?scene_id=${sceneId}`)
    sceneModalPreviewUrl.value = data.scene_preview_url || data.preview_url
    sceneModalPreviewDialog.value = true
  } catch (e) {
    ui.notifyError('プレビューの生成に失敗しました: ' + e.message)
  } finally {
    sceneModalPreviewLoading.value = false
  }
}

function openVideoPlayer(generationId) {
  playerSrc.value = generationStore.playUrl(generationId)
  playerDialog.value = true
}

function statusColor(status) {
  return {
    draft: 'default',
    generating: 'warning',
    completed: 'success',
    failed: 'error',
    running: 'warning',
    cancelled: 'secondary'
  }[status] ?? 'default'
}

function videoStatusLabel(status) {
  const map = {
    draft: '下書き',
    generating: '生成中',
    completed: '完了',
    failed: '失敗'
  }
  return map[status] || status || '下書き'
}

function historyStatusLabel(status) {
  const map = {
    running: '実行中',
    completed: '完了',
    failed: '失敗',
    cancelled: '中止'
  }
  return map[status] || status || '不明'
}

function getProgressStepLabel(progress) {
  if (!progress) return ''
  if (progress.status === 'completed') return '完了'
  if (progress.status === 'cancelled') return '中止'
  if (progress.status === 'failed') return '失敗'
  const map = {
    queued: '準備中',
    tts: '音声を合成中',
    composition: '構成を作成中',
    rendering: '動画をレンダリング中',
    finishing: '仕上げ中（BGM・サムネイル）',
    generating: '生成中'
  }
  return map[progress.step] || progress.step || '準備中'
}

function formatDurationSeconds(sec) {
  if (sec == null || isNaN(sec)) return ''
  const s = Math.round(sec)
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  const rest = s % 60
  return `${m} 分 ${rest} 秒`
}




function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString()
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}




// handleAssetsChange は撤去した。
// slideContent.image_src（.value 抜きで Ref 自身に書いていたため元々効いていない）
// への書き戻しをしていたが、image_src は images[] に置き換わった旧キーであり、
// 画像パスの解決は composition.py が素材スロットから直接行っている。
</script>

<style scoped>
.editor-root-container {
  background: #090a14;
}

.editor-top-bar {
  border-bottom: 1px solid rgba(255, 255, 255, 0.07) !important;
}

.editor-title {
  color: #f1f5f9;
  letter-spacing: -0.2px;
}

/* ─── ステッパータブスタイル ─── */
.editor-stepper-tabs {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
}
.stepper-tab {
  text-transform: none !important;
  font-weight: 600 !important;
  font-size: 0.85rem !important;
  letter-spacing: 0px !important;
  padding: 0 18px !important;
  min-height: 44px !important;
  transition: all 0.2s ease !important;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  font-size: 0.65rem;
  margin-right: 6px;
  color: rgba(255, 255, 255, 0.7);
}
:deep(.v-tab--selected) .step-num {
  background: #06b6d4;
  color: #090a14;
  font-weight: 800;
  box-shadow: 0 0 8px #06b6d4;
}

/* ─── AI 専用ネオンボタン ─── */
.btn-neon-ai {
  background: linear-gradient(135deg, #06b6d4 0%, #a855f7 100%) !important;
  color: #ffffff !important;
  font-weight: 700 !important;
  border: none !important;
  box-shadow: 0 2px 10px rgba(6, 182, 212, 0.35) !important;
  transition: all 0.2s ease !important;
}
.btn-neon-ai:hover {
  box-shadow: 0 4px 16px rgba(168, 85, 247, 0.5) !important;
  transform: translateY(-1px);
}

/* ─── タイムライン & シーン一覧 ─── */
.cyber-scenes-col {
  border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
  background: rgba(12, 14, 26, 0.4);
}
.cyber-scenes-list-container {
  background: rgba(9, 10, 20, 0.5);
}

.cursor-grab {
  cursor: grab;
}
.cursor-grab:active {
  cursor: grabbing;
}

/* シーンカード */
.scene-card {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
  min-height: 68px;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  background: rgba(18, 22, 34, 0.6) !important;
  backdrop-filter: blur(8px);
}

.scene-card:hover {
  border-color: rgba(99, 102, 241, 0.35) !important;
  background: rgba(26, 31, 48, 0.8) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
}

.scene-card-selected {
  border-color: rgba(99, 102, 241, 0.6) !important;
  border-left: 3px solid #6366f1 !important;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.18) 0%, rgba(99, 102, 241, 0.04) 100%) !important;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.2) !important;
}

/* シーン追加ボタン */
.btn-add-scene {
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.35) !important;
  letter-spacing: 0.02em;
  transition: all 0.2s ease !important;
}
.btn-add-scene:hover {
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.55) !important;
  transform: translateY(-1px);
}

.drag-handle {
  opacity: 0.6;
  transition: opacity 0.2s ease;
}
.scene-card:hover .drag-handle {
  opacity: 1;
}

/* シーンサムネイル */
.scene-thumb {
  width: 44px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  flex-shrink: 0;
  margin-right: 14px;
}

/* ギャップユーティリティ */
.gap-1 { gap: 4px !important; }
.gap-2 { gap: 8px !important; }
.gap-3 { gap: 12px !important; }
.gap-4 { gap: 16px !important; }

.thumb-text_only             { background: linear-gradient(135deg, #475569 0%, #64748b 100%); }
.thumb-text_left_image_right { background: linear-gradient(135deg, #0284c7 0%, #38bdf8 100%); }
.thumb-full_image            { background: linear-gradient(135deg, #7c3aed 0%, #c084fc 100%); }
.thumb-bullet_list           { background: linear-gradient(135deg, #0d9488 0%, #2dd4bf 100%); }
.thumb-section_header        { background: linear-gradient(135deg, #ea580c 0%, #fb923c 100%); }
.thumb-comparison            { background: linear-gradient(135deg, #0891b2 0%, #22d3ee 100%); }
.thumb-chat_dialog           { background: linear-gradient(135deg, #16a34a 0%, #4ade80 100%); }

.min-width-0 { min-width: 0; }

.editor-logo-img {
  width: 26px;
  height: 26px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 2px 8px rgba(6, 182, 212, 0.4);
}

.status-pulse-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #fbbf24;
  box-shadow: 0 0 6px #fbbf24;
  animation: pulse 1.5s infinite;
}

/* 下見の枠。16:9 を保ったまま横幅に追従させる。
   中身は別オリジンではないが iframe なので、高さは自前で確保する必要がある。 */
.preview-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 6px;
  overflow: hidden;
  background-color: #000;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.preview-frame iframe {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  /* レンダリングと同じマシンで動くため、下見にポインタ操作までさせない。
     見せるだけに徹して余計な再描画を起こさない。 */
  pointer-events: none;
}

/* ─── 基本情報 特別カード ─── */
.basic-info-special-card {
  background: rgba(35, 18, 22, 0.25) !important;
  border-radius: 6px !important;
  border: 1px solid rgba(255, 183, 153, 0.45) !important;
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 0 24px rgba(251, 146, 120, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
  backdrop-filter: blur(16px) saturate(150%) !important;
  -webkit-backdrop-filter: blur(16px) saturate(150%) !important;
}

.basic-info-bg-wrap {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 1;
}

.basic-info-bg-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.28;
  filter: blur(3px) saturate(130%) contrast(115%);
  transform: scale(1.04);
}

.basic-info-bg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: 
    radial-gradient(circle at 85% 15%, rgba(255, 183, 153, 0.22) 0%, transparent 60%),
    linear-gradient(135deg, rgba(64, 30, 26, 0.58) 0%, rgba(84, 38, 32, 0.48) 100%);
  z-index: 2;
}

.basic-info-content {
  position: relative;
  z-index: 3;
}

/* ─── 「✨ AI でシーン内容を作成」主アクションボタン ─── */
.btn-generate-scene-main {
  background: linear-gradient(135deg, #06b6d4 0%, #8b5cf6 50%, #d946ef 100%) !important;
  color: #ffffff !important;
  border-radius: 6px !important;
  box-shadow: 0 4px 18px rgba(6, 182, 212, 0.35) !important;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
}
.btn-generate-scene-main:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(217, 70, 239, 0.45) !important;
}

.rich-btn-icon {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  object-fit: cover;
  box-shadow: 0 0 8px rgba(6, 182, 212, 0.5);
  vertical-align: middle;
}

.layout-select-btn {
  border-radius: 6px !important;
}

/* ─── 詳細欄 アコーディオン ─── */
.cyber-expansion-panels :deep(.v-expansion-panel) {
  border-radius: 6px !important;
  background: rgba(15, 23, 42, 0.6) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}
.cyber-expansion-panels :deep(.v-expansion-panel-title) {
  padding: 12px 16px !important;
  min-height: 48px !important;
}
.cyber-expansion-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 8px 16px 16px !important;
}

/* ─── コンパクト共通設定カード ─── */
.glass-panel-compact {
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(12px);
}
.compact-select :deep(.v-field__input) {
  font-size: 0.8rem !important;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}

/* ─── 「⚡ AI で全シーンを一括生成」暖色スピードボタン (Issue #40) ─── */
.btn-bulk-generate-main {
  position: relative !important;
  overflow: hidden !important;
  border-radius: 6px !important;
  border: 1px solid rgba(245, 158, 11, 0.65) !important;
  background-color: #1a0f05 !important;
  color: #ffffff !important;
  box-shadow: 0 4px 18px rgba(245, 158, 11, 0.35), inset 0 1px 1px rgba(254, 240, 138, 0.4) !important;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

.btn-bulk-bg-wrap {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}

.btn-bulk-bg-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.9;
  filter: contrast(115%) saturate(120%);
}

.btn-bulk-bg-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, rgba(15, 8, 2, 0.62) 0%, rgba(25, 12, 3, 0.3) 45%, rgba(15, 8, 2, 0.68) 100%);
}

.btn-bulk-content {
  position: relative;
  z-index: 2;
  pointer-events: none;
}

.btn-bulk-generate-main:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: rgba(251, 191, 36, 0.95) !important;
  box-shadow: 0 6px 26px rgba(245, 158, 11, 0.6), 0 0 16px rgba(251, 146, 60, 0.45) !important;
}

.btn-bulk-title {
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: 0.03em;
  color: #ffffff;
  text-shadow: 0 2px 5px rgba(0, 0, 0, 0.95), 0 0 12px rgba(245, 158, 11, 0.9);
  line-height: 1.2;
}

.btn-bulk-subtitle {
  font-size: 0.72rem;
  color: rgba(254, 240, 138, 0.92);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9);
  line-height: 1.1;
  margin-top: 3px;
  letter-spacing: 0.02em;
}

.icon-pulse {
  filter: drop-shadow(0 0 6px rgba(250, 204, 21, 0.95));
}

/* ─── シーン詳細 フロート操作バー (#84) ─── */
.scene-floating-actions {
  position: fixed;
  top: 108px;
  right: 28px;
  z-index: 80;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  background: rgba(18, 18, 24, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 28px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 0 16px rgba(var(--v-theme-primary), 0.15);
  transition: all 0.25s ease;
}

.scene-floating-actions:hover {
  background: rgba(22, 22, 30, 0.95);
  border-color: rgba(255, 255, 255, 0.25);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.6), 0 0 20px rgba(var(--v-theme-primary), 0.25);
}

.floating-action-btn {
  border-radius: 20px !important;
  font-weight: 700 !important;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
}
</style>
