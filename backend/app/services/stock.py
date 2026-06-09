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


def _is_main_board(code: str) -> bool:
    """Return True only for 沪深主板 stocks (600/601/603/605 + 000/001/002/003)."""
    return code.startswith(("60", "00"))


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
    """Strip market prefix like SZ/SH/BJ from stock code."""
    if len(raw_code) > 2 and raw_code[:2] in ("SZ", "SH", "BJ"):
        return raw_code[2:]
    return raw_code


def _code_to_sina(code: str) -> str:
    """Convert pure code to sina format: sh600519 / sz000651 / bj830799"""
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith("8") or code.startswith("4"):
        return f"bj{code}"
    return f"sz{code}"


_SINA_HQ_PATTERN = re.compile(r'var hq_str_((?:s[hz]|bj)\d+)="(.+)"')


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
        m = _SINA_HQ_PATTERN.match(line)
        if m:
            parts = m.group(2).split(",")
            if len(parts) >= 10:
                code = m.group(1)[2:]  # strip sh/sz/bj prefix
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
# Morning Auction Analysis
# ---------------------------------------------------------------------------

def _preselect_morning_candidates(trade_date: str) -> list[dict]:
    """Select ~20 candidate stocks from DB for morning auction analysis."""
    candidates: dict[str, dict] = {}

    conn = get_connection()
    try:
        # Yesterday's limit-up stocks (top 12 by amount)
        prev_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM limit_up_snapshot WHERE trade_date < ?",
            (trade_date,),
        ).fetchone()
        lu_date = prev_row["d"] if prev_row and prev_row["d"] else trade_date

        rows = conn.execute(
            "SELECT code, name, limit_up_times, sector, amount "
            "FROM limit_up_snapshot WHERE trade_date = ? ORDER BY amount DESC LIMIT 12",
            (lu_date,),
        ).fetchall()
        for r in rows:
            if not _is_main_board(r["code"]):
                continue
            candidates[r["code"]] = {
                "code": r["code"],
                "name": r["name"],
                "source": f"昨日涨停(连板{r['limit_up_times'] or 1})",
            }

        # Hot sector leading stocks (top 10)
        sec_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM sector_snapshot_item WHERE trade_date < ?",
            (trade_date,),
        ).fetchone()
        sec_date = sec_row["d"] if sec_row and sec_row["d"] else trade_date

        rows = conn.execute(
            "SELECT leading_stock, leading_stock_code, name "
            "FROM sector_snapshot_item "
            "WHERE trade_date = ? AND sector_type = 'industry' "
            "AND leading_stock_code IS NOT NULL "
            "ORDER BY change_pct DESC LIMIT 10",
            (sec_date,),
        ).fetchall()
        for r in rows:
            code = r["leading_stock_code"]
            if code and code not in candidates and _is_main_board(code):
                candidates[code] = {
                    "code": code,
                    "name": r["leading_stock"],
                    "source": f"行业领涨({r['name']})",
                }
    finally:
        conn.close()

    return list(candidates.values())[:20]


