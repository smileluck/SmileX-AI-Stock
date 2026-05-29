import hashlib
import json
import pandas as pd
import akshare as ak
from datetime import datetime

SOURCE_NAME = "cls_telegraph"


def fetch_cls_telegraph() -> pd.DataFrame:
    """通过 AKShare 抓取财联社电报快讯"""
    try:
        df = ak.stock_info_global_cls(symbol="全部")
        if df.empty:
            return pd.DataFrame()

        rows = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for _, row in df.iterrows():
            title = str(row.get("标题", ""))
            content = str(row.get("内容", ""))
            pub_date = str(row.get("发布日期", ""))
            pub_time = str(row.get("发布时间", ""))
            url_hash = hashlib.md5((title + content).encode("utf-8")).hexdigest()

            rows.append({
                "source": SOURCE_NAME,
                "title": title,
                "content": content,
                "url": f"cls://{url_hash}",
                "publish_time": f"{pub_date} {pub_time}".strip(),
                "fetch_time": now,
                "extra": json.dumps(
                    {"level": str(row.get("重要性", ""))},
                    ensure_ascii=False,
                ),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"fetch_cls_telegraph failed: {e}")
        return pd.DataFrame()
