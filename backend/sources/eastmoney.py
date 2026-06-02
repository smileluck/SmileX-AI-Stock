import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource


class EastMoneySource(BaseSource):
    source_name = "eastmoney"

    def fetch(self, page_size: int = 30) -> pd.DataFrame:
        url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        params = {
            "client": "web",
            "biz": "web_news_col",
            "column": "350",
            "order": "1",
            "needInteractData": "0",
            "page_index": "1",
            "page_size": str(page_size),
            "req_trace": "smilex",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.eastmoney.com/",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            items = resp.json().get("data", {}).get("list", [])
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                rows.append({
                    "source": self.source_name,
                    "title": item.get("title", ""),
                    "content": item.get("summary", ""),
                    "url": item.get("url", item.get("uniqueUrl", "")),
                    "publish_time": item.get("showTime", ""),
                    "fetch_time": now,
                    "extra": json.dumps({"mediaName": item.get("mediaName", "")}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[eastmoney] fetch failed: {e}")
            return pd.DataFrame()
