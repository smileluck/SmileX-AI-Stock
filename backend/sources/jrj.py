import hashlib
import json
from datetime import datetime

import pandas as pd
import requests
from lxml import html as lxml_html

from sources.base import BaseSource


class JrjSource(BaseSource):
    source_name = "jrj"

    def fetch(self) -> pd.DataFrame:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        try:
            resp = requests.get("https://www.jrj.com.cn/", headers=headers, timeout=10)
            resp.encoding = "gb2312"
            tree = lxml_html.fromstring(resp.text)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for a in tree.cssselect("a[href]"):
                href = a.get("href", "")
                text = a.text_content().strip()
                if not text or len(text) < 8:
                    continue
                if not href.startswith("http"):
                    href = f"https://www.jrj.com.cn{href}" if href.startswith("/") else ""
                if not href:
                    continue
                url_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
                rows.append({
                    "source": self.source_name,
                    "title": text,
                    "content": "",
                    "url": href or f"jrj://{url_hash}",
                    "publish_time": now,
                    "fetch_time": now,
                    "extra": json.dumps({}, ensure_ascii=False),
                })
            return pd.DataFrame(rows[:30]) if rows else pd.DataFrame()
        except Exception as e:
            print(f"[jrj] fetch failed: {e}")
            return pd.DataFrame()
