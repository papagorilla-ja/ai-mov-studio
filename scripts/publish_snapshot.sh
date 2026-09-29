#!/bin/bash
# =============================================================================
# 公開用リポジトリへの書き出し（#118）
#
# このリポジトリ（非公開）の履歴は公開しない。履歴にはコミットの作者の
# メールアドレスや、過去に入っていた手元のパスが残っているため。
# 代わりに、指定した時点のファイル一式を「1 回の書き出し = 1 コミット」として
# 公開用リポジトリへ積む。作者は GitHub の noreply アドレスにする。
#
# 使い方:
#   scripts/publish_snapshot.sh <公開用リポジトリの URL>          準備とチェックだけ（押し出さない）
#   scripts/publish_snapshot.sh <公開用リポジトリの URL> --push   チェックを通ったら押し出す
#
# 環境変数（任意）:
#   PUBLISH_REF           書き出す版（既定: main。作業中の変更は含まれない）
#   PUBLISH_BRANCH        公開用リポジトリのブランチ（既定: main）
#   PUBLISH_AUTHOR_NAME   作者の名前（既定: GitHub のログイン名）
#   PUBLISH_AUTHOR_EMAIL  作者のメール（既定: GitHub の noreply アドレス）
# =============================================================================
set -euo pipefail

REMOTE_URL="${1:-}"
PUSH="${2:-}"
if [ -z "$REMOTE_URL" ] || { [ -n "$PUSH" ] && [ "$PUSH" != "--push" ]; }; then
  echo "使い方: $0 <公開用リポジトリの URL> [--push]" >&2
  exit 2
fi
REF="${PUBLISH_REF:-main}"
BRANCH="${PUBLISH_BRANCH:-main}"
SRC="$(git rev-parse --show-toplevel)"

# ─── 作者（noreply） ─────────────────────────────────────
if [ -z "${PUBLISH_AUTHOR_EMAIL:-}" ]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "PUBLISH_AUTHOR_EMAIL を指定するか、gh（GitHub CLI）にログインしてください。" >&2
    exit 1
  fi
  login="$(gh api user --jq .login)"
  PUBLISH_AUTHOR_EMAIL="$(gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"')"
  PUBLISH_AUTHOR_NAME="${PUBLISH_AUTHOR_NAME:-$login}"
fi
if [[ "$PUBLISH_AUTHOR_EMAIL" != *noreply* ]]; then
  echo "作者のメールは noreply のアドレスにしてください: $PUBLISH_AUTHOR_EMAIL" >&2
  exit 1
fi
export GIT_AUTHOR_NAME="${PUBLISH_AUTHOR_NAME:-publisher}" GIT_AUTHOR_EMAIL="$PUBLISH_AUTHOR_EMAIL"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

# ─── 作業用のリポジトリを作る ────────────────────────────
WORK="$(mktemp -d)"
echo "作業用のフォルダ: $WORK"
cd "$WORK"
git init -q
git config core.hooksPath /dev/null   # 手元のフックは使わない（チェックは下で明示的に行う）
git remote add public "$REMOTE_URL"
if git fetch -q public "$BRANCH" 2>/dev/null; then
  # 前回までの書き出しの続きに積む
  git checkout -q -b "$BRANCH" FETCH_HEAD
  git rm -rq --ignore-unmatch . >/dev/null
else
  # 初回（公開用リポジトリが空）
  git checkout -q --orphan "$BRANCH"
fi

# 指定した版のファイル一式を展開する（git archive なので、追跡していないファイルは入らない）
git -C "$SRC" archive "$REF" | tar -x -C "$WORK"
git add -A

# ─── チェック ────────────────────────────────────────────
"$SRC/scripts/check_private_info.sh" --all

if git rev-parse -q --verify HEAD >/dev/null && git diff --cached --quiet; then
  echo "前回の書き出しから変わったところはありません。"
  exit 0
fi
git commit -q -m "公開: $(date +%Y-%m-%d) 時点"
echo "書き出す内容: $(git ls-files | wc -l | tr -d ' ') ファイル / 作者: $GIT_AUTHOR_NAME <$GIT_AUTHOR_EMAIL>"
git log --format='  %h %an <%ae> %s' -3

if [ "$PUSH" = "--push" ]; then
  git push -q public "$BRANCH"
  echo "押し出しました: $REMOTE_URL（$BRANCH）"
else
  echo "押し出していません。中身を確かめたら --push を付けて実行してください。"
fi
