import hashlib
import json
from datetime import datetime

import pandas as pd
import requests

from sources.base import BaseSource

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.cls.cn/telegraph",
}

_API_URL = "https://www.cls.cn/v1/roll/get_roll_list"


def _sign_cls(params: dict) -> str:
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sha1 = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1.encode("utf-8")).hexdigest()


def _fetch_cls_category(category: str, page_size: int = 20) -> pd.DataFrame:
    params = {
        "refresh_type": "1",
        "rn": str(page_size),
        "last_time": "0",
        "os": "web",
        "sv": "8.7.9",
        "app": "CailianpressWeb",
    }
    if category:
        params["category"] = category
    params["sign"] = _sign_cls(params)

    resp = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno") != 0:
        print(f"[cls] API error: errno={data.get('errno')}, msg={data.get('msg')}")
        return pd.DataFrame()

    roll_data = data.get("data", {}).get("roll_data", [])
    if not roll_data:
        return pd.DataFrame()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in roll_data:
        ctime = item.get("ctime", 0)
        pub_time = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else ""
        title = item.get("title", "")
        content = item.get("content", "")
        item_id = item.get("id", "")
        url = f"https://www.cls.cn/telegraph/{item_id}" if item_id else ""
        extra = json.dumps({
            "level": item.get("level", ""),
            "images": item.get("images", ""),
            "stock_list": item.get("stock_list", []),
        }, ensure_ascii=False)
        rows.append({
            "source": "",
            "title": title,
            "content": content,
            "url": url,
            "publish_time": pub_time,
            "fetch_time": now,
            "extra": extra,
        })
    return pd.DataFrame(rows)


class ClsSource(BaseSource):
    source_name = "cls"
    category = ""

    def fetch(self) -> pd.DataFrame:
        try:
            df = _fetch_cls_category(self.category)
            if not df.empty:
                df["source"] = self.source_name
            return df
        except Exception as e:
            print(f"[{self.source_name}] fetch failed: {e}")
            return pd.DataFrame()


class ClsRedSource(ClsSource):
    source_name = "cls_red"
    category = "red"


class ClsAnnouncementSource(ClsSource):
    source_name = "cls_announcement"
    category = "announcement"


class ClsWatchSource(ClsSource):
    source_name = "cls_watch"
    category = "watch"


class ClsHkUsSource(ClsSource):
    source_name = "cls_hk_us"
    category = "hk_us"


class ClsFundSource(ClsSource):
    source_name = "cls_fund"
    category = "fund"


class ClsRemindSource(ClsSource):
    source_name = "cls_remind"
    category = "remind"
