import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource


class EastMoneyGlobalSource(BaseSource):
    source_name = "eastmoney_global"

    def fetch(self, page_size: int = 50) -> pd.DataFrame:
        url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(page_size),
            "req_trace": "smilex",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://kuaixun.eastmoney.com/",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            items = resp.json().get("data", {}).get("fastNewsList", [])
            if not items:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for item in items:
                code = item.get("code", "")
                rows.append({
                    "source": self.source_name,
                    "title": item.get("title", ""),
                    "content": item.get("summary", ""),
                    "url": f"https://finance.eastmoney.com/a/{code}.html" if code else "",
                    "publish_time": item.get("showTime", ""),
                    "fetch_time": now,
                    "extra": json.dumps({"stockList": item.get("stockList", [])}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[eastmoney_global] fetch failed: {e}")
            return pd.DataFrame()
