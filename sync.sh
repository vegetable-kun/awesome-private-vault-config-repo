#!/usr/bin/env bash
# sync.sh — 把 ~/.hermes 的指定内容同步到 ~/hermes-config 并提交推送
# 白名单制：只复制下面列出的条目，绝不整目录扫 ~/.hermes（避免敏感文件混入）
#
# 用法:
#   ./sync.sh             # 同步 + 提交 + 推送
#   ./sync.sh --no-push   # 只同步 + 提交，不推送
set -euo pipefail

SRC="$HOME/.hermes"
DST="$HOME/hermes-config"
cd "$DST"

# ---- 1. 复制 ----
cp -a "$SRC/AGENTS.md" "$SRC/SOUL.md" "$DST/"

rsync -a --delete --exclude='*.lock' \
  "$SRC/memories/" "$DST/memories/"

# 注意：skills/ 不自动同步（约 58 MB，含大量第三方上游技能包）。
# 如需纳入指定技能，取消下面注释并自行限定范围：
# rsync -a --delete \
#   --exclude='.venv/' --exclude='__pycache__/' \
#   --exclude='.hub/' --exclude='.curator_backups/' \
#   "$SRC/skills/" "$DST/skills/"

rsync -a --delete \
  --exclude='.venv/' --exclude='__pycache__/' \
  "$SRC/scripts/" "$DST/scripts/"

mkdir -p "$DST/cron"
cp -a "$SRC/cron/jobs.json" "$DST/cron/jobs.json"

# ---- 2. 提交 ----
git add -A
if git diff --cached --quiet; then
  echo "✓ 无变化，跳过提交"
  exit 0
fi
git commit -m "sync: $(date '+%Y-%m-%d %H:%M')"

# ---- 3. 推送 ----
if [ "${1:-}" != "--no-push" ]; then
  git push
fi