def _fetch_one_stock_auction(code: str) -> dict | None:
    """Fetch auction order book data for a single stock from East Money push2 API."""
    secid = _code_to_secid(code)
    try:
        r = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": secid,
                "fltt": "2",
                "fields": (
                    "f43,f46,f47,f48,f50,f51,f52,f60,f161,"
                    "f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,"
                    "f31,f32,f33,f34,f35,f36,f37,f38,f39,f40"
                ),
            },
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json().get("data")
        if not data:
            return None
    except Exception:
        logger.debug("竞价数据获取失败: %s", code, exc_info=True)
        return None

    prev_close = _parse_float(data.get("f60"))
    current = _parse_float(data.get("f43"))
    limit_up = _parse_float(data.get("f51"))

    buy_vols = [_parse_float(data.get(f"f{i}")) or 0 for i in (12, 14, 16, 18, 20)]
    sell_vols = [_parse_float(data.get(f"f{i}")) or 0 for i in (32, 34, 36, 38, 40)]
    total_buy = sum(buy_vols)
    total_sell = sum(sell_vols)

    change_pct = round((current - prev_close) / prev_close * 100, 2) if prev_close and current else None
    buy_sell_ratio = round(total_buy / total_sell, 2) if total_sell else None
    volume_ratio = _parse_float(data.get("f50"))

    signal_tags: list[str] = []
    if current and limit_up and current >= limit_up:
        signal_tags.append("竞价涨停")
    if buy_sell_ratio is not None:
        if buy_sell_ratio > 3:
            signal_tags.append(f"买盘强势(比{buy_sell_ratio})")
        elif buy_sell_ratio < 0.5:
            signal_tags.append(f"卖盘压力大(比{buy_sell_ratio})")
    if volume_ratio is not None and volume_ratio > 5:
        signal_tags.append(f"量比异常({volume_ratio})")

    return {
        "code": code,
        "current": current,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "volume": _parse_float(data.get("f47")),
        "amount": _parse_float(data.get("f46")),
        "volume_ratio": volume_ratio,
        "turnover": _parse_float(data.get("f48")),
        "limit_up": limit_up,
        "limit_down": _parse_float(data.get("f52")),
        "total_buy_vol": total_buy,
        "total_sell_vol": total_sell,
        "buy_sell_ratio": buy_sell_ratio,
        "order_ratio": _parse_float(data.get("f161")),
        "is_limit_up": current is not None and limit_up is not None and current >= limit_up,
        "signal_tags": signal_tags,
    }


def _fetch_auction_data(candidates: list[dict]) -> list[dict]:
    """Fetch auction data for candidate stocks with 2 concurrency."""
    results: list[dict] = []
    code_to_cand = {c["code"]: c for c in candidates}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_fetch_one_stock_auction, c["code"]): c["code"] for c in candidates}
        for f in as_completed(futures, timeout=60):
            result = f.result()
            if result:
                code = futures[f]
                cand = code_to_cand[code]
                result["name"] = cand["name"]
                result["source"] = cand["source"]
                results.append(result)

    return results


