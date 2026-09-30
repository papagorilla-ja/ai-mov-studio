#!/bin/bash
# AI-MovGen 動画作成 Web アプリ — 一括バックグラウンド起動
#
# 使い方:
#   bash start.sh           # 自動ビルド & バックグラウンド起動
#   bash start.sh --no-build # ビルドをスキップして起動
#   bash start.sh --logs    # 起動後にコンテナログを tail
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# docker compose は -f を付けず、Compose の標準の読み方にする（#119）。
#   - docker-compose.override.yml があれば自動で重ねる（環境ごとの上書き。git 管理外）
#   - .env の COMPOSE_FILE で、使うファイルを並べることもできる
#     例: COMPOSE_FILE=docker-compose.yml:docker-compose.traefik.example.yml
# 以前は -f docker-compose.yml を付けていたため、どちらも効かなかった。
compose() { (cd "$SCRIPT_DIR" && docker compose "$@"); }

# 環境変数か .env の値を読む（無ければ既定値）。start.sh は .env を読み込まないので、
# 必要な値だけここで拾う。
env_value() {
  local key="$1" default="$2" value="${!1:-}"
  if [ -z "$value" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    value="$(grep -E "^${key}=" "$SCRIPT_DIR/.env" | tail -1 | cut -d= -f2- || true)"
    value="${value%\"}"; value="${value#\"}"
  fi
  echo "${value:-$default}"
}

# 画面の URL（起動の最後に表示するだけ）。Traefik などの後ろに置くときは .env で変える
APP_URL="$(env_value APP_URL http://localhost:3000)"

# ホスト側の TTS・レンダラーの待ち受けアドレス（#120）。
# macOS の Docker Desktop は、コンテナから host.docker.internal 経由でホストの 127.0.0.1 に届く。
# Linux では届かないので、コンテナから届くアドレス（Docker のブリッジ 172.17.0.1 など）を
# .env の HOST_SERVICES_BIND で指定する。0.0.0.0 にすると LAN からも届くので注意。
HOST_SERVICES_BIND="$(env_value HOST_SERVICES_BIND 127.0.0.1)"
# 起動確認で問い合わせる先。0.0.0.0（すべて）で待ち受けるなら 127.0.0.1 で届く
if [ "$HOST_SERVICES_BIND" = "0.0.0.0" ]; then
  HOST_SERVICES_CHECK="127.0.0.1"
else
  HOST_SERVICES_CHECK="$HOST_SERVICES_BIND"
fi

# OS ごとの案内（依存の入れ方が違う）
if [ "$(uname -s)" = "Darwin" ]; then
  DOCKER_HINT="Docker Desktop を起動してください。"
  INSTALL_FFMPEG="brew install ffmpeg"
else
  DOCKER_HINT="Docker を起動してください（例: sudo systemctl start docker）。"
  INSTALL_FFMPEG="sudo apt install ffmpeg（ディストリビューションのパッケージ管理で）"
fi

# ─── カラー定義 ───────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[start]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }

# ─── 引数パース (デフォルトで --build を内包) ─────────────
BUILD_FLAG="--build"
TAIL_LOGS=false
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD_FLAG="" ;;
    --logs)     TAIL_LOGS=true ;;
  esac
done

# ─── 前提確認 ─────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  err "Docker が見つかりません。$DOCKER_HINT"
  exit 1
fi
if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
  err "docker-compose.yml が見つかりません: $SCRIPT_DIR/docker-compose.yml"
  err "先に Web アプリの docker-compose.yml を配置してください。"
  exit 1
fi

# ─── ホストネイティブ実行用 venv の確認 ───────────────────
# 以前は `source .venv-host/bin/activate` で venv を有効化していたが、activate には
# venv 作成時の絶対パスが埋め込まれているため、プロジェクトを移動・リネームすると
# 黙って機能しなくなる（存在しないディレクトリを PATH に足すだけでエラーは出ない）。
# その結果 uvicorn がシステムの python で解決され、依存不足で TTS が起動しない事故が
# 起きたため、venv の python を絶対パスで直接起動する方式に変更した。
TTS_PY="$SCRIPT_DIR/qwen3-tts/.venv-host/bin/python"
RENDERER_PY="$SCRIPT_DIR/mlx/.venv-host/bin/python"

