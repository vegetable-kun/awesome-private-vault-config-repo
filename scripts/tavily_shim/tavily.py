"""Minimal Tavily SDK shim — uses REST API via requests."""
import os
import requests

API_URL = "https://api.tavily.com/search"


class TavilyClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")

    def search(self, query: str, max_results: int = 5, time_range: str = "week",
               **kwargs) -> dict:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "time_range": time_range,
        }
        # Optional fields
        for key in ("search_depth", "include_answer", "include_raw_content",
                    "include_images", "include_domains", "exclude_domains"):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        resp = requests.post(API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Normalize to SDK format: results with title/url/content
        results = []
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            })
        return {"results": results}
