import hashlib
import json
import pandas as pd
import akshare as ak
from datetime import datetime, timedelta

SOURCE_NAME = "cctv_news"


def fetch_cctv_news(date: str = "") -> pd.DataFrame:
    """通过 AKShare 抓取央视新闻联播内容"""
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    try:
        df = ak.news_cctv(date=date)
        if df.empty:
            return pd.DataFrame()

        rows = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for _, row in df.iterrows():
            title = str(row.get("title", ""))
            content = str(row.get("content", ""))
            url_hash = hashlib.md5((title + content[:200]).encode("utf-8")).hexdigest()

            rows.append({
                "source": SOURCE_NAME,
                "title": title,
                "content": content,
                "url": f"cctv://{date}/{url_hash}",
                "publish_time": str(row.get("date", date)),
                "fetch_time": now,
                "extra": json.dumps({"date": date}, ensure_ascii=False),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"fetch_cctv_news failed: {e}")
        return pd.DataFrame()
