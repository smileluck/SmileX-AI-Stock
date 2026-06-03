import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource


class JrjSource(BaseSource):
    source_name = "jrj"

    def fetch(self) -> pd.DataFrame:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.jrj.com.cn/",
            "Origin": "https://www.jrj.com.cn",
        }
        try:
            resp = requests.post(
                "https://gateway.jrj.com/jrj-news/news/queryNewsFlash",
                json={"pageSize": 20, "pageNo": 1},
                headers=headers,
                timeout=10,
            )
            resp.encoding = "utf-8"
            data = resp.json()
            items = data.get("data", {}).get("data", [])
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                title = (item.get("title") or "").strip()
                detail = (item.get("detail") or "").strip()
                if not title and not detail:
                    continue
                if not title:
                    title = detail[:50].strip()
                page_url = item.get("pcInfoUrl") or item.get("infoUrl") or ""
                pub_time = item.get("makeDate", "")
                rows.append({
                    "source": self.source_name,
                    "title": title,
                    "content": detail,
                    "url": page_url or f"jrj://{item.get('iiId', '')}",
                    "publish_time": pub_time,
                    "fetch_time": now,
                    "extra": json.dumps({}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[jrj] fetch failed: {e}")
            return pd.DataFrame()
