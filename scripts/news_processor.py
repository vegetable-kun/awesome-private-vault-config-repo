#!/home/ecs-assist-user/.hermes/scripts/.venv/bin/python3
"""
热点新闻速览 - 数据处理脚本
由 news_fetcher.sh 调用，接收原始抓取目录，做以下处理并输出前 30 条候选(JSON)：
  1. 解析各平台 RSS/HTML/JSON（IT之家、少数派、百度热搜、B站、知乎）
  2. 过滤低质：贴吧整类丢弃 / 通用低质词(LOWVAL) / 跨平台重复事件(DROP_EXACT)
  3. B站仅留标题含科技/科普关键词的白名单条目
  4. 去重 → 按【技术/AI→财经→国际→社会→其他】分类排序 → 取前 30 条
最终 20 条由下游 LLM 按"平台保底 + 价值排序"从 30 条候选中手筛。
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

from bs4 import BeautifulSoup
import feedparser

# Blacklist: entertainment/low-quality keywords
BLACKLIST = [
    "演唱会", "离婚", "恋情", "出轨", "绯闻", "八卦", "粉丝", "追星",
    "明星", "网红", "吃瓜", "撕逼", "吵架", "怒怼", "道歉", "洗白",
    "综艺", "选秀", "偶像", "CP", "发糖", "撒糖",
    "鼬", "十拳剑", "火影忍者", "红楼梦", "源氏",
    "三角洲", "王者荣耀", "国服孙策", "钢琴", "六年级",
    "年终奖", "买包", "旅行", "卡吕普索", "珀涅罗珀",
    "遇见小面", "客单价",
]

# B站: keep only tech/科普/social-depth videos (title keyword whitelist)
BILIB_TECH_KW = [
    "芯片", "AI", "人工智能", "机器人", "评测", "拆解", "科普", "科学", "技术",
    "教程", "编程", "手机", "电脑", "相机", "镜头", "汽车", "新能源", "大模型",
    "小米", "华为", "三星", "字节", "豆包", "智能", "算力", "自动驾驶", "半导体",
    "SiC", "碳化硅", "护理", "医疗",
]

# B站 junk: 蹭关键词的水帖/带货/资源合集（rid=188 科技区实测命中后需再筛）
BILIB_JUNK = [
    "愚人节", "资源", "合集", "推荐配置", "装机", "清单", "壁纸", "盘点",
    "第1期", "新品开箱", "开箱", "带货", "优惠券", "福利", "抽奖",
    "小白入门", "购买链接", "低价", "好用不贵", "值不值得买",
    # 教学/维修/带货类：非新闻，无时效价值
    "教程", "教你", "怎么", "如何", "技巧", "经验分享", "维修", "修复",
    "推荐", "闭眼入", "上手", "实测", "体验", "开箱", "值得买",
    "购买", "二手", "价格", "多少钱", "选购", "对比",
]

# B站 新闻性门槛：命中这些才算“新闻”，否则一律丢弃
# 目标是抵消白名单过宽带来的水帖（教学/带货/体验类视频占比过高）
BILIB_NEWS_KW = [
    "发布", "发布会", "官宣", "宣布", "上线", "首曝", "官宣了", "正式",
    "涨", "跌", "事故", "遇难", "起火", "爆炸", "召回", "暴跌", "暴涨",
    "禁令", "监管", "调查", "起诉", "财报", "融资", "上市", "量产",
    "研究", "论文", "开源", "发布模型", "登顶", "突破",
]

# Generic low-value / gossip keywords to drop (beyond BLACKLIST)
LOWVAL = [
    "滑跪", "笑话", "喷日本人", "卖血", "卡中国脖子", "打瓦",
    "科学修仙", "政绩观", "学习成果", "up动画",
]

# Exact cross-platform duplicate events to drop (keep only the best source)
DROP_EXACT = [
    "扶老人被索赔店主支付的1.9万获返还",
]

CATEGORY_KEYWORDS = {
    "技术/AI": [
        "AI", "人工智能", "机器人", "芯片", "大模型", "华为", "小米", "特斯拉",
        "算法", "算力", "自动驾驶", "智能", "科技", "互联网", "手机", "电脑",
        "GPT", "DeepSeek", "openai", "编程", "代码", "工厂", "制造", "出口",
        "销量", "续航", "工厂", "量产", "机器人", "科技", "英伟达", "宇树",
    ],
    "财经": [
        "股票", "市值", "融资", "IPO", "降价", "涨价", "出口", "销量", "利润",
        "营收", "投资", "基金", "银行", "贷款", "GDP", "经济", "并购", "财报",
        "盈利", "亏损", "净利润", "增长",
    ],
    "国际": [
        "美国", "欧盟", "日本", "俄罗斯", "台风", "地震", "战争", "制裁",
        "特朗普", "拜登", "印度", "朝鲜", "韩国", "中东", "联合国", "北约",
        "俄乌", "巴以",
    ],
    "社会": [
        "教育", "医疗", "就业", "房价", "婚姻", "法律", "法院", "警察",
        "最低工资", "社保", "养老", "生育", "高考", "大学", "学生",
        "事故", "灾难", "台风", "洪水", "死亡", "隐私",
    ],
}


def is_blacklisted(title):
    return any(kw in title for kw in BLACKLIST)


def classify(title):
    scores = defaultdict(int)
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                scores[cat] += 1
    return max(scores, key=scores.get) if scores else "其他"


def is_duplicate(t1, t2, threshold=0.75):
    r1 = re.sub(r'[\s，。！？、：；""''【】()-]+', '', t1)
    r2 = re.sub(r'[\s，。！？、：；""''【】()-]+', '', t2)
    if r1 == r2:
        return True
    return SequenceMatcher(None, r1, r2).ratio() >= threshold


def dedupe(items):
    result = []
    for item in items:
        if any(is_duplicate(item["title"], e["title"]) for e in result):
            continue
        result.append(item)
    return result


def parse_ithome(path):
    items = []
    try:
        feed = feedparser.parse(path)
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            pub = entry.get("published", "") or entry.get("pubDate", "")
            date_str = datetime.now().strftime("%Y-%m-%d")
            if pub:
                try:
                    dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            if title and link:
                items.append({"title": title, "source": "IT之家", "url": link, "date": date_str})
    except Exception as e:
        print(f"[WARN] ithome parse: {e}", file=sys.stderr)
    return items


def parse_sspai(path):
    items = []
    try:
        feed = feedparser.parse(path)
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            pub = entry.get("published", "") or entry.get("pubDate", "")
            date_str = datetime.now().strftime("%Y-%m-%d")
            if pub:
                try:
                    dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            if title and link:
                items.append({"title": title, "source": "少数派", "url": link, "date": date_str})
    except Exception as e:
        print(f"[WARN] sspai parse: {e}", file=sys.stderr)
    return items


def parse_baidu(path):
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        for item in soup.select(".category-wrap_iQLoo .content_1YWBm")[:10]:
            a = item.find("a", class_="title_dIF3B")
            if a and a.get("href"):
                title = a.get_text(strip=True)
                href = a["href"]
                if title:
                    items.append({"title": title, "source": "百度热搜", "url": href, "date": today})
    except Exception as e:
        print(f"[WARN] baidu parse: {e}", file=sys.stderr)
    return items


def parse_tieba(path):
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        topics = data.get("data", {}).get("bang_topic", {}).get("topic_list", [])[:10]
        for topic in topics:
            title = topic.get("topic_name", "").strip()
            url = topic.get("topic_url", "").strip()
            if title:
                items.append({"title": title, "source": "贴吧热榜", "url": url, "date": today})
    except Exception as e:
        print(f"[WARN] tieba parse: {e}", file=sys.stderr)
    return items


def parse_bilibili(path):
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.read(), strict=False)
        for video in data.get("data", {}).get("list", [])[:60]:
            title = video.get("title", "").strip()
            bvid = video.get("bvid", "").strip()
            owner = video.get("owner", {}).get("name", "")
            tname = video.get("tname", "")
            if title and bvid and not any(j in title for j in BILIB_JUNK):
                # 解析阶段先卡水帖+非新闻，省得后面配额被垃圾占位
                if not any(n in title for n in BILIB_NEWS_KW):
                    continue
                url = f"https://www.bilibili.com/video/{bvid}"
                items.append({"title": title, "source": f"B站·{owner}", "url": url, "date": today, "category": tname})
    except Exception as e:
        print(f"[WARN] bilibili parse: {e}", file=sys.stderr)
    return items


def parse_zhihu(path):
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        rows = soup.select("table tbody tr")[:15]
        for row in rows:
            a = row.find("a")
            if a and a.get("href"):
                title = a.get_text(strip=True)
                href = a["href"]
                if title and len(title) > 5:
                    items.append({"title": title, "source": "知乎热榜", "url": href, "date": today})
    except Exception as e:
        print(f"[WARN] zhihu parse: {e}", file=sys.stderr)
    return items


def main():
    if len(sys.argv) < 2:
        print("Usage: news_processor.py <raw_dir>", file=sys.stderr)
        sys.exit(1)

    raw_dir = sys.argv[1]
    all_items = []

    parsers = [
        ("ithome.xml", parse_ithome),
        ("sspai.xml", parse_sspai),
        ("baidu.html", parse_baidu),
        ("tieba.json", parse_tieba),
        ("bilibili.json", parse_bilibili),
        ("zhihu.html", parse_zhihu),
    ]

    for filename, parser in parsers:
        path = os.path.join(raw_dir, filename)
        if os.path.exists(path):
            items = parser(path)
            print(f"[OK] {filename}: {len(items)} items", file=sys.stderr)
            all_items.extend(items)
        else:
            print(f"[SKIP] {filename}: not found", file=sys.stderr)

    print(f"[INFO] Total raw items: {len(all_items)}", file=sys.stderr)

    # Filter blacklisted
    before = len(all_items)
    all_items = [i for i in all_items if not is_blacklisted(i["title"])]
    print(f"[INFO] After blacklist: {len(all_items)} (removed {before - len(all_items)})", file=sys.stderr)

    # Hard drop 贴吧 (gossip/low-value), generic low-value keywords, dup events
    before = len(all_items)
    all_items = [i for i in all_items if i["source"] != "贴吧热榜"]
    all_items = [i for i in all_items if not any(k in i["title"] for k in LOWVAL)]
    all_items = [i for i in all_items if i["title"] not in DROP_EXACT]
    print(f"[INFO] After extra filters: {len(all_items)} (removed {before - len(all_items)})", file=sys.stderr)

    # B站: 白名单命中 + 新闻性门槛（rid=188 科技区源）
    before = len(all_items)
    all_items = [i for i in all_items if not i["source"].startswith("B站")
                 or (any(k in i["title"] for k in BILIB_TECH_KW)
                     and any(n in i["title"] for n in BILIB_NEWS_KW))]
    print(f"[INFO] After bilibili filter: {len(all_items)} (removed {before - len(all_items)})", file=sys.stderr)

    # Dedupe
    before = len(all_items)
    all_items = dedupe(all_items)
    print(f"[INFO] After dedup: {len(all_items)} (removed {before - len(all_items)})", file=sys.stderr)

    # Classify
    for item in all_items:
        item["category"] = classify(item["title"])

    # Sort: 技术/AI first
    cat_order = {"技术/AI": 0, "财经": 1, "国际": 2, "社会": 3, "其他": 4}

    # 打分排序
    def score_item(item):
        cat = item.get("category", "其他")
        score = 0

        # 1. 类别优先级分 (0-40)
        score += (4 - cat_order.get(cat, 4)) * 10

        # 2. 关键词匹配分 (0-30)
        title = item.get("title", "")
        cat_kws = CATEGORY_KEYWORDS.get(cat, [])
        kw_hits = sum(1 for kw in cat_kws if kw in title)
        score += min(30, kw_hits * 6)

        # 3. 来源质量分 (0-20)
        source_weights = {
            "IT之家": 20,
            "少数派": 18,
            "知乎热榜": 15,
            "百度热搜": 10,
            "B站·": 12,
        }
        src = item.get("source", "")
        matched_weight = 5
        for src_key, src_w in source_weights.items():
            if src.startswith(src_key):
                matched_weight = src_w
                break
        score += matched_weight

        # 4. 时效性分 (0-10)
        date_str = item.get("date", "")
        if date_str and date_str != "unknown":
            try:
                from datetime import datetime
                item_date = datetime.strptime(date_str, "%Y-%m-%d")
                now = datetime.now()
                days_old = (now - item_date).days
                if days_old <= 1:
                    score += 10
                elif days_old <= 3:
                    score += 7
                elif days_old <= 7:
                    score += 4
                else:
                    score += 1
            except ValueError:
                pass

        return score

    # 按类别分组 → 各类别内按分数降序
    from collections import defaultdict
    cat_items = defaultdict(list)
    for item in all_items:
        cat_items[item.get("category", "其他")].append(item)

    # 每个类别内按分数排序
    for cat in cat_items:
        cat_items[cat].sort(key=score_item, reverse=True)

    # 按类别优先级合并
    sorted_items = []
    for cat_name in sorted(cat_order.keys(), key=lambda c: cat_order.get(c, 99)):
        sorted_items.extend(cat_items.get(cat_name, []))

    all_items = sorted_items

    # Take top 30 (final 20 curated downstream), with per-source floor so a
    # single source (e.g. B站) can't be squeezed out of the candidate pool.
    SRC_MIN = {"B站": 2, "IT之家": 3, "少数派": 2, "知乎热榜": 2, "百度热搜": 2}
    SRC_MAX = {"B站": 4}
    chosen, seen_sources = [], {}
    for it in all_items:
        src_key = next((k for k in SRC_MIN if str(it.get("source", "")).startswith(k)), None)
        want = SRC_MIN.get(src_key, 0)
        if seen_sources.get(src_key, 0) < want:
            chosen.append(it)
            seen_sources[src_key] = seen_sources.get(src_key, 0) + 1
    chosen_ids = {id(x) for x in chosen}
    for it in all_items:
        if len(chosen) >= 30:
            break
        src_key = next((k for k in SRC_MIN if str(it.get("source", "")).startswith(k)), None)
        if SRC_MAX.get(src_key, 99) and seen_sources.get(src_key, 0) >= SRC_MAX.get(src_key, 99):
            continue
        if id(it) not in chosen_ids:
            chosen.append(it)
            seen_sources[src_key] = seen_sources.get(src_key, 0) + 1
            chosen_ids.add(id(it))
    all_items = chosen[:30]
    per_src = {}
    for it in all_items:
        per_src[str(it.get("source", "")).split("·")[0]] = per_src.get(str(it.get("source", "")).split("·")[0], 0) + 1
    print(f"[INFO] Top30 by source: {per_src}", file=sys.stderr)

    # Remove internal category field from Bilibili
    for item in all_items:
        item.pop("category", None)

    output = {
        "generated_at": datetime.now().isoformat(),
        "total": len(all_items),
        "items": all_items,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
