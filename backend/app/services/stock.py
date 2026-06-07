import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import akshare as ak
import requests
from lxml import etree

from app.database import get_connection
from app.services import llm

logger = logging.getLogger(__name__)


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _classify_board(code: str) -> str:
    """Classify stock code into board type."""
    if code.startswith("688"):
        return "科创板"
    if code.startswith("60") or code.startswith("00"):
        return "沪深主板"
    if code.startswith("30"):
        return "创业板"
    if code.startswith("8") or code.startswith("4"):
        return "北交所"
    return "其他"


def _round2(val) -> float | None:
    if val is None:
        return None
    return round(val, 2)


# ---------------------------------------------------------------------------
# Limit Up (涨停)
# ---------------------------------------------------------------------------

def fetch_limit_up_stocks(date: str) -> list[dict]:
    """Fetch limit-up stock pool from akshare. date format: YYYY-MM-DD."""
    ak_date = date.replace("-", "")
    try:
        df = ak.stock_zt_pool_em(date=ak_date)
        if df is None or df.empty:
            return []
    except Exception:
        logger.warning("akshare stock_zt_pool_em failed for %s", date, exc_info=True)
        return []

    items = []
    for _, row in df.iterrows():
        code = str(row.get("代码", ""))
        items.append({
            "code": code,
            "name": str(row.get("名称", "")),
            "price": _parse_float(row.get("最新价")),
            "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
            "limit_up_amount": _parse_float(row.get("封板资金")),
            "turnover_rate": _round2(_parse_float(row.get("换手率"))),
            "volume": _parse_float(row.get("成交额")),
            "amount": _parse_float(row.get("成交额")),
            "amplitude": None,
            "first_limit_up_time": str(row.get("首次封板时间", "")) or None,
            "last_limit_up_time": str(row.get("最后封板时间", "")) or None,
            "limit_up_times": int(_parse_float(row.get("连板数")) or 1),
            "reason": str(row.get("涨停统计", "")) if row.get("涨停统计") else "",
            "sector": str(row.get("所属行业", "")) if row.get("所属行业") else "",
            "board": _classify_board(code),
        })
    return items