# venv の python と主要な依存モジュールが揃っているかを起動前に検証する。
# 起動してからログを追わないと原因が分からない状態を避けるのが目的。
#   $1: 表示名 / $2: venv の python パス / $3: venv があるディレクトリ / $4: 必須モジュール
check_venv() {
  local label="$1" py="$2" dir="$3" module="$4"

  if [ ! -x "$py" ]; then
    err "$label の venv が見つかりません: $py"
    err "  初回セットアップとして、次のコマンドで仮想環境を作成してください:"
    err "    cd \"$dir\""
    err "    python3 -m venv .venv-host"
    err "    .venv-host/bin/pip install -r requirements.txt"
    err "  (※ uv をお使いの場合: uv venv .venv-host --python 3.12 && uv pip install --python .venv-host/bin/python -r requirements.txt)"
    exit 1
  fi

  # 依存の代表として 1 モジュールだけ import する（torch は読まないので 1 秒未満）
  if ! "$py" -c "import $module" 2>/dev/null; then
    err "$label の venv に $module がインストールされていません: $py"
    err "  次のコマンドで依存パッケージを導入してください:"
    err "    cd \"$dir\""
    err "    .venv-host/bin/pip install -r requirements.txt"
    exit 1
  fi
}

check_venv "TTS"      "$TTS_PY"      "$SCRIPT_DIR/qwen3-tts" soundfile
check_venv "Renderer" "$RENDERER_PY" "$SCRIPT_DIR/mlx"       fastapi

# ─── ホストネイティブ TTS 起動 ─────────────────────────────
# デバイスは TTS サーバーが自動で選ぶ（CUDA → Apple Silicon の MPS → CPU）
if [ -f "$SCRIPT_DIR/data/tts_host.pid" ]; then
  kill "$(cat "$SCRIPT_DIR/data/tts_host.pid")" 2>/dev/null || true
  rm -f "$SCRIPT_DIR/data/tts_host.pid"
fi

log "ホストネイティブ TTS を起動します（待ち受け: ${HOST_SERVICES_BIND}:8100）..."
cd "$SCRIPT_DIR/qwen3-tts"
export MODEL_CACHE_DIR="$SCRIPT_DIR/data/model_cache"
export HF_HOME="$SCRIPT_DIR/data/model_cache"
export QWEN3_TTS_MODEL_ID="Qwen/Qwen3-TTS-12Hz-0.6B-Base"
export VOICE_SAMPLES_DIR="$SCRIPT_DIR/engine/voice_samples"
export PYTORCH_ENABLE_MPS_FALLBACK=1
# ─── TTS 生成パラメータ ───
# Qwen3-TTS は長いテキストを1回で投げると EOS を出せずに雑音を生成し続けて破綻する。
# TTS_MAX_ITEM_CHARS はその最後の安全弁（超過したリクエストは 400 で拒否する）。
export TTS_MAX_ITEM_CHARS=160
export TTS_TEMPERATURE=0.7          # 既定 0.9 より下げて破綻を抑える
export TTS_REPETITION_PENALTY=1.10  # 破綻時のコード列反復を抑える
export TTS_BATCH_SIZE=4             # 遅くなる場合は 1 に戻す
export TTS_CHUNK_GAP_SEC=0.28
export TTS_MAX_RETRY=2
nohup "$TTS_PY" -m uvicorn server:app --host "$HOST_SERVICES_BIND" --port 8100 \
  > "$SCRIPT_DIR/data/tts_host.log" 2>&1 &
echo $! > "$SCRIPT_DIR/data/tts_host.pid"
cd "$SCRIPT_DIR"

# ─── ホストネイティブ Renderer (hyperframes --docker) 起動 ───
if [ -f "$SCRIPT_DIR/data/renderer_host.pid" ]; then
  kill "$(cat "$SCRIPT_DIR/data/renderer_host.pid")" 2>/dev/null || true
  rm -f "$SCRIPT_DIR/data/renderer_host.pid"
