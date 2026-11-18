#!/usr/bin/env bash
# sync.sh — 把 ~/.hermes 的指定内容同步到本仓库，以 PR 形式提交（半自动：人工合并）
# 白名单制：只复制下面列出的条目，绝不整目录扫 ~/.hermes（避免敏感文件混入）
#
# 用法:
#   ./sync.sh             # 同步 → 建分支 → 提交 → 推送 → 开 PR（不合并）
#   ./sync.sh --no-push   # 只同步到本地分支并提交，不推送、不开 PR
set -euo pipefail

SRC="$HOME/.hermes"
DST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="vegetable-kun/awesome-private-vault-config-repo"
cd "$DST"

# ---- 1. 从 main 建同步分支 ----
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠ 工作区有未提交变更，将一并进入本次同步 PR（合并前请在 PR 里确认）："
  git status --short
fi

git checkout main
git pull --ff-only origin main >/dev/null 2>&1 || echo "⚠ 拉取远端 main 失败，继续使用本地 main"

BRANCH="sync/$(date '+%Y%m%d-%H%M%S')"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  BRANCH="${BRANCH}-$$"
fi
git checkout -b "$BRANCH"
echo "✓ 已建分支 $BRANCH"

# ---- 2. 复制 ----
cp -a "$SRC/AGENTS.md" "$SRC/SOUL.md" "$DST/"

rsync -a --delete --exclude='*.lock' \
  "$SRC/memories/" "$DST/memories/"

# 按需纳入的 skill（用户指定；当前：search-router、session-recap、llm-api-benchmark、kfc-crazy-thursday、server-disk-hygiene）
# 其它技能不同步，避免把约 58 MB 第三方技能包整体推上仓库
rsync -a --delete --exclude='__pycache__/' \
  "$SRC/skills/productivity/search-router/" "$DST/skills/search-router/"

rsync -a --delete --exclude='__pycache__/' \
  "$SRC/skills/productivity/session-recap/" "$DST/skills/session-recap/"

rsync -a --delete --exclude='__pycache__/' --exclude='node_modules/' \
  "$SRC/skills/mlops/llm-api-benchmark/" "$DST/skills/llm-api-benchmark/"

rsync -a --delete --exclude='__pycache__/' --exclude='node_modules/' \
  "$SRC/skills/kfc-crazy-thursday/" "$DST/skills/kfc-crazy-thursday/"

rsync -a --delete --exclude='__pycache__/' --exclude='node_modules/' \
  "$SRC/skills/devops/server-disk-hygiene/" "$DST/skills/server-disk-hygiene/"

rsync -a --delete \
  --exclude='.venv/' --exclude='__pycache__/' \
  "$SRC/scripts/" "$DST/scripts/"

# hook 插件（AGENTS.md 强制门禁，含 search-router 搜索路由）
rsync -a --delete --exclude='__pycache__/' \
  "$SRC/plugins/agents-md-gate/" "$DST/hooks/agents-md-gate/"

mkdir -p "$DST/cron"
cp -a "$SRC/cron/jobs.json" "$DST/cron/jobs.json"

# ---- 3. 提交 ----
git add -A
if git diff --cached --quiet; then
  echo "✓ 无变化，跳过提交"
  git checkout main
  git branch -D "$BRANCH"
  exit 0
fi

STAT=$(git diff --cached --stat | tail -1)
git commit -m "sync: $(date '+%Y-%m-%d %H:%M')" -m "$STAT"

# ---- 4. 推送 + 开 PR ----
if [ "${1:-}" = "--no-push" ]; then
  echo "✓ 已提交到本地分支 $BRANCH（--no-push，未推送）"
  exit 0
fi

git push -u origin "$BRANCH"

PR_URL=$(gh pr create \
  --repo "$REPO" \
  --base main \
  --head "$BRANCH" \
  --title "sync: $(date '+%Y-%m-%d %H:%M')" \
  --body "自动同步 \`~/.hermes/\` 的指定内容（白名单制）。

\`\`\`
$STAT
\`\`\`

> **半自动流程**：本 PR 由 \`sync.sh\` 创建，**需人工审查后合并**。
> 合并命令：\`gh pr merge --merge --delete-branch\`")

git checkout main

echo
echo "✅ 同步完成，等待人工合并"
echo "   PR: $PR_URL"
echo "   合并: gh pr merge --merge --delete-branch"
