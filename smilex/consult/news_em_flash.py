import json
import pandas as pd
import requests
from datetime import datetime

SOURCE_NAME = "eastmoney_flash"


def fetch_em_flash(page_size: int = 30) -> pd.DataFrame:
    """抓取东方财富7x24小时财经快讯"""
    url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    params = {
        "client": "web",
        "biz": "web_news_col",
        "column": "350",
        "order": "1",
        "needInteractData": "0",
        "page_index": "1",
        "page_size": str(page_size),
        "req_trace": "smilex_news",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.eastmoney.com/",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        if not items:
            return pd.DataFrame()

        rows = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in items:
            rows.append({
                "source": SOURCE_NAME,
                "title": item.get("title", ""),
                "content": item.get("summary", ""),
                "url": item.get("url", item.get("uniqueUrl", "")),
                "publish_time": item.get("showTime", ""),
                "fetch_time": now,
                "extra": json.dumps(
                    {"mediaName": item.get("mediaName", "")},
                    ensure_ascii=False,
                ),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"fetch_em_flash failed: {e}")
        return pd.DataFrame()
