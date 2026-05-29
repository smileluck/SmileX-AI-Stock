import json
import pandas as pd
import akshare as ak
from datetime import datetime

SOURCE_NAME = "stock_news_em"


def fetch_stock_news(codes: list[str] | None = None) -> pd.DataFrame:
    """抓取指定股票的个股新闻"""
    if codes is None:
        codes = ["000001", "600519", "000858"]

    all_rows = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for code in codes:
        try:
            df = ak.stock_news_em(symbol=code)
            if df.empty:
                continue
            for _, row in df.iterrows():
                all_rows.append({
                    "source": SOURCE_NAME,
                    "title": str(row.get("新闻标题", "")),
                    "content": str(row.get("新闻内容", "")),
                    "url": str(row.get("新闻链接", "")),
                    "publish_time": str(row.get("发布时间", "")),
                    "fetch_time": now,
                    "extra": json.dumps({
                        "stock_code": code,
                        "media_source": str(row.get("文章来源", "")),
                    }, ensure_ascii=False),
                })
        except Exception as e:
            print(f"fetch_stock_news({code}) failed: {e}")

    return pd.DataFrame(all_rows)