fi

log "ホストネイティブ Renderer (hyperframes) を起動します..."
docker info >/dev/null 2>&1 || { err "Docker が起動していません。$DOCKER_HINT"; exit 1; }

# レンダリングはホスト上でネイティブ実行するため ffmpeg/ffprobe が必須。
# （--docker 方式はコンテナ内に GPU が無く低速なうえ、hyperframes 側の不具合で失敗するため廃止した）
if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/ffmpeg ]; then
  err "ffmpeg が見つかりません。$INSTALL_FFMPEG を実行してから再実行してください。"
  exit 1
fi

cd "$SCRIPT_DIR/mlx"
export PROJECTS_DIR_HOST="$SCRIPT_DIR/projects"
export NVM_DIR="$HOME/.nvm"
# Homebrew の ffmpeg を hyperframes から見えるようにする（Linux では何もしない）
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# hyperframes が使う Chrome（#120）。Linux の arm64 には、hyperframes が取ってくる
# 配布物の Chrome（Chrome for Testing）が無いので、ディストリビューションの Chromium を
# .env の HYPERFRAMES_BROWSER_PATH で指定する。レンダラーはこの環境変数をそのまま渡す
HYPERFRAMES_BROWSER_PATH="$(env_value HYPERFRAMES_BROWSER_PATH "")"
if [ -n "$HYPERFRAMES_BROWSER_PATH" ]; then
  export HYPERFRAMES_BROWSER_PATH
  log "  hyperframes が使う Chrome: $HYPERFRAMES_BROWSER_PATH"
  # hyperframes は、指定したパスに実行ファイルが無いと黙って無視し、配布物の Chrome に戻る。
  # 書き間違いに気づけるよう、ここで確かめる
  if [ ! -x "$HYPERFRAMES_BROWSER_PATH" ]; then
    warn "HYPERFRAMES_BROWSER_PATH の実行ファイルが見つかりません: $HYPERFRAMES_BROWSER_PATH"
  fi
elif [ "$(uname -s)" = "Linux" ] && [ "$(uname -m)" = "aarch64" ]; then
  warn "Linux (arm64) では Chromium を入れ、.env の HYPERFRAMES_BROWSER_PATH で指定してください（README 参照）"
fi
nohup "$RENDERER_PY" -m uvicorn renderer_server:app --host "$HOST_SERVICES_BIND" --port 8200 \
  > "$SCRIPT_DIR/data/renderer_host.log" 2>&1 &
echo $! > "$SCRIPT_DIR/data/renderer_host.pid"
cd "$SCRIPT_DIR"

# ─── ファイルの所有者をそろえる ───────────────────────────
# api コンテナはホストのユーザーと同じ UID/GID で動かす（docker-compose.yml の user）。
# 以前は root で動かしていたため、Linux では projects/ などに root 所有のファイルが残っている。
# そのままだと api が DB や動画フォルダに書き込めず、レンダラーも作業フォルダを作れない。
# macOS の Docker Desktop はもともとホストのユーザーの所有で作るので、何もしない。
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
# rootless の Docker では、コンテナの root がホストのユーザーに当たる。
# ホストの UID で動かすとホスト上では別の UID になってしまうので、root のまま動かす
if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q 'name=rootless'; then
  HOST_UID=0
  HOST_GID=0
fi
export HOST_UID HOST_GID

# api が書き込むフォルダ。ホスト側と、docker-compose.yml でマウントしたコンテナ側を同じ順に並べる
OWNED_DIRS_HOST=("$SCRIPT_DIR/projects" "$SCRIPT_DIR/data" "$SCRIPT_DIR/engine/voice_samples")
OWNED_DIRS_CONTAINER=(/app/projects /app/data /app/voice_samples)

