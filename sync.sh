#!/usr/bin/env bash
# sync.sh — 把 ~/.hermes 的指定内容同步到本仓库并提交推送
# 白名单制：只复制下面列出的条目，绝不整目录扫 ~/.hermes（避免敏感文件混入）
#
# 用法:
#   ./sync.sh             # 同步 + 提交 + 推送
#   ./sync.sh --no-push   # 只同步 + 提交，不推送
set -euo pipefail

SRC="$HOME/.hermes"
DST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DST"

# ---- 1. 复制 ----
cp -a "$SRC/AGENTS.md" "$SRC/SOUL.md" "$DST/"

rsync -a --delete --exclude='*.lock' \
  "$SRC/memories/" "$DST/memories/"

# 按需纳入的 skill（用户指定；当前：search-router、session-recap、llm-api-benchmark）
# 其它技能不同步，避免把约 58 MB 第三方技能包整体推上仓库
rsync -a --delete --exclude='__pycache__/' \
  "$SRC/skills/productivity/search-router/" "$DST/skills/search-router/"

rsync -a --delete --exclude='__pycache__/' \
  "$SRC/skills/productivity/session-recap/" "$DST/skills/session-recap/"

rsync -a --delete --exclude='__pycache__/' --exclude='node_modules/' \
  "$SRC/skills/mlops/llm-api-benchmark/" "$DST/skills/llm-api-benchmark/"

rsync -a --delete \
  --exclude='.venv/' --exclude='__pycache__/' \
  "$SRC/scripts/" "$DST/scripts/"

# hook 插件（AGENTS.md 强制门禁，含 search-router 搜索路由）
rsync -a --delete --exclude='__pycache__/' \
  "$SRC/plugins/agents-md-gate/" "$DST/hooks/agents-md-gate/"

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