def snapshot_limit_up_data(trade_date: str | None = None, trigger: str = "manual") -> dict:
    """Fetch limit-up stocks and persist to DB."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items = fetch_limit_up_stocks(trade_date)
    if not items:
        return {"trade_date": trade_date, "item_count": 0, "success": True, "message": "当日无涨停股或非交易日"}

    conn = get_connection()
    try:
        conn.execute("DELETE FROM limit_up_snapshot WHERE trade_date = ?", (trade_date,))
        conn.executemany(
            """INSERT INTO limit_up_snapshot
               (trade_date, code, name, price, change_pct, limit_up_amount,
                turnover_rate, volume, amount, amplitude,
                first_limit_up_time, last_limit_up_time, limit_up_times, reason, sector, created_at)
               VALUES (?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?)""",
            [
                (trade_date, i["code"], i["name"], i["price"], i["change_pct"], i["limit_up_amount"],
                 i["turnover_rate"], i["volume"], i["amount"], i["amplitude"],
                 i["first_limit_up_time"], i["last_limit_up_time"], i["limit_up_times"],
                 i["reason"], i["sector"], now)
                for i in items
            ],
        )
        conn.execute(
            "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            ("limit_up_snapshot", trigger, "[]", len(items), "ok", 0, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to snapshot limit-up data")
        return {"trade_date": trade_date, "item_count": 0, "success": False, "message": "快照失败"}
    finally:
        conn.close()

    logger.info("Limit-up snapshot for %s: %d items", trade_date, len(items))
    return {"trade_date": trade_date, "item_count": len(items), "success": True, "message": "ok"}


def get_limit_up_by_date(trade_date: str) -> dict:
    """Get limit-up data from DB, fallback to live fetch."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM limit_up_snapshot WHERE trade_date = ? ORDER BY amount DESC NULLS LAST",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        items = [dict(r) for r in rows]
    else:
        items = fetch_limit_up_stocks(trade_date)

    return {
        "trade_date": trade_date,
        "items": items,
        "item_count": len(items),
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Hot Stocks & Market Sentiment
# ---------------------------------------------------------------------------

def _strip_code(raw_code: str) -> str:
    """Strip market prefix like SZ/SH from stock code."""
    if len(raw_code) > 2 and raw_code[:2] in ("SZ", "SH"):
        return raw_code[2:]
    return raw_code


def _code_to_sina(code: str) -> str:
    """Convert pure code to sina format: sh600519 / sz000651"""
    if code.startswith("6"):
        return f"sh{code}"
    return f"sz{code}"


def _enrich_from_sina(items: list[dict]) -> list[dict]:
    """Batch enrich stock items with volume/amount/turnover from Sina HQ API."""
    if not items:
        return items
    codes = ",".join(_code_to_sina(it["code"]) for it in items)
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={codes}",
            headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        logger.debug("新浪行情补充获取失败", exc_info=True)
        return items

    lines = [l.strip() for l in r.text.strip().split("\n") if l.strip()]
    sina_map: dict[str, dict] = {}
    for line in lines:
        m = re.match(r'var hq_str_(s[hz]\d+)="(.+)"', line)
        if m:
            parts = m.group(2).split(",")
            if len(parts) >= 10:
                code = m.group(1)[2:]  # strip sh/sz prefix
                prev_close = _parse_float(parts[2])
                current = _parse_float(parts[3])
                volume_shares = _parse_float(parts[8])
                amount = _parse_float(parts[9])
                high = _parse_float(parts[4])
                low = _parse_float(parts[5])
                turnover_rate = None
                if prev_close and prev_close > 0 and volume_shares:
                    pass  # need流通股本 for turnover, skip
                sina_map[code] = {
                    "volume": volume_shares,
                    "amount": amount,
                    "change_pct": _round2(((current or 0) - (prev_close or 0)) / prev_close * 100) if prev_close else None,
                    "amplitude": _round2(((high or 0) - (low or 0)) / prev_close * 100) if prev_close else None,
                }

    for item in items:
        sd = sina_map.get(item["code"])
        if sd:
            item["volume"] = sd["volume"]
            item["amount"] = sd["amount"]
            if item.get("change_pct") is None and sd["change_pct"] is not None:
                item["change_pct"] = sd["change_pct"]
    return items


# ---------------------------------------------------------------------------
# Driving Concepts (受力分析)
# ---------------------------------------------------------------------------

def _build_concept_change_map() -> dict[str, float]:
    """Build concept_name → change_pct map from latest sector_snapshot."""
    conn = get_connection()
    try:
        date_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM sector_snapshot WHERE status='ok'"
        ).fetchone()
        if not date_row or not date_row["d"]:
            return {}
        rows = conn.execute(
            "SELECT name, change_pct FROM sector_snapshot_item WHERE trade_date = ?",
            (date_row["d"],),
        ).fetchall()
    finally:
        conn.close()
    return {r["name"]: r["change_pct"] for r in rows if r["change_pct"] is not None}


def _build_leading_stock_map() -> dict[str, list[tuple[str, float]]]:
    """Build stock_name → [(sector_name, change_pct)] from latest sector_snapshot leading stocks."""
    conn = get_connection()
    try:
        date_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM sector_snapshot WHERE status='ok'"
        ).fetchone()
        if not date_row or not date_row["d"]:
            return {}
        rows = conn.execute(
            """SELECT leading_stock, name, change_pct
               FROM sector_snapshot_item
               WHERE trade_date = ? AND leading_stock IS NOT NULL AND leading_stock != ''""",
            (date_row["d"],),
        ).fetchall()
    finally:
        conn.close()
    result: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        name = r["leading_stock"]
        if name not in result:
            result[name] = []
        if r["change_pct"] is not None:
            result[name].append((r["name"], r["change_pct"]))
    return result


def _code_to_secid(code: str) -> str:
    if code.startswith("6"):
        return f"1.{code}"
    return f"0.{code}"