# 自分の所有でないファイルがあるときだけ、root のコンテナで所有者を直す（sudo は要らない）
fix_ownership() {
  # コンテナを root で動かすとき（start.sh を root で動かした・rootless の Docker）は直さない
  # （直すと、かえってユーザーのファイルまで root 所有にしてしまう）
  [ "$HOST_UID" = "0" ] && return 0

  # 1 件見つかれば十分なので -quit で打ち切る。読めないフォルダのエラーは無視する
  local found
  found="$(find "${OWNED_DIRS_HOST[@]}" ! -uid "$HOST_UID" -print -quit 2>/dev/null || true)"
  [ -z "$found" ] && return 0

  log "自分の所有でないファイルがあるため、所有者を ${HOST_UID}:${HOST_GID} に直します（例: ${found#"$SCRIPT_DIR"/}）..."
  # api のイメージを root で一時的に動かして直す。シンボリックリンク（分割レンダリングの
  # assets など）はリンク先ではなくリンク自体を直す（-h）
  if ! compose run --rm -T --no-deps --user 0:0 api \
      find "${OWNED_DIRS_CONTAINER[@]}" ! -uid "$HOST_UID" \
      -exec chown -h "${HOST_UID}:${HOST_GID}" {} +; then
    err "所有者を直せませんでした。次のコマンドで直してから再実行してください:"
    err "  sudo chown -R ${HOST_UID}:${HOST_GID} $(printf '%q ' "${OWNED_DIRS_HOST[@]}")"
    exit 1
  fi
}
fix_ownership

# ─── 起動 ─────────────────────────────────────────────────
log "Web アプリを起動します (docker compose up -d ${BUILD_FLAG})..."
# 環境ごとの上書きを使っているかを示す（使っていることに気づかないまま設定を探さないように）
if [ -n "$(env_value COMPOSE_FILE "")" ]; then
  log "  使う設定ファイル（.env の COMPOSE_FILE）: $(env_value COMPOSE_FILE "")"
elif [ -f "$SCRIPT_DIR/docker-compose.override.yml" ]; then
  log "  docker-compose.override.yml を重ねます"
fi
if ! compose up -d $BUILD_FLAG; then
  err "docker compose up が失敗しました。api ログ:"
  compose logs --tail=50 api 2>&1 | sed 's/^/  /'
  exit 1
fi

# ─── ヘルスチェック ───────────────────────────────────────
# TTS はモデルのロードとウォームアップに数十秒かかる。API だけを見て「起動完了」と
# 表示すると、UI は操作できるのに TTS だけ未起動という窓ができ、その間に動画生成を
# 実行すると「TTSサーバー接続エラー」で失敗する。そのため全サービスの ready を待つ。
INTERVAL=3

# ヘルスチェックの応答を取る。
#   "webapp:/パス" … webapp のコンテナの中から問い合わせる。画面の URL の設定
#                    （ポートを開けない・Traefik の後ろに置くなど）に左右されずに、
#                    nginx と、その先の api まで届くかを確かめられる（#119）。
#                    localhost ではなく 127.0.0.1 にする。コンテナの中の localhost は
#                    IPv6（::1）で引かれ、IPv4 だけで待ち受ける nginx に届かない
#   それ以外       … ホストから URL に問い合わせる（ホスト側の TTS・レンダラー）
fetch_health() {
  case "$1" in
    webapp:*) compose exec -T webapp wget -qO- -T 3 "http://127.0.0.1${1#webapp:}" 2>/dev/null ;;
    *)        curl -sf -m 3 "$1" 2>/dev/null ;;
  esac
}

# サービスが応答するまでポーリングする。
#   $1: 表示名 / $2: ヘルスチェック URL / $3: 応答に含まれるべき文字列 (空なら疎通のみ)
#   $4: 最大待機秒数 / $5: 監視する pid ファイル (空なら監視しない) / $6: 失敗時に出すログ
# 戻り値: 0=ready / 1=タイムアウト / 2=プロセス停止
wait_for() {
  local label="$1" url="$2" expect="$3" max_wait="$4" pidfile="$5" logfile="$6"
  local elapsed=0 body
  printf "  %-22s" "$label"

  while [ "$elapsed" -lt "$max_wait" ]; do
    # バックグラウンド起動したプロセスが死んでいたら、待たずに打ち切る
    if [ -n "$pidfile" ] && [ -f "$pidfile" ] && ! kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo " ✗ プロセスが停止しました"
      [ -n "$logfile" ] && [ -f "$logfile" ] && tail -15 "$logfile" | sed 's/^/      /'
      return 2
    fi

    body="$(fetch_health "$url" || true)"
    if [ -n "$body" ] && { [ -z "$expect" ] || [[ "$body" == *"$expect"* ]]; }; then
      echo " ✓ ready (${elapsed}秒)"
      return 0
    fi

    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
    echo -n "."
  done

  echo " ✗ タイムアウト (${max_wait}秒)"
  [ -n "$logfile" ] && [ -f "$logfile" ] && tail -15 "$logfile" | sed 's/^/      /'
  return 1
}

