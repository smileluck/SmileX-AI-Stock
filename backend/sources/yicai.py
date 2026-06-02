import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource


class YicaiSource(BaseSource):
    source_name = "yicai"

    def fetch(self) -> pd.DataFrame:
        url = "https://www.yicai.com/api/ajax/getlatest"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.yicai.com/",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            items = resp.json()
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                url_path = item.get("url", "")
                full_url = f"https://www.yicai.com{url_path}" if url_path.startswith("/") else url_path
                rows.append({
                    "source": self.source_name,
                    "title": item.get("NewsTitle", ""),
                    "content": item.get("NewsNotes", ""),
                    "url": full_url or f"yicai://{item.get('NewsID', '')}",
                    "publish_time": item.get("CreateDate", ""),
                    "fetch_time": now,
                    "extra": json.dumps({
                        "news_source": item.get("NewsSource", ""),
                        "channel": item.get("ChannelName", ""),
                    }, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[yicai] fetch failed: {e}")
            return pd.DataFrame()