def _fetch_one_stock_concepts(code: str) -> list[str]:
    """Fetch concept tag names for a single stock. Try EM push2 first, then Sina."""
    # Try EM push2 API
    secid = _code_to_secid(code)
    try:
        r = requests.get(
            "http://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": secid, "fields": "f129"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            timeout=5,
        )
        r.raise_for_status()
        tags = (r.json().get("data") or {}).get("f129") or ""
        result = [t.strip() for t in tags.split(",") if t.strip()]
        if result:
            return result
    except Exception:
        pass

    # Fallback: Sina concept page
    try:
        r = requests.get(
            f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpOtherInfo/stockid/{code}/menu_num/5.phtml",
            headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        parser = etree.HTMLParser(encoding="gbk")
        tree = etree.HTML(r.content, parser=parser)
        concepts = []
        # Find the concept table (after "所属概念板块" header)
        in_concept = False
        for table in tree.xpath("//table"):
            for row in table.xpath(".//tr"):
                cells = [c.xpath("string(.)").strip() for c in row.xpath(".//td | .//th")]
                text = "".join(cells)
                if "所属概念板块" in text:
                    in_concept = True
                    continue
                if "所属行业" in text:
                    in_concept = False
                    continue
                if in_concept and cells:
                    name = cells[0].strip()
                    if name and name not in ("概念板块", "同概念个股", "备注：此为申万行业分类"):
                        concepts.append(name)
        return concepts
    except Exception:
        return []


def _enrich_driving_concepts(items: list[dict], top_k: int = 3) -> list[dict]:
    """Enrich each stock item with top-K driving concepts sorted by change_pct desc."""
    if not items:
        return items

    concept_map = _build_concept_change_map()
    leading_map = _build_leading_stock_map()

    # Try EM API for concept tags (primary source)
    codes = [it["code"] for it in items]
    stock_tags: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one_stock_concepts, c): c for c in set(codes)}
        for f in as_completed(futures, timeout=15):
            stock_tags[futures[f]] = f.result()

    api_hit = any(v for v in stock_tags.values())

    for item in items:
        matched: list[dict] = []

        # Source 1: EM API concept tags matched against sector_snapshot
        tags = stock_tags.get(item["code"], [])
        for tag in tags:
            pct = concept_map.get(tag)
            if pct is not None:
                matched.append({"name": tag, "change_pct": round(pct, 2)})

        # Source 2 (fallback): DB leading_stock matching
        if not api_hit or len(matched) < top_k:
            stock_name = item.get("name", "")
            sectors = leading_map.get(stock_name, [])
            for sec_name, sec_pct in sectors:
                if not any(m["name"] == sec_name for m in matched):
                    matched.append({"name": sec_name, "change_pct": round(sec_pct, 2)})

        matched.sort(key=lambda x: x["change_pct"], reverse=True)
        item["driving_concepts"] = matched[:top_k]
        item["concepts"] = tags[:8]
    return items


_XQ_HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://xueqiu.com/hq",
    "X-Requested-With": "XMLHttpRequest",
}


def _fetch_hot_em(top_n: int) -> list[dict]:
    """东方财富个股人气榜"""
    try:
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return []
        items = []
        for idx, row in df.head(top_n).iterrows():
            items.append({
                "code": _strip_code(str(row.get("代码", ""))),
                "name": str(row.get("股票名称", "")),
                "price": _parse_float(row.get("最新价")),
                "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
                "hot_rank": int(_parse_float(row.get("当前排名")) or (idx + 1)),
                "turnover_rate": None,
                "amount": None,
                "volume": None,
                "net_inflow": None,
                "industry": "",
            })
        items = _enrich_from_sina(items)
        return items
    except Exception:
        logger.debug("东方财富人气榜获取失败", exc_info=True)
        return []


def _fetch_hot_em_surge(top_n: int) -> list[dict]:
    """东方财富飙升榜"""
    try:
        df = ak.stock_hot_up_em()
        if df is None or df.empty:
            return []
        items = []
        for idx, row in df.head(top_n).iterrows():
            items.append({
                "code": _strip_code(str(row.get("代码", ""))),
                "name": str(row.get("股票名称", "")),
                "price": _parse_float(row.get("最新价")),
                "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
                "hot_rank": int(_parse_float(row.get("当前排名")) or (idx + 1)),
                "turnover_rate": None,
                "amount": None,
                "volume": None,
                "net_inflow": None,
                "industry": "",
            })
        items = _enrich_from_sina(items)
        return items
    except Exception:
        logger.debug("东方财富飙升榜获取失败", exc_info=True)
        return []


def _parse_ths_amount(val: str) -> float | None:
    """Parse THS amount string like '13.83亿' or '9389.91万'."""
    if not val or val == "--":
        return None
    val = val.strip()
    try:
        if val.endswith("亿"):
            return float(val[:-1]) * 1_0000_0000
        if val.endswith("万"):
            return float(val[:-1]) * 1_0000
        return float(val)
    except (ValueError, TypeError):
        return None


