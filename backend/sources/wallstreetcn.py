import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource


class WallStreetCnSource(BaseSource):
    source_name = "wallstreetcn"

    def fetch(self) -> pd.DataFrame:
        url = "https://api-one-wscn.awtmt.com/apiv1/content/lives"
        params = {"channel": "global-channel", "limit": 50}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://wallstreetcn.com",
            "Referer": "https://wallstreetcn.com/",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            items = resp.json().get("data", {}).get("items", [])
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                title = item.get("title") or ""
                content = item.get("content_text", "")
                if not title:
                    title = content[:50] if len(content) > 50 else content
                display_time = item.get("display_time", 0)
                pub_time = datetime.fromtimestamp(display_time).strftime("%Y-%m-%d %H:%M:%S") if display_time else ""
                uri = item.get("uri", "")
                if not uri:
                    uri = f"wscn://{item.get('id', '')}"
                rows.append({
                    "source": self.source_name,
                    "title": title,
                    "content": content,
                    "url": uri,
                    "publish_time": pub_time,
                    "fetch_time": now,
                    "extra": json.dumps({"type": item.get("type", "")}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[wallstreetcn] fetch failed: {e}")
            return pd.DataFrame()
