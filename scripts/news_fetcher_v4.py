#!/home/ecs-assist-user/.hermes/scripts/.cron-python
"""
News Fetcher v4 - Parallel hot news aggregator with auto-classification
Fetches from 5 sources, deduplicates, auto-categorizes, filters entertainment.
"""
import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

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
    "zhihu_hot": {
        "url": "https://tophub.today/n/mproPpoq6O",
        "type": "html",
        "parser": "parse_zhihu",
        "limit": 15,
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Auto-classification keywords
CATEGORY_KEYWORDS = {
    "技术/AI": [
        "AI", "人工智能", "机器人", "芯片", "大模型", "华为", "小米", "特斯拉",
        "算法", "算力", "自动驾驶", "智能", "科技", "互联网", "手机", "电脑",
        "GPT", "DeepSeek", "openai", "神经网络", "深度学习", "编程", "代码",
        "工厂", "制造", "汽车", "出口", "销量", "续航", "工厂", "量产",
    ],
    "财经": [
        "股票", "市值", "融资", "IPO", "降价", "涨价", "出口", "销量", "利润",
        "营收", "投资", "基金", "银行", "贷款", "通胀", "GDP", "经济",
        "融资", "并购", "市值", "财报", "盈利", "亏损",
    ],
    "国际": [
        "美国", "欧盟", "日本", "俄罗斯", "台风", "地震", "战争", "制裁",
        "特朗普", "拜登", "马克龙", "普京", "朝鲜", "韩国", "印度", "中东",
        "联合国", "北约", "俄乌", "巴以",
    ],
    "社会": [
        "教育", "医疗", "就业", "房价", "婚姻", "法律", "法院", "警察",
        "最低工资", "社保", "养老", "生育", "高考", "大学", "学生",
        "事故", "灾难", "台风", "洪水", "死亡",
    ],
}

# Entertainment/low-quality blacklist
BLACKLIST_KEYWORDS = [
    "演唱会", "离婚", "恋情", "出轨", "绯闻", "八卦", "粉丝", "追星",
    "明星", "网红", "吃瓜", "撕逼", "吵架", "怒怼", "道歉", "洗白",
    "综艺节目", "选秀", "偶像", "CP", "发糖", "撒糖",
    "鼬", "十拳剑", "火影忍者", "红楼梦", "源氏", "奥德赛", "诺兰",
    "三角洲", "王者荣耀", "国服孙策", "钢琴", "六年级",
    "年终奖", "买包", "旅行", "欧拉", "卡吕普索", "珀涅罗珀",
]

# Bilibili entertainment categories to filter out
BILIB_BLACKLIST_CATES = ["动画", "游戏", "鬼畜", "娱乐", "影视"]


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
            tname = video.get("tname", "")
            if title and bvid:
                url = f"https://www.bilibili.com/video/{bvid}"
                items.append({"title": title, "source": f"B站·{owner}", "url": url, "date": today, "category": tname})
    except Exception as e:
        print(f"[ERROR] bilibili parse: {e}", file=sys.stderr)
    return items


def parse_zhihu(html, source_name, limit=15):
    """Parse Zhihu hot list from tophub.today."""
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        soup = BeautifulSoup(html, "lxml")
        # tophub.today structure: table with rows
        rows = soup.select("table tbody tr")[:limit]
        for row in rows:
            a = row.find("a")
            if a and a.get("href"):
                title = a.get_text(strip=True)
                href = a["href"]
                if title and len(title) > 5:
                    items.append({"title": title, "source": "知乎热榜", "url": href, "date": today})
    except Exception as e:
        print(f"[ERROR] zhihu parse: {e}", file=sys.stderr)
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


def is_duplicate(title1, title2, threshold=0.75):
    """Check if two titles are similar enough to be duplicates."""
    # Normalize: remove spaces and common punctuation
    t1 = re.sub(r'[\s，。！？、：；""''【】（）\-\|]+', '', title1)
    t2 = re.sub(r'[\s，。！？、：；""''【】（）\-\|]+', '', title2)
    if t1 == t2:
        return True
    # Use SequenceMatcher for similarity
    ratio = SequenceMatcher(None, t1, t2).ratio()
    return ratio >= threshold


def dedupe(items):
    """Deduplicate by title similarity."""
    result = []
    for item in items:
        is_dup = False
        for existing in result:
            if is_duplicate(item["title"], existing["title"]):
                is_dup = True
                break
        if not is_dup:
            result.append(item)
    return result


def is_blacklisted(title):
    """Check if title contains blacklisted keywords."""
    for kw in BLACKLIST_KEYWORDS:
        if kw in title:
            return True
    return False


def classify(title):
    """Auto-classify title into category."""
    scores = defaultdict(int)
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                scores[cat] += 1
    if scores:
        return max(scores, key=scores.get)
    return "其他"


def main():
    print(f"[INFO] Fetching hot news from {len(SOURCES)} sources...", file=sys.stderr)
    items = asyncio.run(fetch_all())
    print(f"[INFO] Total raw items: {len(items)}", file=sys.stderr)

    # Filter blacklisted
    before = len(items)
    items = [i for i in items if not is_blacklisted(i["title"])]
    print(f"[INFO] After blacklist filter: {len(items)} (removed {before - len(items)})", file=sys.stderr)

    # Filter Bilibili entertainment categories
    before = len(items)
    items = [i for i in items if not (i["source"].startswith("B站") and i.get("category") in BILIB_BLACKLIST_CATES)]
    print(f"[INFO] After bilibili cate filter: {len(items)} (removed {before - len(items)})", file=sys.stderr)

    # Deduplicate
    before = len(items)
    items = dedupe(items)
    print(f"[INFO] After dedup: {len(items)} (removed {before - len(items)})", file=sys.stderr)

    # Classify
    for item in items:
        item["category"] = classify(item["title"])

    # Sort: 技术/AI first, then by category priority
    cat_order = {"技术/AI": 0, "财经": 1, "国际": 2, "社会": 3, "其他": 4}
    items.sort(key=lambda x: cat_order.get(x.get("category", "其他"), 99))

    # Take top 20
    items = items[:20]

    output = {
        "generated_at": datetime.now().isoformat(),
        "total": len(items),
        "items": items,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