_THS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://q.10jqka.com.cn/",
}


def _fetch_hot_ths(top_n: int) -> list[dict]:
    """同花顺涨幅排行"""
    try:
        r = requests.get(
            "http://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page/1/ajax/1/",
            headers=_THS_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        parser = etree.HTMLParser(encoding="gbk")
        tree = etree.HTML(r.content, parser=parser)
        rows = tree.xpath("//table/tbody/tr")
        if not rows:
            return []
    except Exception:
        logger.debug("同花顺涨幅排行获取失败", exc_info=True)
        return []

    items = []
    for row in rows[:top_n]:
        tds = row.xpath(".//td")
        vals = [td.xpath("string(.)").strip() for td in tds]
        if len(vals) < 11:
            continue
        code = vals[1]
        name = vals[2]
        if not code or not name:
            continue
        pct = _round2(_parse_float(vals[4]))
        items.append({
            "code": code,
            "name": name,
            "price": _parse_float(vals[3]),
            "change_pct": pct,
            "hot_rank": len(items) + 1,
            "turnover_rate": _round2(_parse_float(vals[7])),
            "amount": _parse_ths_amount(vals[10]),
            "volume": None,
            "net_inflow": None,
            "industry": "",

        })
    items = _enrich_from_sina(items)
    return items


def _fetch_hot_xq(order_by: str, top_n: int) -> list[dict]:
    """雪球热度排行 - 直接 HTTP 请求，只取一页"""
    try:
        r = requests.get(
            "https://xueqiu.com/service/v5/stock/screener/screen",
            params={
                "category": "CN",
                "size": str(top_n),
                "order": "desc",
                "order_by": order_by,
                "only_count": "0",
                "page": "1",
            },
            headers=_XQ_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        stock_list = data.get("data", {}).get("list") or []
    except Exception:
        logger.debug("雪球排行获取失败 (order_by=%s)", order_by, exc_info=True)
        return []

    items = []
    for idx, s in enumerate(stock_list[:top_n]):
        pct = _round2(_parse_float(s.get("pct")))
        items.append({
            "code": _strip_code(str(s.get("symbol", ""))),
            "name": str(s.get("name", "")),
            "price": _parse_float(s.get("current")),
            "change_pct": pct,
            "hot_rank": idx + 1,
            "turnover_rate": None,
            "amount": None,
            "volume": None,
            "net_inflow": None,
            "industry": "",

        })
    items = _enrich_from_sina(items)
    return items


def get_stock_hot_rank(top_n: int = 20) -> list[dict]:
    """Fetch stock popularity ranking from all sources, returns list of {source, items}."""
    result = []

    em_items = _fetch_hot_em(top_n)
    if em_items:
        result.append({"source": "东方财富人气", "items": em_items})
        logger.info("热门个股 [东方财富人气]: %d 条", len(em_items))

    em_surge = _fetch_hot_em_surge(top_n)
    if em_surge:
        result.append({"source": "东方财富飙升", "items": em_surge})
        logger.info("热门个股 [东方财富飙升]: %d 条", len(em_surge))

    ths_items = _fetch_hot_ths(top_n)
    if ths_items:
        result.append({"source": "同花顺涨幅", "items": ths_items})
        logger.info("热门个股 [同花顺涨幅]: %d 条", len(ths_items))

    xq_follow = _fetch_hot_xq("follow", top_n)
    if xq_follow:
        result.append({"source": "雪球关注", "items": xq_follow})
        logger.info("热门个股 [雪球关注]: %d 条", len(xq_follow))

    xq_tweet = _fetch_hot_xq("tweet", top_n)
    if xq_tweet:
        result.append({"source": "雪球讨论", "items": xq_tweet})
        logger.info("热门个股 [雪球讨论]: %d 条", len(xq_tweet))

    xq_deal = _fetch_hot_xq("deal", top_n)
    if xq_deal:
        result.append({"source": "雪球交易", "items": xq_deal})
        logger.info("热门个股 [雪球交易]: %d 条", len(xq_deal))

    # Enrich driving concepts for all items at once (shared concept map)
    all_items = [it for src in result for it in src["items"]]
    if all_items:
        _enrich_driving_concepts(all_items)

    if not result:
        logger.warning("所有热门个股数据源均失败")
    return result


def get_market_sentiment() -> dict:
    """Get market sentiment data (up/down/flat counts, limit up/down)."""
    up_count = 0
    down_count = 0
    flat_count = 0
    limit_up_count = 0
    limit_down_count = 0
    sentiment_score = None

    try:
        df = ak.stock_market_activity_legu()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                item_name = str(row.get("item", ""))
                value = _parse_float(row.get("value"))
                if "上涨" in item_name:
                    up_count = int(value or 0)
                elif "下跌" in item_name:
                    down_count = int(value or 0)
                elif "平盘" in item_name:
                    flat_count = int(value or 0)
                elif "涨停" in item_name:
                    limit_up_count = int(value or 0)
                elif "跌停" in item_name:
                    limit_down_count = int(value or 0)
                elif "赚钱" in item_name or "情绪" in item_name:
                    sentiment_score = _round2(value)
    except Exception:
        logger.warning("akshare stock_market_activity_legu failed", exc_info=True)

    hot_stocks = get_stock_hot_rank()
    hot_concepts = _get_hot_concepts()

    return {
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "sentiment_score": sentiment_score,
        "hot_stocks": hot_stocks,
        "hot_concepts": hot_concepts,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _get_hot_concepts(limit: int = 5) -> list[dict]:
    """Get top concepts and industries from DB snapshot."""

    def _resolve_code(name: str) -> str:
        """Resolve stock name to code via DB or Sina search."""
        # Try DB first
        for table in ("limit_up_snapshot", "stock_recommendation"):
            try:
                row = conn.execute(f"SELECT code FROM {table} WHERE name = ? LIMIT 1", (name,)).fetchone()
                if row:
                    return row["code"]
            except Exception:
                pass
        # Fallback: Sina suggest API
        try:
            r = requests.get(
                f"https://suggest3.sinajs.cn/suggest/type=11,12&key={name}",
                headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
                timeout=5,
            )
            val = r.text.split('="')[1].rstrip('";').strip('"')
            if val:
                parts = val.split(",")
                if len(parts) >= 3:
                    return parts[2]
        except Exception:
            pass
        return ""

    conn = get_connection()
    try:
        date_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM sector_snapshot WHERE status='ok'"
        ).fetchone()
        if not date_row or not date_row["d"]:
            return []
        trade_date = date_row["d"]

        rows = conn.execute(
            """SELECT name, sector_type, change_pct, main_net_inflow,
                      leading_stock, leading_stock_code, leading_stock_change_pct
               FROM sector_snapshot_item
               WHERE trade_date = ? AND sector_type = 'concept'
               ORDER BY change_pct DESC NULLS LAST LIMIT ?""",
            (trade_date, limit),
        ).fetchall()
        concepts = [dict(r) for r in rows]

        rows2 = conn.execute(
            """SELECT name, sector_type, change_pct, main_net_inflow,
                      leading_stock, leading_stock_code, leading_stock_change_pct
               FROM sector_snapshot_item
               WHERE trade_date = ? AND sector_type = 'industry'
               ORDER BY change_pct DESC NULLS LAST LIMIT ?""",
            (trade_date, limit),
        ).fetchall()
        industries = [dict(r) for r in rows2]

        result = []
        for item in concepts + industries:
            leading_name = item.get("leading_stock") or ""
            leading_code = item.get("leading_stock_code") or ""
            if leading_name and not leading_code:
                leading_code = _resolve_code(leading_name)
            result.append({
                "name": item.get("name", ""),
                "sector_type": item.get("sector_type", ""),
                "change_pct": _round2(item.get("change_pct")),
                "main_net_inflow": item.get("main_net_inflow"),
                "leading_stock": leading_name,
                "leading_stock_code": leading_code,
                "leading_stock_change_pct": _round2(item.get("leading_stock_change_pct")),
            })
        return result
    finally:
        conn.close()


def get_stock_overview() -> dict:
    """Aggregate overview: sentiment + limit-up data."""
    sentiment = get_market_sentiment()
    trade_date = datetime.now().strftime("%Y-%m-%d")
    limit_up = get_limit_up_by_date(trade_date)
    return {
        "sentiment": sentiment,
        "limit_up": limit_up,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# AI Recommendations
# ---------------------------------------------------------------------------

_REC_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责根据当日市场数据为用户挑选具有投资价值的个股。

请根据以下市场数据，推荐 5-10 只有潜力的个股。要求：

1. 每只股票必须包含以下字段，以 JSON 数组格式输出：
   - code: 股票代码（如 "600519"）
   - name: 股票名称
   - reason: 推荐理由（50-100字，结合当日市场表现和基本面）
   - strategy: 操作策略（如 "短线追涨"、"低吸等待反弹"、"趋势持有"）
   - current_price: 当前价格（根据最新行情数据填写）
   - buy_low: 建议买入区间下限
   - buy_high: 建议买入区间上限
   - target_price: 目标价
   - stop_loss_price: 止损价
   - take_profit_price: 止盈价
   - risk_level: 风险等级 "low"/"medium"/"high"
   - confidence: 信心度 0-1 之间的小数
   - sector: 所属行业/板块
   - score: 综合评分 1-10

2. 推荐原则：
   - 优先从涨停股中筛选强势品种
   - 关注主力资金大幅流入的个股
   - 结合热门板块和当日市场热点
   - 兼顾不同风险偏好的品种
   - 不推荐ST、*ST股票
   - 买入区间应基于当前价格合理设定，buy_low 不高于当前价，buy_high 可略高于当前价
   - 止损价一般设在买入区间下限下方 2-5%
   - 止盈价和目标价应体现合理盈利预期

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


def _get_rec_context(trade_date: str, phase: str = "afternoon") -> str:
    """Collect context data for recommendation generation."""
    parts = []

    # Limit-up data
    conn = get_connection()
    try:
        if phase == "morning":
            # 早盘尚无当日涨停数据，使用昨日涨停
            prev_row = conn.execute(
                "SELECT MAX(trade_date) as d FROM limit_up_snapshot WHERE trade_date < ?",
                (trade_date,),
            ).fetchone()
            lu_date = prev_row["d"] if prev_row and prev_row["d"] else trade_date
        else:
            lu_date = trade_date
        rows = conn.execute(
            "SELECT code, name, change_pct, amount, limit_up_times, sector FROM limit_up_snapshot WHERE trade_date = ? ORDER BY amount DESC LIMIT 20",
            (lu_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        label = "昨日涨停股" if phase == "morning" else "今日涨停股"
        lines = [f"=== {label} ({len(rows)}只) ==="]
        for r in rows:
            lines.append(f"  {r['name']}({r['code']}) 涨幅{r['change_pct']}% 连板{r['limit_up_times']} 行业:{r['sector']}")
        parts.append("\n".join(lines))

    # Hot sectors
    conn = get_connection()
    try:
        if phase == "morning":
            prev_row = conn.execute(
                "SELECT MAX(trade_date) as d FROM sector_snapshot_item WHERE trade_date < ?",
                (trade_date,),
            ).fetchone()
            sec_date = prev_row["d"] if prev_row and prev_row["d"] else trade_date
        else:
            sec_date = trade_date
        rows = conn.execute(
            "SELECT name, change_pct, main_net_inflow, leading_stock FROM sector_snapshot_item WHERE trade_date = ? AND sector_type = 'industry' ORDER BY change_pct DESC LIMIT 10",
            (sec_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        lines = ["=== 热门行业 TOP10 ==="]
        for r in rows:
            inflow = (r["main_net_inflow"] or 0) / 1e8
            lines.append(f"  {r['name']}: 涨幅{r['change_pct']}% 主力净流入{inflow:.2f}亿 领涨:{r['leading_stock']}")
        parts.append("\n".join(lines))

    # Recent news — include overnight news for morning phase
    conn = get_connection()
    try:
        if phase == "morning":
            rows = conn.execute(
                "SELECT title, source FROM news WHERE date(publish_time) >= date(?, '-1 day') ORDER BY publish_time DESC LIMIT 20",
                (trade_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT title, source FROM news WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT 15",
                (trade_date,),
            ).fetchall()
    finally:
        conn.close()

    if rows:
        lines = [f"=== 最新新闻 ({len(rows)}条) ==="]
        for r in rows:
            lines.append(f"  [{r['source']}] {r['title']}")
        parts.append("\n".join(lines))

    return f"=== 交易日期: {trade_date} ===\n\n" + "\n\n".join(parts)


def _parse_recommendation_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def generate_recommendations(trade_date: str | None = None, phase: str = "afternoon") -> dict:
    """Generate AI stock recommendations."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context = _get_rec_context(trade_date, phase)

    messages = [
        {"role": "system", "content": _REC_SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    response = llm.analysis_chat(messages)
    recs = _parse_recommendation_json(response)

    if not recs:
        logger.warning("No recommendations parsed from LLM response")
        return {"items": [], "total": 0}

    conn = get_connection()
    try:
        # Remove existing recommendations for this date and phase
        conn.execute("DELETE FROM stock_recommendation WHERE trade_date = ? AND phase = ?", (trade_date, phase))

        for rec in recs:
            conn.execute(
                """INSERT INTO stock_recommendation
                   (trade_date, code, name, reason, strategy, target_price, stop_loss_price,
                    risk_level, confidence, sector, score, model_used, status,
                    current_price, buy_low, buy_high, take_profit_price,
                    phase, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?,?)""",
                (
                    trade_date,
                    rec.get("code", ""),
                    rec.get("name", ""),
                    rec.get("reason", ""),
                    rec.get("strategy", ""),
                    _parse_float(rec.get("target_price")),
                    _parse_float(rec.get("stop_loss_price")),
                    rec.get("risk_level", "medium"),
                    _parse_float(rec.get("confidence")) or 0.5,
                    rec.get("sector", ""),
                    _parse_float(rec.get("score")) or 0,
                    llm.get_model_for_function("stock_recommendation"),
                    "pending",
                    _parse_float(rec.get("current_price")),
                    _parse_float(rec.get("buy_low")),
                    _parse_float(rec.get("buy_high")),
                    _parse_float(rec.get("take_profit_price")),
                    phase,
                    now,
                    now,
                ),
            )
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM stock_recommendation WHERE trade_date = ? AND phase = ? ORDER BY score DESC",
            (trade_date, phase),
        ).fetchall()
        items = [dict(r) for r in rows]
    except Exception:
        conn.rollback()
        logger.exception("Failed to save recommendations")
        raise
    finally:
        conn.close()

    logger.info("Generated %d %s recommendations for %s", len(items), phase, trade_date)
    return {"items": items, "total": len(items)}


def get_recommendations_by_date(trade_date: str, phase: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        if phase:
            rows = conn.execute(
                "SELECT * FROM stock_recommendation WHERE trade_date = ? AND phase = ? ORDER BY score DESC",
                (trade_date, phase),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stock_recommendation WHERE trade_date = ? ORDER BY score DESC",
                (trade_date,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recommendation_history(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM stock_recommendation").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM stock_recommendation ORDER BY trade_date DESC, score DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()


def update_morning_performance(trade_date: str | None = None) -> dict:
    """Update actual_return_pct for morning recommendations using live prices."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, code FROM stock_recommendation WHERE trade_date = ? AND phase = 'morning' AND status = 'pending'",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"updated": 0, "trade_date": trade_date}

    # Batch fetch prices from Sina
    codes = [r["code"] for r in rows]
    price_map: dict[str, float | None] = {}
    prev_close_map: dict[str, float | None] = {}

    sina_codes = ",".join(_code_to_sina(c) for c in codes)
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={sina_codes}",
            headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
        for line in r.text.strip().split("\n"):
            m = re.match(r'var hq_str_(s[hz]\d+)="(.+)"', line.strip())
            if m:
                parts = m.group(2).split(",")
                if len(parts) >= 4:
                    code = m.group(1)[2:]
                    prev_close = _parse_float(parts[2])
                    current = _parse_float(parts[3])
                    prev_close_map[code] = prev_close
                    price_map[code] = current
    except Exception:
        logger.warning("Failed to fetch prices for morning performance update", exc_info=True)
        return {"updated": 0, "trade_date": trade_date}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = 0
    conn = get_connection()
    try:
        for row in rows:
            code = row["code"]
            current = price_map.get(code)
            prev_close = prev_close_map.get(code)
            if current is not None and prev_close and prev_close > 0:
                ret_pct = round((current - prev_close) / prev_close * 100, 2)
                conn.execute(
                    "UPDATE stock_recommendation SET actual_return_pct = ?, status = 'completed', updated_at = ? WHERE id = ?",
                    (ret_pct, now, row["id"]),
                )
                updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to update morning performance")
    finally:
        conn.close()

    logger.info("Updated morning performance for %d / %d stocks on %s", updated, len(rows), trade_date)
    return {"updated": updated, "total": len(rows), "trade_date": trade_date}
