#!/usr/bin/env python3
"""广州番禺天气 + 中国气象信息 采集脚本（cron 用）

数据采集下沉到脚本，模型只做分析格式化。
API key 从 ~/.hermes/.env 读取，绝不硬编码、绝不输出。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")
WEATHER_URL = "https://wttr.in/Guangzhou+Panyu?format=j1"
SEARCH_URL = "https://api.anysearch.com/v1/search"


def _load_env_key(env_path: str = ENV_PATH, name: str = "MCP_ANYSEARCH_API_KEY") -> str:
    """从 .env 读取 key。找不到返回空串（anysearch 支持匿名，但限速更低）。"""
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def fetch_weather(timeout: int = 20) -> dict:
    req = urllib.request.Request(
        WEATHER_URL, headers={"User-Agent": "HermesCron/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def search_weather_news(key: str, timeout: int = 25) -> list[dict]:
    body = json.dumps(
        {
            "query": "广东天气 台风 气象预警 最新",
            "max_results": 5,
            "language": "zh-CN",
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "HermesCron/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(SEARCH_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        if d.get("code") != 0:
            return [{"title": f"搜索返回异常: {d.get('message')}", "url": "", "description": ""}]
        return (d.get("data") or {}).get("results") or []
    except urllib.error.HTTPError as e:
        return [{"title": f"搜索 HTTP 错误: {e.code}", "url": "", "description": ""}]
    except Exception as e:
        return [{"title": f"搜索失败: {type(e).__name__}", "url": "", "description": ""}]


def _time_emoji(hour: int) -> str:
    """时段 emoji：清晨/上午/中午/下午/傍晚/夜间。"""
    if 6 <= hour < 9:
        return "🌅"
    if 9 <= hour < 12:
        return "☀️"
    if 12 <= hour < 14:
        return "🌞"
    if 14 <= hour < 18:
        return "🌇"
    if 18 <= hour < 20:
        return "🌆"
    return "🌙"


def _temp_emoji(temp: int) -> str:
    """温度 emoji：≥30 炎热 / ≥26 偏热 / ≥20 舒适 / ≥15 偏凉 / ≥10 冷 / <10 严寒。"""
    if temp >= 30:
        return "🔥"
    if temp >= 26:
        return "🌡️"
    if temp >= 20:
        return "😊"
    if temp >= 15:
        return "🍃"
    if temp >= 10:
        return "❄️"
    return "🥶"


def _summary(desc: str, max_temp: str, min_temp: str) -> str:
    """根据天气状况给出提示。"""
    d = desc.lower()
    span = int(max_temp) - int(min_temp)
    if "rain" in d or "drizzle" in d or "shower" in d:
        return f"☔ 今天有雨，记得带伞！温差 {span}°C，建议穿轻薄外套。"
    if int(max_temp) >= 32:
        return f"🔥 高温预警！最高 {max_temp}°C，注意防暑防晒，多喝水。"
    if int(min_temp) <= 15:
        return f"🧥 早晚偏凉，最低 {min_temp}°C，建议带件外套出门。"
    return "🌤️ 天气舒适，适合户外活动。湿度适中，体感良好。"


def render(weather: dict, news: list[dict]) -> str:
    out = [f"# 采集时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    out.append("## 一、番禺天气数据（wttr.in）\n")
    try:
        c = weather["current_condition"][0]
        w = weather["weather"][0]
        desc = c["weatherDesc"][0]["value"]
        out.append(
            f"- 当前：{_temp_emoji(int(c['temp_C']))} {c['temp_C']}°C（体感 {c['FeelsLikeC']}°C）"
        )
        out.append(
            f"- 湿度：{c['humidity']}%  风速：{c['windspeedKmph']}km/h {c['winddir16Point']}"
        )
        out.append(f"- 天气：{desc}  能见度：{c['visibility']}km")
        out.append(f"- 今日：{w['mintempC']}-{w['maxtempC']}°C  紫外线：{w['uvIndex']}")

        out.append("\n### 逐时段（每 6 小时）\n")
        for h in w["hourly"]:
            t = int(h["time"]) // 100
            if t % 6 != 0:  # 只保留 00/06/12/18
                continue
            hdesc = h["weatherDesc"][0]["value"]
            out.append(
                f"{_time_emoji(t)} {t:02d}:00 │ {_temp_emoji(int(h['tempC']))} {h['tempC']}°C "
                f"│ {hdesc} │ 💧{h['humidity']}% │ 💨{h['windspeedKmph']}km/h"
            )

        out.append(f"\n### 📝 今日总结\n{_summary(desc, w['maxtempC'], w['mintempC'])}")
    except Exception as e:
        out.append(f"❌ 天气数据解析失败：{type(e).__name__}")

    out.append("\n## 二、中国气象信息（anysearch）\n")
    if not news:
        out.append("（无结果）")
    for r in news:
        title = r.get("title") or "（无标题）"
        out.append(f"- **{title}**")
        desc = (r.get("description") or "").strip()
        if desc:
            out.append(f"  {desc[:200]}")
        url = (r.get("url") or "").strip()
        if url:
            out.append(f"  {url}")
    return "\n".join(out)


def main() -> int:
    key = _load_env_key()
    try:
        weather = fetch_weather()
    except Exception as e:
        print(f"❌ 天气获取失败：{type(e).__name__}: {e}", file=sys.stderr)
        weather = {}
    news = search_weather_news(key)
    print(render(weather, news))
    return 0


if __name__ == "__main__":
    sys.exit(main())
