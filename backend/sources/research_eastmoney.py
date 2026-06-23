"""东方财富研报源。

接口来源：data.eastmoney.com/report/ 页面背后的 reportapi.eastmoney.com。
- /report/list?qType=0 个股研报（带评级，目标价部分有）
- /report/list?qType=1 行业研报（带行业名）

字段映射通过 _FIELD_MAP 集中维护，API 变动可单点修复。
评级归一化通过 RATING_NORMALIZE 统一为：买入/增持/中性/减持。
"""
import json
import logging
from datetime import datetime, timedelta

import pandas as pd
import requests

from sources.base import BaseSource

logger = logging.getLogger(__name__)

_API_URL = "https://reportapi.eastmoney.com/report/list"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/report/",
}

# 东财评级归一化（emRatingName / sRatingName 任一非空都归一化）
RATING_NORMALIZE = {
    "买入": "买入",
    "强烈推荐": "买入",
    "推荐": "买入",
    "增持": "增持",
    "优大于市": "增持",
    "谨慎推荐": "增持",
    "中性": "中性",
    "持有": "中性",
    "同步": "中性",
    "减持": "减持",
    "回避": "减持",
    "卖出": "减持",
    "落后大势": "减持",
}

# 买入类的归一化值
BUY_LIKE_RATINGS = ("买入", "增持")

# 研报 URL 前缀（infoCode 拼成可访问链接）
_REPORT_URL_PREFIX = "https://data.eastmoney.com/report/zw_stock.jshtml?infocode="


def _normalize_rating(raw: str) -> str:
    if not raw:
        return ""
    return RATING_NORMALIZE.get(raw.strip(), raw.strip())


def _safe_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


class ResearchEastMoneySource(BaseSource):
    """抓取东财个股研报和行业研报。"""

    source_name = "research_eastmoney"

    def fetch(self, days: int = 3, page_size: int = 100, max_pages: int = 5, chunk_days: int = 14) -> pd.DataFrame:
        """抓取近 days 天的研报。返回标准 7 列 DataFrame。

        days > chunk_days 时自动按 chunk_days 分块抓取，避免单次 API 返回上限
        （单类型 max_pages * page_size 条上限，默认 500）。

        extra 字段内嵌：org/analyst/rating/target_price/current_price/
                       report_type/industry/stock_codes/raw_rating
        """
        # 计算时间窗口分块（从最近往前倒推）
        chunks: list[tuple[str, str]] = []
        end_dt = datetime.now()
        remaining = days
        while remaining > 0:
            chunk = min(remaining, chunk_days)
            start_dt = end_dt - timedelta(days=chunk)
            chunks.append((start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")))
            end_dt = start_dt
            remaining -= chunk

        rows: list[dict] = []
        seen_urls: set[str] = set()
        for chunk_idx, (begin_date, end_date) in enumerate(chunks, 1):
            for report_type, q_type in (("stock", 0), ("industry", 1)):
                try:
                    items = self._fetch_one_type(
                        begin_date=begin_date,
                        end_date=end_date,
                        q_type=q_type,
                        page_size=page_size,
                        max_pages=max_pages,
                    )
                    for item in items:
                        parsed = self._parse_item(item, report_type)
                        if parsed and parsed["url"] not in seen_urls:
                            seen_urls.add(parsed["url"])
                            rows.append(parsed)
                except Exception:
                    logger.exception("[research_eastmoney] fetch chunk %d %s failed", chunk_idx, report_type)

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=[
            "source", "title", "content", "url",
            "publish_time", "fetch_time", "extra",
        ])

    def _fetch_one_type(
        self, begin_date: str, end_date: str, q_type: int,
        page_size: int, max_pages: int,
    ) -> list[dict]:
        """分页拉取一种类型（qType=0 或 1）的研报列表。"""
        all_items: list[dict] = []
        for page_no in range(1, max_pages + 1):
            params = {
                "industryCode": "*",
                "pageSize": str(page_size),
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": begin_date,
                "endTime": end_date,
                "pageNo": str(page_no),
                "fields": "",
                "qType": str(q_type),
            }
            try:
                resp = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=15)
                data = resp.json()
                items = data.get("data") or []
                if not items:
                    break
                all_items.extend(items)
                if len(items) < page_size:
                    break
            except Exception:
                logger.exception("[research_eastmoney] page %d qType=%d failed", page_no, q_type)
                break
        return all_items

    def _parse_item(self, item: dict, report_type: str) -> dict | None:
        """把东财一条研报解析为标准 7 列 + extra 内嵌结构。"""
        title = (item.get("title") or "").strip()
        if not title:
            return None

        # URL：优先 infoCode 拼接，回退 encodeUrl
        info_code = item.get("infoCode") or ""
        encode_url = item.get("encodeUrl") or ""
        if info_code:
            url = f"{_REPORT_URL_PREFIX}{info_code}"
        elif encode_url:
            url = f"https://data.eastmoney.com/report/zw_stock.jshtml?encodeurl={encode_url}"
        else:
            return None

        # 评级：emRatingName 优先（东财归一化），sRatingName 是机构原始
        raw_rating = (item.get("emRatingName") or "").strip()
        s_rating = (item.get("sRatingName") or "").strip()
        if not raw_rating and s_rating:
            raw_rating = s_rating
        rating = _normalize_rating(raw_rating)

        # 目标价：indvAimPriceT（东财整理后的目标价）
        target_price = _safe_float(item.get("indvAimPriceT") or item.get("indvAimPriceL"))

        # 关联个股：个股研报 stockCode，行业研报一般为空
        stock_code = (item.get("stockCode") or "").strip()
        stock_name = (item.get("stockName") or "").strip()
        stock_codes = [stock_code] if stock_code else []

        # 行业：行业研报用 industryName，个股研报用 indvInduName
        industry = (item.get("industryName") or item.get("indvInduName") or "").strip()

        # 机构：orgSName 简称优先，回退 orgName 全称
        org = (item.get("orgSName") or item.get("orgName") or "").strip()
        analyst = (item.get("researcher") or "").strip()
        publish_date = (item.get("publishDate") or "").split(" ")[0]

        summary_parts = []
        if stock_name:
            summary_parts.append(f"个股：{stock_name}")
        if industry:
            summary_parts.append(f"行业：{industry}")
        if rating:
            summary_parts.append(f"评级：{rating}")
        if target_price:
            summary_parts.append(f"目标价：{target_price:.2f}")
        summary = "，".join(summary_parts)

        extra = {
            "org": org,
            "analyst": analyst,
            "rating": rating,
            "target_price": target_price,
            "current_price": None,
            "report_type": report_type,
            "industry": industry,
            "stock_codes": stock_codes,
            "stock_name": stock_name,
            "raw_rating": raw_rating,
            "predict_this_year_pe": _safe_float(item.get("predictThisYearPe")),
            "predict_next_year_pe": _safe_float(item.get("predictNextYearPe")),
            "attach_pages": item.get("attachPages"),
        }

        return {
            "source": self.source_name,
            "title": title,
            "content": summary,
            "url": url,
            "publish_time": publish_date,
            "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extra": json.dumps(extra, ensure_ascii=False),
        }