def _format_auction_context(auction_data: list[dict]) -> str:
    """Format auction data as context text for AI recommendation."""
    if not auction_data:
        return ""

    sorted_data = sorted(auction_data, key=lambda x: x.get("change_pct") or 0, reverse=True)

    lines = [f"=== 集合竞价分析 ({len(sorted_data)}只) ==="]
    lines.append("说明: 竞价结束后(9:25)盘口数据，连续竞价开盘前(9:30)")

    for d in sorted_data:
        name = d.get("name", "")
        code = d.get("code", "")
        pct = d.get("change_pct")
        current = d.get("current")
        prev_close = d.get("prev_close")
        buy_sell_ratio = d.get("buy_sell_ratio")
        total_buy = d.get("total_buy_vol", 0)
        total_sell = d.get("total_sell_vol", 0)
        vol_ratio = d.get("volume_ratio")
        source = d.get("source", "")
        tags = d.get("signal_tags", [])

        pct_str = f"{pct:+.2f}" if pct is not None else "N/A"
        signal_str = f" 信号:[{','.join(tags)}]" if tags else ""

        lines.append(
            f"  {name}({code}) 竞价{pct_str}% 竞价价{current} 昨收{prev_close} "
            f"买盘{total_buy}股 卖盘{total_sell}股 买卖比{buy_sell_ratio} "
            f"量比{vol_ratio} 来源:{source}{signal_str}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Midday (午盘) Analysis
# ---------------------------------------------------------------------------

def _preselect_midday_candidates(trade_date: str) -> list[dict]:
    """Select ~25 candidate stocks for midday recommendation."""
    candidates: dict[str, dict] = {}

    # Source 1: Morning recommendations that are performing well
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code, name, current_price, buy_low, buy_high FROM stock_recommendation "
            "WHERE trade_date = ? AND phase = 'morning'",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        if not _is_main_board(r["code"]):
            continue
        candidates[r["code"]] = {
            "code": r["code"],
            "name": r["name"],
            "source": "早盘推荐",
        }

    # Source 2: Yesterday's limit-up stocks (continuation plays)
    conn = get_connection()
    try:
        prev_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM limit_up_snapshot WHERE trade_date < ?",
            (trade_date,),
        ).fetchone()
        lu_date = prev_row["d"] if prev_row and prev_row["d"] else trade_date
        rows = conn.execute(
            "SELECT code, name, limit_up_times, sector, amount "
            "FROM limit_up_snapshot WHERE trade_date = ? ORDER BY amount DESC LIMIT 10",
            (lu_date,),
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        if r["code"] not in candidates and _is_main_board(r["code"]):
            candidates[r["code"]] = {
                "code": r["code"],
                "name": r["name"],
                "source": f"昨日涨停(连板{r['limit_up_times'] or 1})",
            }

    # Source 3: Hot sector leading stocks
    conn = get_connection()
    try:
        sec_row = conn.execute(
            "SELECT MAX(trade_date) as d FROM sector_snapshot_item WHERE trade_date <= ?",
            (trade_date,),
        ).fetchone()
        sec_date = sec_row["d"] if sec_row and sec_row["d"] else trade_date
        rows = conn.execute(
            "SELECT leading_stock, leading_stock_code, name "
            "FROM sector_snapshot_item "
            "WHERE trade_date = ? AND sector_type = 'industry' "
            "AND leading_stock_code IS NOT NULL "
            "ORDER BY change_pct DESC LIMIT 8",
            (sec_date,),
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        code = r["leading_stock_code"]
        if code and code not in candidates and _is_main_board(code):
            candidates[code] = {
                "code": code,
                "name": r["leading_stock"],
                "source": f"行业领涨({r['name']})",
            }

    return list(candidates.values())[:25]


def _fetch_morning_session_data(candidates: list[dict]) -> list[dict]:
    """Fetch morning session real-time data for candidates via Sina HQ API."""
    if not candidates:
        return []
    results: list[dict] = []
    code_to_cand = {c["code"]: c for c in candidates}
    codes = ",".join(_code_to_sina(c["code"]) for c in candidates)

    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={codes}",
            headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        logger.warning("午盘候选股行情获取失败", exc_info=True)
        return []

    for line in r.text.strip().split("\n"):
        m = _SINA_HQ_PATTERN.match(line.strip())
        if not m:
            continue
        parts = m.group(2).split(",")
        if len(parts) < 32:
            continue
        code = m.group(1)[2:]
        cand = code_to_cand.get(code)
        if not cand:
            continue

        open_price = _parse_float(parts[1])
        prev_close = _parse_float(parts[2])
        current = _parse_float(parts[3])
        high = _parse_float(parts[4])
        low = _parse_float(parts[5])
        volume = _parse_float(parts[8])
        amount = _parse_float(parts[9])

        change_pct = _round2(((current or 0) - (prev_close or 0)) / prev_close * 100) if prev_close else None
        amplitude = _round2(((high or 0) - (low or 0)) / prev_close * 100) if prev_close else None

        # Signal tags
        signals: list[str] = []
        if change_pct is not None:
            if change_pct > 5:
                signals.append("上午强势")
            elif change_pct > 2:
                signals.append("上午偏强")
            elif change_pct < -3:
                signals.append("上午回调")
        if amplitude is not None and amplitude > 8:
            signals.append("振幅较大")
        if open_price and current and prev_close:
            if current > open_price and current > prev_close:
                signals.append("阳线")
            elif current < open_price:
                signals.append("阴线")

        results.append({
            "code": code,
            "name": cand["name"],
            "source": cand["source"],
            "current": current,
            "open": open_price,
            "prev_close": prev_close,
            "high": high,
            "low": low,
            "change_pct": change_pct,
            "amplitude": amplitude,
            "volume": volume,
            "amount": amount,
            "signals": signals,
        })

    return results


def _format_midday_context(midday_data: list[dict]) -> str:
    """Format morning session data as context text for AI midday recommendation."""
    if not midday_data:
        return ""

    sorted_data = sorted(midday_data, key=lambda x: x.get("change_pct") or 0, reverse=True)

    lines = [f"=== 上午盘面分析 ({len(sorted_data)}只候选) ==="]
    lines.append("说明: 基于11:25左右上午盘面数据，分析午后延续性")

    for d in sorted_data:
        pct_str = f"{d['change_pct']:+.2f}" if d["change_pct"] is not None else "N/A"
        amt = (d["amount"] or 0) / 1e8
        signal_str = f" 信号:[{','.join(d['signals'])}]" if d["signals"] else ""

        lines.append(
            f"  {d['name']}({d['code']}) 涨幅{pct_str}% 现价{d['current']} "
            f"开{d['open']} 高{d['high']} 低{d['low']} "
            f"成交额{amt:.2f}亿 振幅{d['amplitude']}% "
            f"来源:{d['source']}{signal_str}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI Recommendations
# ---------------------------------------------------------------------------

_REC_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责对当日早盘和午盘推荐的个股进行收盘复盘分析。

以下是当日早盘(9:26)和午盘(11:25)推荐的个股列表及其收盘行情数据。请对每只推荐股票进行复盘评估。

要求每只股票输出以下字段，以 JSON 数组格式：
   - code: 股票代码
   - name: 股票名称
   - reason: 复盘评语（80-150字，分析推荐后实际走势，是否符合预期，给出后续操作建议）
   - strategy: 后续策略（如 "继续持有"、"获利了结"、"止损离场"、"观望等待"）
   - current_price: 收盘价
   - buy_low: 原建议买入下限（照搬原文）
   - buy_high: 原建议买入上限（照搬原文）
   - target_price: 原目标价（照搬原文）
   - stop_loss_price: 原止损价（照搬原文）
   - take_profit_price: 原止盈价（照搬原文）
   - risk_level: 风险等级 "low"/"medium"/"high"（根据实际表现重新评估）
   - confidence: 信心度 0-1 之间（对后续走势的信心）
   - sector: 所属行业/板块
   - score: 综合评分 1-10（根据推荐后的实际表现打分，达标则高分，未达预期则低分）

复盘原则：
   - 收盘价在买入区间内：说明买入机会出现，评估后续空间
   - 收盘价高于买入区间且接近目标价：推荐成功，评估是否继续持有
   - 收盘价低于止损价：推荐失败，分析原因
   - 收盘价高于目标价或达到止盈价：超预期表现
   - 结合当日板块整体表现评估个股相对强弱
   - reason 中要具体说明盘中走势特征（是否触达买入区间、最高/最低价表现等）

输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""

_REC_MORNING_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责根据集合竞价数据和市场信息为用户挑选具有投资价值的个股。

请根据以下市场数据和竞价分析，推荐 5-10 只有潜力的个股。要求：

1. 每只股票必须包含以下字段，以 JSON 数组格式输出：
   - code: 股票代码（如 "600519"）
   - name: 股票名称
   - reason: 推荐理由（50-100字，重点结合竞价表现和市场热点分析）
   - strategy: 操作策略（如 "竞价追涨"、"开盘低吸"、"竞价打板"）
   - current_price: 当前价格（根据竞价数据填写）
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
   - 重点参考集合竞价数据，竞价涨幅高且买盘强势的股票优先考虑
   - 买卖比 > 3 说明买盘远强于卖盘，开盘大概率继续走强
   - 量比异常(>5)说明市场关注度高，可能有大资金介入
   - 竞价涨停的股票封板概率高但风险也大，需谨慎评估
   - 昨日涨停今日继续高开的股票具有强延续性，值得重点关注
   - 结合热门板块和隔夜新闻利好，寻找竞价强势+消息面共振的品种
   - 不推荐ST、*ST股票
   - 只推荐沪深主板股票（代码以60或00开头），禁止推荐科创板(688)、创业板(30)、北交所(8/4开头）
   - 买入区间应基于竞价价格合理设定，buy_low 不高于竞价价，buy_high 可略高于竞价价
   - 止损价一般设在买入区间下限下方 2-5%
   - 止盈价和目标价应体现合理盈利预期

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


_REC_MIDDAY_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责根据上午盘面数据为用户挑选午后有潜力的个股。

请根据以下上午盘面数据和市场信息，推荐 5-10 只有潜力的个股。要求：

1. 每只股票必须包含以下字段，以 JSON 数组格式输出：
   - code: 股票代码（如 "600519"）
   - name: 股票名称
   - reason: 推荐理由（50-100字，重点结合上午盘面表现和午后预期分析）
   - strategy: 操作策略（如 "午盘追涨"、"午后低吸"、"半日强势延续"、"午后反弹"）
   - current_price: 当前价格（根据上午行情数据填写）
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
   - 重点参考上午盘面数据，上午涨幅较大且成交量放大的股票午后有延续动力
   - 早盘推荐的股票中上午表现强势的值得继续关注
   - 上午缩量回调到支撑位的强势股可能是午后低吸机会
   - 关注上午板块轮动方向，午后可能继续发酵的热点板块龙头
   - 结合上午新闻和市场情绪，寻找午后可能启动的品种
   - 不推荐ST、*ST股票
   - 只推荐沪深主板股票（代码以60或00开头），禁止推荐科创板(688)、创业板(30)、北交所(8/4开头）
   - 买入区间应基于上午收盘价合理设定，buy_low 不高于当前价，buy_high 可略高于当前价
   - 止损价一般设在买入区间下限下方 2-5%
   - 止盈价和目标价应体现合理盈利预期

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


def _get_rec_context(trade_date: str, phase: str = "afternoon", auction_data: list[dict] | None = None, midday_data: list[dict] | None = None) -> str:
    """Collect context data for recommendation generation."""
    parts = []

    # Review phase: collect morning+midday recommendations with actual performance
    if phase == "review":
        return _get_review_context(trade_date)

    # Auction analysis (morning only)
    if phase == "morning" and auction_data:
        auction_text = _format_auction_context(auction_data)
        if auction_text:
            parts.append(auction_text)

    # Morning session analysis (midday only)
    if phase == "midday" and midday_data:
        midday_text = _format_midday_context(midday_data)
        if midday_text:
            parts.append(midday_text)

    # Limit-up data
    conn = get_connection()
    try:
        if phase == "morning":
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
        if phase == "morning":
            label = "昨日涨停股"
        elif phase == "midday":
            label = "今日上午涨停股"
        else:
            label = "今日涨停股"
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
        if not rows and phase == "midday":
            prev_row = conn.execute(
                "SELECT MAX(trade_date) as d FROM sector_snapshot_item WHERE trade_date < ?",
                (trade_date,),
            ).fetchone()
            if prev_row and prev_row["d"]:
                sec_date = prev_row["d"]
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

    # Recent news
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


def _get_review_context(trade_date: str) -> str:
    """Collect morning+midday recommendations with actual closing data for review."""
    parts = []

    # Fetch morning and midday recommendations
    conn = get_connection()
    try:
        recs = conn.execute(
            "SELECT code, name, phase, reason, strategy, current_price, buy_low, buy_high, "
            "target_price, stop_loss_price, take_profit_price, risk_level, confidence, sector, score "
            "FROM stock_recommendation WHERE trade_date = ? AND phase IN ('morning', 'midday') "
            "ORDER BY phase, score DESC",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if not recs:
        return f"=== 交易日期: {trade_date} ===\n\n当日无早盘/午盘推荐数据，无法进行复盘。"

    # Batch fetch closing prices from Sina
    codes = list({r["code"] for r in recs})
    price_map: dict[str, dict] = {}
    sina_codes = ",".join(_code_to_sina(c) for c in codes)
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={sina_codes}",
            headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
        for line in r.text.strip().split("\n"):
            m = _SINA_HQ_PATTERN.match(line.strip())
            if m:
                p = m.group(2).split(",")
                if len(p) >= 32:
                    code = m.group(1)[2:]
                    prev_close = _parse_float(p[2])
                    price_map[code] = {
                        "open": _parse_float(p[1]),
                        "prev_close": prev_close,
                        "close": _parse_float(p[3]),
                        "high": _parse_float(p[4]),
                        "low": _parse_float(p[5]),
                        "volume": _parse_float(p[8]),
                        "amount": _parse_float(p[9]),
                        "change_pct": _round2((_parse_float(p[3]) - prev_close) / prev_close * 100) if prev_close and _parse_float(p[3]) else None,
                    }
    except Exception:
        logger.warning("复盘行情数据获取失败", exc_info=True)

    # Format by phase
    for phase_label, phase_key in [("早盘推荐", "morning"), ("午盘推荐", "midday")]:
        phase_recs = [r for r in recs if r["phase"] == phase_key]
        if not phase_recs:
            continue
        lines = [f"=== {phase_label} ({len(phase_recs)}只) ==="]
        for rec in phase_recs:
            market = price_map.get(rec["code"], {})
            close = market.get("close")
            high = market.get("high")
            low = market.get("low")
            open_price = market.get("open")
            change_pct = market.get("change_pct")
            amount = (market.get("amount") or 0) / 1e8

            lines.append(
                f"  {rec['name']}({rec['code']}) [{rec['strategy']}] "
                f"推荐价:{rec['current_price']} 买入区间:{rec['buy_low']}~{rec['buy_high']} "
                f"目标:{rec['target_price']} 止损:{rec['stop_loss_price']} 止盈:{rec['take_profit_price']} "
                f"风险:{rec['risk_level']} 行业:{rec['sector']}"
            )
            lines.append(
                f"    收盘:{close} 涨跌:{change_pct}% 开:{open_price} 高:{high} 低:{low} "
                f"成交额:{amount:.2f}亿"
            )
        parts.append("\n".join(lines))

    # Hot sectors for context
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, change_pct, main_net_inflow, leading_stock FROM sector_snapshot_item "
            "WHERE trade_date = ? AND sector_type = 'industry' ORDER BY change_pct DESC LIMIT 10",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()
    if rows:
        lines = ["=== 今日热门行业 TOP10 ==="]
        for r in rows:
            inflow = (r["main_net_inflow"] or 0) / 1e8
            lines.append(f"  {r['name']}: 涨幅{r['change_pct']}% 主力净流入{inflow:.2f}亿 领涨:{r['leading_stock']}")
        parts.append("\n".join(lines))

    return f"=== 交易日期: {trade_date} 收盘复盘 ===\n\n" + "\n\n".join(parts)


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

    # Morning phase: preselect candidates and fetch auction data
    auction_data: list[dict] | None = None
    midday_data: list[dict] | None = None

    if phase == "morning":
        candidates = _preselect_morning_candidates(trade_date)
        if candidates:
            logger.info("早盘候选股: %d 只，开始获取竞价数据", len(candidates))
            auction_data = _fetch_auction_data(candidates)
            logger.info("竞价数据获取完成: %d 只成功", len(auction_data or []))

    elif phase == "midday":
        candidates = _preselect_midday_candidates(trade_date)
        if candidates:
            logger.info("午盘候选股: %d 只，开始获取上午行情数据", len(candidates))
            midday_data = _fetch_morning_session_data(candidates)
            logger.info("上午行情数据获取完成: %d 只成功", len(midday_data or []))

    elif phase == "review":
        # Update actual returns for morning and midday before generating review
        try:
            update_morning_performance(trade_date)
        except Exception:
            logger.warning("早盘收益更新失败", exc_info=True)
        try:
            update_recommendation_performance(trade_date, phase="midday")
        except Exception:
            logger.warning("午盘收益更新失败", exc_info=True)

    context = _get_rec_context(trade_date, phase, auction_data=auction_data, midday_data=midday_data)

    if phase == "morning":
        system_prompt = _REC_MORNING_SYSTEM_PROMPT
    elif phase == "midday":
        system_prompt = _REC_MIDDAY_SYSTEM_PROMPT
    else:
        system_prompt = _REC_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]
    response = llm.analysis_chat(messages)
    recs = _parse_recommendation_json(response)

    if not recs:
        logger.warning("No recommendations parsed from LLM response")
        return {"items": [], "total": 0}

    # Filter out non-main-board stocks (safety net in case LLM ignores the rule)
    before = len(recs)
    recs = [r for r in recs if _is_main_board(r.get("code", ""))]
    if len(recs) < before:
        logger.info("过滤掉 %d 只非沪深主板推荐", before - len(recs))

    # Deduplicate by code for review phase (AI may return same stock from morning+midday)
    if phase == "review":
        seen: set[str] = set()
        unique_recs: list[dict] = []
        for rec in recs:
            code = rec.get("code", "")
            if code not in seen:
                seen.add(code)
                unique_recs.append(rec)
        recs = unique_recs

    # Override LLM-generated current_price with real-time prices
    if phase in ("morning", "midday", "review") and recs:
        codes = [r.get("code", "") for r in recs if r.get("code")]
        if codes:
            sina_codes = ",".join(_code_to_sina(c) for c in codes)
            try:
                r = requests.get(
                    f"https://hq.sinajs.cn/list={sina_codes}",
                    headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                r.raise_for_status()
                real_price: dict[str, float | None] = {}
                for line in r.text.strip().split("\n"):
                    m = _SINA_HQ_PATTERN.match(line.strip())
                    if m:
                        parts = m.group(2).split(",")
                        if len(parts) >= 4:
                            code = m.group(1)[2:]
                            real_price[code] = _parse_float(parts[3])
                for rec in recs:
                    code = rec.get("code", "")
                    rp = real_price.get(code)
                    if rp is None:
                        continue
                    llm_price = _parse_float(rec.get("current_price"))
                    rec["current_price"] = rp
                    # Adjust buy_low/buy_high proportionally when LLM price deviates
                    if llm_price and llm_price > 0:
                        ratio = rp / llm_price
                        bl = _parse_float(rec.get("buy_low"))
                        bh = _parse_float(rec.get("buy_high"))
                        tp = _parse_float(rec.get("target_price"))
                        sl = _parse_float(rec.get("stop_loss_price"))
                        tk = _parse_float(rec.get("take_profit_price"))
                        if bl: rec["buy_low"] = _round2(bl * ratio)
                        if bh: rec["buy_high"] = _round2(bh * ratio)
                        if tp: rec["target_price"] = _round2(tp * ratio)
                        if sl: rec["stop_loss_price"] = _round2(sl * ratio)
                        if tk: rec["take_profit_price"] = _round2(tk * ratio)
                logger.info("覆盖 %d 只推荐股的 current_price 及买入区间为实时价格", sum(1 for c in codes if c in real_price))
            except Exception:
                logger.warning("实时价格覆盖失败，使用 LLM 生成价格", exc_info=True)

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
    return update_recommendation_performance(trade_date, phase="morning")


def update_recommendation_performance(trade_date: str | None = None, phase: str = "morning") -> dict:
    """Update actual_return_pct for recommendations of a given phase using live prices."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, code FROM stock_recommendation WHERE trade_date = ? AND phase = ? AND status = 'pending'",
            (trade_date, phase),
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
            m = _SINA_HQ_PATTERN.match(line.strip())
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

    logger.info("Updated %s performance for %d / %d stocks on %s", phase, updated, len(rows), trade_date)
    return {"updated": updated, "total": len(rows), "trade_date": trade_date}
