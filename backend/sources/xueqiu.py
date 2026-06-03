import json
import re
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
            # Visit homepage to get initial session cookie
            session.get("https://xueqiu.com/", timeout=10)
            # The v6 endpoint returns 404 but sets auth cookies (xq_a_token etc.)
            session.get("https://xueqiu.com/v6/sns/news/flash.json", timeout=10)

            url = "https://xueqiu.com/statuses/livenews/list.json?count=15&max_id="
            resp = session.get(url, timeout=10)
            resp.encoding = "utf-8"
            data = resp.json()
            items = data.get("items", [])
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                raw_text = item.get("text", "")
                clean_text = re.sub(r"<[^>]+>", "", raw_text)
                title = clean_text[:50].strip() or "快讯"
                page_url = item.get("target", "")
                if not page_url:
                    page_url = f"https://xueqiu.com/5124430882/{item.get('id', '')}"
                elif page_url.startswith("http://"):
                    page_url = page_url.replace("http://", "https://")
                created_at = item.get("created_at", 0)
                pub_time = (
                    datetime.fromtimestamp(created_at / 1000).strftime("%Y-%m-%d %H:%M:%S")
                    if created_at
                    else ""
                )
                rows.append({
                    "source": self.source_name,
                    "title": title,
                    "content": clean_text,
                    "url": page_url,
                    "publish_time": pub_time,
                    "fetch_time": now,
                    "extra": json.dumps({}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[xueqiu] fetch failed: {e}")
            return pd.DataFrame()
