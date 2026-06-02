import hashlib
import json
from datetime import datetime

import akshare as ak
import pandas as pd

from sources.base import BaseSource


class ClsSource(BaseSource):
    source_name = "cls"

    def fetch(self) -> pd.DataFrame:
        try:
            df = ak.stock_info_global_cls(symbol="全部")
            if df.empty:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for _, row in df.iterrows():
                title = str(row.get("标题", ""))
                content = str(row.get("内容", ""))
                url_hash = hashlib.md5((title + content).encode("utf-8")).hexdigest()
                pub_date = str(row.get("发布日期", ""))
                pub_time = str(row.get("发布时间", ""))
                rows.append({
                    "source": self.source_name,
                    "title": title,
                    "content": content,
                    "url": f"cls://{url_hash}",
                    "publish_time": f"{pub_date} {pub_time}".strip(),
                    "fetch_time": now,
                    "extra": json.dumps({"level": str(row.get("重要性", ""))}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[cls] fetch failed: {e}")
            return pd.DataFrame()
