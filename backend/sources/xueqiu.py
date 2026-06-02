import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource


class XueqiuSource(BaseSource):
    source_name = "xueqiu"

    def fetch(self) -> pd.DataFrame:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        try:
            session.get("https://xueqiu.com/", timeout=10)
            url = "https://xueqiu.com/v6/sns/news/flash.json"
            resp = session.get(url, timeout=10)
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else data
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                title = item.get("title", "") or item.get("text", "")[:50]
                content = item.get("text", "")
                page_url = item.get("target", item.get("url", ""))
                if not page_url:
                    page_url = f"xq://{item.get('id', '')}"
                created_at = item.get("created_at", 0)
                pub_time = datetime.fromtimestamp(created_at / 1000).strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
                rows.append({
                    "source": self.source_name,
                    "title": title,
                    "content": content,
                    "url": page_url,
                    "publish_time": pub_time,
                    "fetch_time": now,
                    "extra": json.dumps({}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[xueqiu] fetch failed: {e}")
            return pd.DataFrame()
