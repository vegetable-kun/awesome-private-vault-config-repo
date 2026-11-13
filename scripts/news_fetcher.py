#!/home/ecs-assist-user/.hermes/scripts/.cron-python
"""
News Fetcher - Parallel hot news aggregator
Fetches from multiple sources, deduplicates, outputs JSON.
Version 3: IT之家 + 百度热搜 + 贴吧热榜 + B站热门 (with date filtering)
"""

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

# Config: only keep news within N days
MAX_AGE_DAYS = 7
CUTOFF_DATE = datetime.now() - timedelta(days=MAX_AGE_DAYS)

import aiohttp
from bs4 import BeautifulSoup
import feedparser

SOURCES = {
    "ithome_rss": {
        "url": "https://www.ithome.com/rss/",
        "type": "rss",
        "parser": "parse_rss",
        "limit": 10,
    },
    "baidu_hot": {
        "url": "https://top.baidu.com/board?tab=realtime",
        "type": "html",
        "parser": "parse_baidu",
        "limit": 10,
    },
    "tieba_hot": {
        "url": "https://tieba.baidu.com/hottopic/browse/topicList",
        "type": "json",
        "parser": "parse_tieba",
        "limit": 10,
    },
    "bilibili_popular": {
        "url": "https://api.bilibili.com/x/web-interface/popular?ps=10&pn=1",
        "type": "json",
        "parser": "parse_bilibili",
        "limit": 10,
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def fetch(session, url, timeout=15):
    """Fetch URL content with timeout."""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.text()
            print(f"[WARN] {url} returned {resp.status}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"[ERROR] {url}: {e}", file=sys.stderr)
        return None


def parse_rss(html, source_name, limit=10):
    """Parse RSS feed (IT之家)."""
    items = []
    try:
        feed = feedparser.parse(html)
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            pub_date = entry.get("published", "") or entry.get("pubDate", "")
            date_str = ""
            if pub_date:
                try:
                    dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    date_str = datetime.now().strftime("%Y-%m-%d")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            if title and link:
                items.append({"title": title, "source": "IT之家", "url": link, "date": date_str})
    except Exception as e:
        print(f"[ERROR] RSS parse: {e}", file=sys.stderr)
    return items


def parse_baidu(html, source_name, limit=10):
    """Parse Baidu hot search HTML."""
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".category-wrap_iQLoo .content_1YWBm")[:limit]:
            a = item.find("a", class_="title_dIF3B")
            if a and a.get("href"):
                title = a.get_text(strip=True)
                href = a["href"]
                if title:
                    items.append({"title": title, "source": "百度热搜", "url": href, "date": today})
    except Exception as e:
        print(f"[ERROR] baidu parse: {e}", file=sys.stderr)
    return items


def parse_tieba(html, source_name, limit=10):
    """Parse Tieba hot topic JSON."""
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        data = json.loads(html)
        topics = data.get("data", {}).get("bang_topic", {}).get("topic_list", [])[:limit]
        for topic in topics:
            title = topic.get("topic_name", "").strip()
            url = topic.get("topic_url", "").strip()
            if title:
                items.append({"title": title, "source": "贴吧热榜", "url": url, "date": today})
    except Exception as e:
        print(f"[ERROR] tieba parse: {e}", file=sys.stderr)
    return items


def parse_bilibili(html, source_name, limit=10):
    """Parse Bilibili popular videos JSON."""
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        data = json.loads(html)
        videos = data.get("data", {}).get("list", [])[:limit]
        for video in videos:
            title = video.get("title", "").strip()
            bvid = video.get("bvid", "").strip()
            owner = video.get("owner", {}).get("name", "")
            if title and bvid:
                url = f"https://www.bilibili.com/video/{bvid}"
                items.append({"title": title, "source": f"B站·{owner}", "url": url, "date": today})
    except Exception as e:
        print(f"[ERROR] bilibili parse: {e}", file=sys.stderr)
    return items


async def fetch_all():
    """Fetch all sources in parallel."""
    all_items = []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for name, cfg in SOURCES.items():
            tasks.append(fetch(session, cfg["url"]))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (name, cfg), html in zip(SOURCES.items(), results):
            if html and not isinstance(html, Exception):
                parser = globals().get(cfg["parser"])
                if parser:
                    items = parser(html, name, cfg.get("limit", 10))
                    print(f"[OK] {name}: {len(items)} items", file=sys.stderr)
                    all_items.extend(items)
            else:
                print(f"[SKIP] {name}: no data", file=sys.stderr)
    
    return all_items


def dedupe(items):
    """Deduplicate by title similarity."""
    seen = set()
    result = []
    for item in items:
        key = re.sub(r"\s+", "", item["title"])[:30]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def main():
    print(f"[INFO] Fetching hot news from {len(SOURCES)} sources...", file=sys.stderr)
    
    items = asyncio.run(fetch_all())
    print(f"[INFO] Total raw items: {len(items)}", file=sys.stderr)
    
    items = dedupe(items)
    print(f"[INFO] After dedup: {len(items)}", file=sys.stderr)
    
    output = {
        "generated_at": datetime.now().isoformat(),
        "total": min(20, len(items)),
        "items": items[:20],
    }
    
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
