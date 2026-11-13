#!/bin/bash
# 作用：热点新闻速览 cron 任务的【数据抓取入口】
# 并行抓取 IT之家/少数派 RSS、百度热搜、B站热门、知乎热榜（贴吧一并抓取，但随后由 processor 整类丢弃），
# 再调用 news_processor.py 完成解析/过滤/去重/分类，将前 30 条候选以 JSON 输出到 stdout（>/tmp/news_raw.json）。
# news_fetcher.sh - Parallel news aggregator (Shell + Python hybrid)
# Shell: concurrent curl | Python: parse, dedupe, classify, filter
set -euo pipefail

RAW_DIR="/tmp/news_raw_$$"
mkdir -p "$RAW_DIR"

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Hermes 托管的 cron 专用 Python（`hermes pm environment cron`）。
# wrapper 按 active.json 解析当前 generation，环境重建后路径变了也不用改这里。
PYBIN="$SCRIPT_DIR/.cron-python"
[[ -x "$PYBIN" ]] || PYBIN="$HOME/.hermes/scripts/.venv/bin/python3"
[[ -x "$PYBIN" ]] || PYBIN="$(command -v python3 || true)"
if [[ -z "$PYBIN" || ! -x "$PYBIN" ]]; then
  echo "[FATAL] news_fetcher.sh: no usable python3" >&2
  exit 127
fi

echo "[INFO] Fetching from 5 sources in parallel..." >&2

# Concurrent fetch
curl -sL --compressed -A "$UA" "https://www.ithome.com/rss/" -o "$RAW_DIR/ithome.xml" &
curl -sL --compressed -A "$UA" "https://sspai.com/feed" -o "$RAW_DIR/sspai.xml" &
curl -sL --compressed -A "$UA" "https://top.baidu.com/board?tab=realtime" -o "$RAW_DIR/baidu.html" &
curl -sL --compressed -A "$UA" -H "Referer: https://tieba.baidu.com" "https://tieba.baidu.com/hottopic/browse/topicList" -o "$RAW_DIR/tieba.json" &
curl -sL --compressed -A "$UA" -H "Referer: https://www.bilibili.com" "https://api.bilibili.com/x/web-interface/ranking/v2?rid=188&type=all" -o "$RAW_DIR/bilibili.json" &
curl -sL --compressed -A "$UA" -H "Referer: https://tophub.today" "https://tophub.today/n/mproPpoq6O" -o "$RAW_DIR/zhihu.html" &

wait
echo "[INFO] All sources fetched, processing..." >&2

# Process with Python
"$PYBIN" "$SCRIPT_DIR/news_processor.py" "$RAW_DIR"

# Cleanup
rm -rf "$RAW_DIR"
