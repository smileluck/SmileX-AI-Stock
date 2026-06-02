import json
from datetime import datetime

import akshare as ak
import pandas as pd

from sources.base import BaseSource


class TongHuaShunSource(BaseSource):
    source_name = "tonghuashun"

    def fetch(self) -> pd.DataFrame:
        try:
            df = ak.stock_info_global_ths()
            if df.empty:
                return pd.DataFrame()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for _, row in df.iterrows():
                rows.append({
                    "source": self.source_name,
                    "title": str(row.get("标题", "")),
                    "content": str(row.get("内容", "")),
                    "url": str(row.get("链接", "")) or f"ths://{hash(row.get('标题', ''))}",
                    "publish_time": str(row.get("发布时间", "")),
                    "fetch_time": now,
                    "extra": json.dumps({}, ensure_ascii=False),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[tonghuashun] fetch failed: {e}")
            return pd.DataFrame()
