#!/usr/bin/env bash
# cf-ip-refresh.sh — 重扫可用的 Cloudflare 边缘 IP 并更新 /etc/hosts
#
# 背景：本机到 Cloudflare 默认解析的 IP 段 TLS ClientHello 被丢弃，
#       换用未被过滤的边缘 IP（anycast，任何边缘都服务所有 zone）即可直连。
# 用法：cf-ip-refresh.sh          # 重扫两个域名并更新 hosts
#       cf-ip-refresh.sh --dry    # 只扫描，不写 hosts
#
# 依赖：skills/mlops/llm-api-benchmark/scripts/cf_edge_pin.py
set -euo pipefail

# Hermes 托管的 cron 专用 Python（`hermes pm environment cron`），解析逻辑同 news_fetcher.sh
VENV_PY="$HOME/.hermes/scripts/.cron-python"
[[ -x "$VENV_PY" ]] || VENV_PY="$HOME/.hermes/scripts/.venv/bin/python3"
[[ -x "$VENV_PY" ]] || VENV_PY="$(command -v python3 || true)"
if [[ -z "$VENV_PY" || ! -x "$VENV_PY" ]]; then
  echo "!! no usable python3" >&2
  exit 1
fi
SCAN="$HOME/.hermes/skills/mlops/llm-api-benchmark/scripts/cf_edge_pin.py"
DRY_RUN=0
[[ "${1:-}" == "--dry" ]] && DRY_RUN=1

# 域名 → 探测路径（返回 200/403 都算通，403 只是没带鉴权头）
TARGETS=(
  "inference-api.nousresearch.com /v1/models"
  "openrouter.ai /api/v1/models"
)

entries=()
for t in "${TARGETS[@]}"; do
  host=${t%% *}; path=${t##* }
  ip=$("$VENV_PY" "$SCAN" "$host" --path "$path" --json 2>/dev/null \
        | "$VENV_PY" -c 'import json,sys; w=json.load(sys.stdin).get("working") or []; print(w[0] if w else "")')
  if [[ -z "$ip" ]]; then
    echo "!! $host 扫描不到可用 IP（可能整体线路变化，需人工排查）" >&2
    exit 1
  fi
  entries+=("$ip  $host")
  echo "✓ $host -> $ip"
done

if [[ $DRY_RUN -eq 1 ]]; then
  echo "(dry-run，未修改 /etc/hosts)"
  exit 0
fi

# 原子替换 /etc/hosts 中 BEGIN/END 标记块；同时清理早期无标记的历史行
tmp=$(mktemp)
"$VENV_PY" - "$tmp" "${entries[@]}" <<'PY'
import re, sys
dst, entries = sys.argv[1], sys.argv[2:]
kept, skip = [], False
for ln in open('/etc/hosts').read().splitlines():
    s = ln.strip()
    if s.startswith('# BEGIN cf-edge-pin'):
        skip = True; continue
    if s.startswith('# END cf-edge-pin'):
        skip = False; continue
    if skip:
        continue
    # 清理历史遗留（旧的无标记行）
    if (s.startswith('# --- Cloudflare 边缘IP固定') or s.startswith('# 可用IP:')
            or re.match(r'^\d+\.\d+\.\d+\.\d+\s+inference-api\.nousresearch\.com$', s)
            or re.match(r'^\d+\.\d+\.\d+\.\d+\s+openrouter\.ai$', s)):
        continue
    kept.append(ln)
block = ['', '# BEGIN cf-edge-pin (cf-ip-refresh.sh 自动维护，勿手改)'] + entries + ['# END cf-edge-pin']
open(dst, 'w').write('\n'.join(kept + block) + '\n')
PY

sudo cp /etc/hosts "/etc/hosts.bak.$(date +%Y%m%d-%H%M)"
sudo cp "$tmp" /etc/hosts
rm -f "$tmp"

echo
echo "=== 验证（本机直连，无 --resolve）==="
for t in "${TARGETS[@]}"; do
  host=${t%% *}; path=${t##* }
  code=$(curl -s -m 20 -o /dev/null -w "%{http_code} %{time_total}s %{remote_ip}" "https://$host$path" || echo "FAIL")
  echo "  $host -> $code"
done
echo
echo "提示：长驻进程（如 Hermes 主进程）可能缓存了旧 IP，重启后生效。"
