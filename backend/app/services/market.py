import logging
from datetime import datetime

import akshare as ak
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Sina source uses codes like sh000001, sz399001
CN_INDEX_CODES = {
    "sh000001",  # 上证指数
    "sz399001",  # 深证成指
    "sz399006",  # 创业板指
    "sh000688",  # 科创50
    "sh000300",  # 沪深300
    "sh000016",  # 上证50
    "sh000905",  # 中证500
    "sh000852",  # 中证1000
}

# East Money secids for global indices
GLOBAL_INDEX_SECIDS = [
    "100.DJIA",   # 道琼斯
    "100.NDX",    # 纳斯达克
    "100.SPX",    # 标普500
    "100.N225",   # 日经225
    "100.KS11",   # 韩国KOSPI
    "100.HSI",    # 恒生指数
    "100.FTSE",   # 富时100
    "100.GDAXI",  # 德国DAX
    "100.FCHI",   # 法国CAC40
]

GLOBAL_INDEX_NAMES = {
    "DJIA": "道琼斯",
    "NDX": "纳斯达克",
    "SPX": "标普500",
    "N225": "日经225",
    "KS11": "韩国KOSPI",
    "HSI": "恒生指数",
    "FTSE": "富时100",
    "GDAXI": "德国DAX",
    "FCHI": "法国CAC40",
}


def _parse_float(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_cn_indices() -> list[dict]:
    try:
        df = ak.stock_zh_index_spot_sina()
    except Exception:
        logger.warning("Failed to fetch Chinese indices from Sina", exc_info=True)
        return []

    results = []
    for _, row in df.iterrows():
        code = str(row.iloc[0])
        if code not in CN_INDEX_CODES:
            continue
        results.append({
            "code": code,
            "name": str(row.iloc[1]),
            "price": _parse_float(row.iloc[2]),
            "change": _parse_float(row.iloc[3]),
            "change_pct": _parse_float(row.iloc[4]),
            "open": _parse_float(row.iloc[5]),
            "prev_close": _parse_float(row.iloc[6]),
            "high": _parse_float(row.iloc[7]),
            "low": _parse_float(row.iloc[8]),
            "volume": _parse_float(row.iloc[9]),
            "amount": _parse_float(row.iloc[10]),
            "amplitude": None,
            "update_time": None,
        })
    return results


def _get_global_indices() -> list[dict]:
    secids = ",".join(GLOBAL_INDEX_SECIDS)
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    try:
        r = session.get(
            "http://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2,
                "fields": "f2,f3,f4,f12,f14,f15,f16,f17,f18",
                "secids": secids,
            },
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        r.raise_for_status()
        items = r.json()["data"]["diff"]
    except Exception:
        logger.warning("Failed to fetch global indices from EastMoney", exc_info=True)
        return []

    results = []
    for item in items:
        code = item.get("f12", "")
        results.append({
            "code": code,
            "name": GLOBAL_INDEX_NAMES.get(code, item.get("f14", "")),
            "price": _parse_float(item.get("f2")),
            "change": _parse_float(item.get("f4")),
            "change_pct": _parse_float(item.get("f3")),
            "open": _parse_float(item.get("f17")),
            "prev_close": _parse_float(item.get("f18")),
            "high": _parse_float(item.get("f15")),
            "low": _parse_float(item.get("f16")),
            "volume": None,
            "amount": None,
            "amplitude": None,
            "update_time": None,
        })
    return results


def get_market_overview() -> dict:
    return {
        "cn_main": _get_cn_indices(),
        "international": _get_global_indices(),
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
