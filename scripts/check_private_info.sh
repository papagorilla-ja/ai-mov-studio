#!/bin/bash
# =============================================================================
# 手元の情報のチェック（#118）
#
# リポジトリは公開する前提なので、次のものが入っていないかを調べる。
#   - 手元の絶対パス（/Users/<名前>/…、/home/<名前>/…）… ユーザー名が分かってしまう
#   - メールアドレス（noreply などの公開用のものは除く）
#   - 鍵・トークンらしき文字列（Google・OpenAI・GitHub・Slack・AWS・秘密鍵）
#
# 使い方:
#   scripts/check_private_info.sh            コミットしようとしている内容を調べる（pre-commit が使う）
#   scripts/check_private_info.sh --all      追跡している全ファイルを調べる（公開前の点検）
#
# 見つかったら一覧を出して終了コード 1 で終わる。本当に必要な場合だけ
# `git commit --no-verify` でチェックを飛ばせる。
# =============================================================================
set -euo pipefail

# 探す文字列。ERE（grep -E）で書く。
# このファイル自身は調べない（下の SELF）。見本の文字列を書いても引っかからない。
PATTERNS=(
  '/Users/[A-Za-z0-9._-]+'
  '/home/[A-Za-z0-9._-]+'
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
  'AIza[0-9A-Za-z_-]{35}'
  'sk-[A-Za-z0-9_-]{20,}'
  'gh[pousr]_[A-Za-z0-9]{30,}'
  'github_pat_[A-Za-z0-9_]{30,}'
  'xox[abprs]-[A-Za-z0-9-]{10,}'
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
)
# 見つかっても問題ないもの（公開用のアドレス・例示用のドメインなど）
ALLOW='noreply@anthropic\.com|@users\.noreply\.github\.com|noreply@github\.com|@example\.(com|org|net)'
# 調べないファイル（配布物そのまま・自動生成で、中身をこちらで決めていないもの）
SKIP_FILES='(^|/)package-lock\.json$|\.min\.js$'
SELF='scripts/check_private_info.sh'

MODE="${1:---staged}"
REGEX="$(IFS='|'; echo "${PATTERNS[*]}")"
found=0

# $1: 表示するファイル名 / 標準入力: 中身
check_content() {
  local file="$1" hits
  hits="$(grep -nE -- "$REGEX" | grep -vE -- "$ALLOW" || true)"
  if [ -n "$hits" ]; then
    found=1
    while IFS= read -r line; do
      echo "  $file:$(echo "$line" | cut -c1-200)"
    done <<< "$hits"
  fi
}

cd "$(git rev-parse --show-toplevel)"

if [ "$MODE" = "--all" ]; then
  files="$(git ls-files)"
elif [ "$MODE" = "--staged" ]; then
  # 追加・変更したファイルだけ（削除は調べない）。バイナリ（numstat が "-"）は除く
  files="$(git diff --cached --numstat --diff-filter=ACMR | awk -F '\t' '$1 != "-" {print $3}')"
else
  echo "使い方: $0 [--staged | --all]" >&2
  exit 2
fi

while IFS= read -r file; do
  [ -z "$file" ] && continue
  [ "$file" = "$SELF" ] && continue
  echo "$file" | grep -qE "$SKIP_FILES" && continue
  if [ "$MODE" = "--all" ]; then
    [ -f "$file" ] || continue
    # バイナリ（画像・フォントなど）は飛ばす
    grep -qI . "$file" 2>/dev/null || continue
    check_content "$file" < "$file"
  else
    # コミットされる内容（ステージした版）を調べる。作業中の版ではない。
    # パイプにすると check_content がサブシェルで動き、見つけた印が消えるので < <() で渡す
    check_content "$file" < <(git show ":$file" 2>/dev/null)
  fi
done <<< "$files"

if [ "$found" -ne 0 ]; then
  echo "" >&2
  echo "手元の情報（絶対パス・メールアドレス・鍵など）が含まれています。上の行を直してください。" >&2
  echo "本当に必要な場合だけ git commit --no-verify で飛ばせます。" >&2
  exit 1
fi
echo "手元の情報は見つかりませんでした。"
