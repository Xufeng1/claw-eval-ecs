"""
Search SERP — raw web skill

POST https://google.serper.dev/search
Headers:
    X-API-KEY:  <SERP_DEV_KEY>
    Content-Type: application/json
Body (JSON):
    q:          <query>
    num:        <int, 1-10>
    hl:         "zh" | "en"  (auto-detected from query)
    gl:         "cn" | "us"  (auto-detected from query)
    start:      <int, 1-based offset>

Input:  query (str), timeout (int), num (int), start (int)
Output: {"status": <int>, "output": <list[dict]>}
"""

import json
import os
import re
import requests

SERP_API_URL = os.getenv("SERP_API_URL", "https://google.serper.dev/search")
SERP_DEV_KEY = os.getenv("SERP_DEV_KEY", "YOUR_API_KEY")


def _detect_language(query: str) -> tuple[str, str]:
    if re.search(r"[\u4e00-\u9fff]", query):
        return "zh", "cn"
    return "en", "us"


def search_serp(
    query: str,
    timeout: int = 20,
    num: int = 10,
    start: int = 1,
    raw_save_path: str | None = None,
) -> dict:
    """Search Google via SERP API and return extracted results.

    Args:
        query: Search query string.
        timeout: Request timeout in seconds.
        num: Number of results (1-10).
        start: 1-based result offset.

    Returns:
        dict with keys:
            status (int): HTTP status code, or -1 on error.
            output (list[dict]): List of result dicts with keys:
                title, link, snippet, date, query.
    """
    hl, gl = _detect_language(query)
    headers = {
        'X-API-KEY': SERP_DEV_KEY,
        'Content-Type': 'application/json'
    }
    params = {
        "q": query,
        "num": min(max(num, 1), 10),
        "hl": hl,
        "gl": gl,
        "start": max(start, 1),
    }
    payload = json.dumps(params)
    try:
        resp = requests.post(SERP_API_URL, data=payload, timeout=timeout, headers=headers)
        if raw_save_path and resp.status_code == 200:
            os.makedirs(os.path.dirname(raw_save_path) or ".", exist_ok=True)
            with open(raw_save_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
        if resp.status_code != 200:
            return {"status": resp.status_code, "output": []}
        data = resp.json()
        results = [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("description", ""),
                "date": item.get("date", ""),
                "query": query,
            }
            for item in data.get("organic", [])
        ]
        return {"status": resp.status_code, "output": results}
    except Exception as e:
        return {"status": -1, "output": []}


if __name__ == "__main__":
    result = search_serp("Python web scraping", num=3)
    print(f"status={result['status']}  count={len(result['output'])}")
    print(json.dumps(result["output"], indent=2, ensure_ascii=False)[:1000])
