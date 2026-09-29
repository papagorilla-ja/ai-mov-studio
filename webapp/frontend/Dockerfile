# HyperFrames Web App — Vue.js + Vuetify フロントエンド
#
# Stage 1: Node.js で Vue アプリをビルド
# Stage 2: Nginx でビルド成果物を配信 + /api/* を api コンテナへリバースプロキシ
#
# 形式（arm64 / amd64）は固定しない。Mac でも Linux（x86_64・arm64）でも、
# そのマシンの形式で作る（#119）。node・nginx の公式イメージはどちらにも対応している。

# ─── Stage 1: Build ───────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

# 依存パッケージのインストール (package-lock.json を先にコピーしてキャッシュ活用)
COPY package*.json ./
# package-lock.json が存在する場合は npm ci、なければ npm install
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ソースコードをコピーしてビルド
COPY . .
RUN npm run build
# → /app/dist/ に成果物が生成される

# ─── Stage 2: Nginx ───────────────────────────────────────
FROM nginx:1.27-alpine

# ビルド成果物をコピー
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx 設定 (SPA フォールバック + API プロキシ + WebSocket プロキシ)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
