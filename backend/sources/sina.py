import hashlib
import json
from datetime import datetime

import akshare as ak
import pandas as pd

from sources.base import BaseSource


class SinaSource(BaseSource):
    source_name = "sina"

    def fetch(self) -> pd.DataFrame:
        try:
            df = ak.stock_info_global_sina()
            if df.empty:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for _, row in df.iterrows():
                content = str(row.get("内容", ""))
                title = content[:50] if len(content) > 50 else content
                url_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                rows.append({
                    "source": self.source_name,
                    "title": title,
                    "content": content,
                    "url": f"sina://{url_hash}",
                    "publish_time": str(row.get("时间", "")),
                    "fetch_time": now,
                    "extra": json.dumps({}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[sina] fetch failed: {e}")
            return pd.DataFrame()