log "サービスの起動を待機中..."
STARTUP_OK=true

# Web・API: webapp（nginx）経由で api のヘルスチェックが引ければ疎通確認とみなす
wait_for "Web / API" "webapp:/api/health" '"status":"ok"' 90 "" "" || {
  STARTUP_OK=false
  warn "直近の api ログ:"
  compose logs --tail=30 api 2>&1 | sed 's/^/  /'
}

# TTS: 疎通だけでなくモデルのロード完了まで待つ（初回はモデル取得で更に時間がかかる）
wait_for "TTS (Qwen3-TTS)" "http://${HOST_SERVICES_CHECK}:8100/health" '"model_loaded":true' 300 \
  "$SCRIPT_DIR/data/tts_host.pid" "$SCRIPT_DIR/data/tts_host.log" || STARTUP_OK=false

# Renderer: hyperframes と ffmpeg を解決できている状態を ready とみなす
wait_for "Renderer" "http://${HOST_SERVICES_CHECK}:8200/health" '"status":"ok"' 90 \
  "$SCRIPT_DIR/data/renderer_host.pid" "$SCRIPT_DIR/data/renderer_host.log" || STARTUP_OK=false

# レンダラーは応答していても依存コマンドを見つけられていないことがあるため個別に確認する
RENDERER_HEALTH="$(curl -sf -m 3 "http://${HOST_SERVICES_CHECK}:8200/health" 2>/dev/null || true)"
if [[ "$RENDERER_HEALTH" == *'"hyperframes":"not found"'* ]]; then
  warn "hyperframes が見つかりません。'npm install -g hyperframes' をご確認ください。"
  STARTUP_OK=false
fi
if [[ "$RENDERER_HEALTH" == *'"ffmpeg":"not found"'* ]]; then
  warn "レンダラーから ffmpeg を解決できません。$INSTALL_FFMPEG をご確認ください。"
  STARTUP_OK=false
fi

# hyperframes の自己更新はレンダリング中のパッケージ入れ替えを引き起こすため
# renderer_server.py 側で無効化している。代わりに起動時に更新の有無だけを通知する。
if command -v hyperframes >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  HF_CURRENT="$(hyperframes --version 2>/dev/null | tr -d '[:space:]' || true)"
  HF_LATEST="$(npm view hyperframes version --fetch-timeout=5000 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -n "$HF_CURRENT" ] && [ -n "$HF_LATEST" ] && [ "$HF_CURRENT" != "$HF_LATEST" ]; then
    warn "hyperframes の新しいバージョンがあります: ${HF_CURRENT} → ${HF_LATEST}"
    warn "更新する場合は動画生成をしていないときに 'npm install -g hyperframes@${HF_LATEST}' を実行してください。"
  fi
fi

if [ "$STARTUP_OK" = true ]; then
  log "起動完了!"
  log "Web UI: ${APP_URL}"
else
  warn "一部のサービスが起動していません。この状態で動画を生成すると失敗します。"
  warn "再起動するには: bash stop.sh && bash start.sh"
fi

# ─── サービス一覧表示 ─────────────────────────────────────
echo ""
compose ps

# ─── ログ tail (オプション) ───────────────────────────────
if [ "$TAIL_LOGS" = true ]; then
  echo ""
  log "ログを表示します (Ctrl+C で終了)..."
  compose logs -f
fi
