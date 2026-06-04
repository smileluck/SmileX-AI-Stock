import logging
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
}

# East Money board type parameters
# fs=m:90+t:2  -> 行业板块
# fs=m:90+t:3  -> 概念板块
INDUSTRY_FS = "m:90+t:2"
CONCEPT_FS = "m:90+t:3"

_SECTOR_FIELDS = "f2,f3,f4,f5,f6,f12,f14,f104,f105,f106,f128,f140,f141,f136"
_CAPITAL_FIELDS = "f2,f3,f12,f14,f62,f66,f72,f78,f84,f184,f184"


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _fetch_sector_list(fs: str, fields: str) -> list[dict]:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    try:
        r = session.get(
            "http://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1,
                "pz": 200,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": fs,
                "fields": fields,
            },
            timeout=10,
            headers=_EASTMONEY_HEADERS,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("data") and data["data"].get("diff"):
            return data["data"]["diff"]
    except Exception:
        logger.warning("Failed to fetch sector list (fs=%s)", fs, exc_info=True)
    return []


def get_sector_overview() -> dict:
    industry_raw = _fetch_sector_list(INDUSTRY_FS, _SECTOR_FIELDS)
    concept_raw = _fetch_sector_list(CONCEPT_FS, _SECTOR_FIELDS)

    def _parse_item(item: dict) -> dict:
        return {
            "code": item.get("f12", ""),
            "name": item.get("f14", ""),
            "price": _parse_float(item.get("f2")),
            "change_pct": _parse_float(item.get("f3")),
            "change": _parse_float(item.get("f4")),
            "volume": _parse_float(item.get("f5")),
            "amount": _parse_float(item.get("f6")),
            "up_count": _parse_float(item.get("f104")),
            "down_count": _parse_float(item.get("f105")),
            "flat_count": _parse_float(item.get("f106")),
            "leading_stock": item.get("f140"),
            "leading_stock_code": item.get("f128"),
            "leading_stock_change_pct": _parse_float(item.get("f136")),
        }

    return {
        "industry": [_parse_item(i) for i in industry_raw],
        "concept": [_parse_item(i) for i in concept_raw],
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_sector_capital_flow() -> dict:
    industry_raw = _fetch_sector_list(INDUSTRY_FS, _CAPITAL_FIELDS)
    concept_raw = _fetch_sector_list(CONCEPT_FS, _CAPITAL_FIELDS)

    def _parse_item(item: dict) -> dict:
        return {
            "code": item.get("f12", ""),
            "name": item.get("f14", ""),
            "change_pct": _parse_float(item.get("f3")),
            "main_net_inflow": _parse_float(item.get("f62")),
            "main_net_inflow_pct": _parse_float(item.get("f184")),
            "super_large_net": _parse_float(item.get("f66")),
            "large_net": _parse_float(item.get("f72")),
            "medium_net": _parse_float(item.get("f78")),
            "small_net": _parse_float(item.get("f84")),
        }

    return {
        "industry": [_parse_item(i) for i in industry_raw],
        "concept": [_parse_item(i) for i in concept_raw],
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
