import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import akshare as ak
import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

def _parse_zt_df(df) -> list[dict]:
    """Parse akshare zt-pool DataFrame into standard item list."""
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


def _fetch_zt_pool_from_em(date: str) -> list[dict]:
    """Fallback: fetch limit-up stocks via East Money clist API."""
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    try:
        r = session.get(
            "http://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 500, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f62,f115,f184,f66,f72,f78,f84",
            },
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
        )
        r.raise_for_status()
        data = r.json()
        diff = (data.get("data") or {}).get("diff") or []
        items = []
        for item in diff:
            change_pct = _round2(_parse_float(item.get("f3")))
            if change_pct is not None and change_pct >= 9.9:
                code = str(item.get("f12", ""))
                items.append({
                    "code": code,
                    "name": str(item.get("f14", "")),
                    "price": _parse_float(item.get("f2")),
                    "change_pct": change_pct,
                    "limit_up_amount": None,
                    "turnover_rate": _round2(_parse_float(item.get("f8"))),
                    "volume": _parse_float(item.get("f5")),
                    "amount": _parse_float(item.get("f6")),
                    "amplitude": _round2(_parse_float(item.get("f7"))),
                    "first_limit_up_time": None,
                    "last_limit_up_time": None,
                    "limit_up_times": 1,
                    "reason": "",
                    "sector": "",
                    "board": _classify_board(code),
                })
        logger.info("East Money fallback fetched %d limit-up stocks", len(items))
        return items
    except Exception:
        logger.warning("East Money fallback fetch limit-up failed", exc_info=True)
        return []


def _fetch_main_fund_flow_rank(top_n: int = 30) -> list[dict]:
    """东方财富 clist API 按主力净流入(f62)降序取 top_n 只个股。

    返回字段：code/name/current/change_pct/amount/main_net_inflow/
              main_inflow_pct/large_net_inflow/turnover_rate。
    """
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    try:
        r = session.get(
            "http://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": top_n, "po": 1, "np": 1,
                "fltt": 2, "invt": 2,
                "fid": "f62",  # 主力净流入降序
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",  # 沪深京 A 股
                "fields": "f12,f14,f2,f3,f6,f62,f184,f66,f72,f8",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
        )
        r.raise_for_status()
        diff = (r.json().get("data") or {}).get("diff") or []
        items = []
        for it in diff:
            code = str(it.get("f12", ""))
            if not code:
                continue
            items.append({
                "code": code,
                "name": str(it.get("f14", "")),
                "current": _parse_float(it.get("f2")),
                "change_pct": _round2(_parse_float(it.get("f3"))),
                "amount": _parse_float(it.get("f6")),
                "main_net_inflow": _parse_float(it.get("f62")),
                "main_inflow_pct": _round2(_parse_float(it.get("f184"))),
                "large_net_inflow": _parse_float(it.get("f72")),
                "turnover_rate": _round2(_parse_float(it.get("f8"))),
            })
        logger.info("主力净流入排行抓取 %d 只", len(items))
        return items
    except Exception:
        logger.warning("主力净流入排行抓取失败", exc_info=True)
        return []


def fetch_limit_up_stocks(date: str) -> list[dict]:
    """Fetch limit-up stock pool from akshare with fallback. date format: YYYY-MM-DD."""
    ak_date = date.replace("-", "")
    try:
        df = ak.stock_zt_pool_em(date=ak_date)
        if df is not None and not df.empty:
            return _parse_zt_df(df)
    except Exception:
        logger.warning("akshare stock_zt_pool_em failed for %s, trying fallback", date, exc_info=True)

    # Fallback 1: akshare sub-new pool (also contains limit-up stocks)
    try:
        df = ak.stock_zt_pool_sub_new_em(date=ak_date)
        if df is not None and not df.empty:
            return _parse_zt_df(df)
    except Exception:
        logger.warning("akshare stock_zt_pool_sub_new_em failed for %s", date, exc_info=True)

    # Fallback 2: East Money clist API
    return _fetch_zt_pool_from_em(date)


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


def _compute_cum_gain(conn, code: str, trade_date: str, days: int) -> float | None:
    """复利累计涨幅 (%)。

    从 stock_daily 取 trade_date < ? 的最近 N 个交易日 close，
    cum_gain = (last_close / first_close - 1) * 100。
    数据不足 days//2 个交易日时返回 None（不强制过滤）。
    口径与"4月以来涨 264%"一致：复利累计，不简单累加日涨幅。
    """
    rows = conn.execute(
        "SELECT close FROM stock_daily "
        "WHERE code = ? AND trade_date < ? AND close IS NOT NULL AND close > 0 "
        "ORDER BY trade_date DESC LIMIT ?",
        (code, trade_date, days),
    ).fetchall()
    if len(rows) < max(2, days // 2):
        return None
    first_close = rows[-1]["close"]
    last_close = rows[0]["close"]
    if not first_close or first_close <= 0:
        return None
    return round((last_close / first_close - 1) * 100, 2)


def _load_latest_daily_metrics(conn, code: str, trade_date: str) -> dict | None:
    """取 stock_daily 中 trade_date <= ? 的最近一行。"""
    row = conn.execute(
        "SELECT trade_date, close, prev_close, change_pct, high, low, amount, "
        "turnover_rate, amplitude, pe_ttm, pe_static, pb, "
        "total_market_cap, circulating_market_cap, main_net_inflow, main_net_inflow_pct "
        "FROM stock_daily "
        "WHERE code = ? AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (code, trade_date),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def _load_fundamental_brief(conn, code: str) -> dict | None:
    """取 stock_fundamental 最新一行（基本面速览）。"""
    row = conn.execute(
        "SELECT roe, eps, revenue_growth, profit_growth, gross_margin, net_margin, report_date "
        "FROM stock_fundamental WHERE code = ? ORDER BY report_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def _load_latest_limit_up_times(conn, code: str, trade_date: str) -> int:
    """取 trade_date <= ? 的最近一日 limit_up_snapshot 中的连板数；无记录返回 0。"""
    row = conn.execute(
        "SELECT limit_up_times FROM limit_up_snapshot "
        "WHERE code = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 1",
        (code, trade_date),
    ).fetchone()
    if not row:
        return 0
    return int(row["limit_up_times"] or 0)


def _classify_risk_proximity(
    pe_ttm: float | None,
    cum_gain_5d: float | None,
    cum_gain_20d: float | None,
    limit_up_times: int,
) -> list[str]:
    """接近但未触发 reject 的边缘标签（透明展示给前端 + LLM）。"""
    from app.services.constants import (
        RECOMMENDATION_CUM_GAIN_5D_WARN,
        RECOMMENDATION_CUM_GAIN_20D_WARN,
        RECOMMENDATION_LIMIT_UP_TIMES_WARN,
        RECOMMENDATION_PE_TTM_WARN,
    )

    tags: list[str] = []
    if pe_ttm is not None and pe_ttm > 0 and pe_ttm >= RECOMMENDATION_PE_TTM_WARN:
        tags.append(f"PE偏高({pe_ttm:.0f})")
    if cum_gain_5d is not None and cum_gain_5d >= RECOMMENDATION_CUM_GAIN_5D_WARN:
        tags.append(f"近5日涨幅偏大(+{cum_gain_5d:.1f}%)")
    if cum_gain_20d is not None and cum_gain_20d >= RECOMMENDATION_CUM_GAIN_20D_WARN:
        tags.append(f"近20日涨幅偏大(+{cum_gain_20d:.1f}%)")
    if limit_up_times >= RECOMMENDATION_LIMIT_UP_TIMES_WARN:
        tags.append(f"连板情绪({limit_up_times}板)")
    return tags


def _apply_hard_filters(
    candidates: list[dict],
    *,
    trade_date: str,
    phase: str,
    zt_codes: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """统一硬过滤。返回 (passed, rejected)。

    rejected: [{'code','name','reason'}]
    passed 中每个候选股追加字段（供后续 payload 与持久化复用）：
      pe_ttm, pe_static, pb, total_market_cap, close, prev_close, change_pct,
      main_net_inflow, turnover_rate, amount,
      cum_gain_5d, cum_gain_20d, cum_gain_60d,
      roe, revenue_growth, profit_growth, gross_margin, net_margin,
      limit_up_times, risk_proximity_tags

    规则（phase 无关，全部对齐到尾盘标准）：
      1. ST/*ST：name 含 'ST'（大小写不敏感）→ reject
      2. 当日涨停：code ∈ zt_codes → reject（早盘 zt_codes=None 时跳过）
      3. limit_up_times >= RECOMMENDATION_LIMIT_UP_TIMES_MAX → reject
      4. pe_ttm > RECOMMENDATION_PE_TTM_MAX → reject（亏损/None 放行）
      5. cum_gain_5d/20d/60d 任一超限 → reject
    """
    from app.services.constants import (
        RECOMMENDATION_CUM_GAIN_5D_MAX,
        RECOMMENDATION_CUM_GAIN_20D_MAX,
        RECOMMENDATION_CUM_GAIN_60D_MAX,
        RECOMMENDATION_LIMIT_UP_TIMES_MAX,
        RECOMMENDATION_PE_TTM_MAX,
    )

    passed: list[dict] = []
    rejected: list[dict] = []

    conn = get_connection()
    try:
        for cand in candidates:
            code = cand.get("code", "")
            name = cand.get("name", "") or ""

            # Rule 1: ST
            if "ST" in name.upper():
                rejected.append({"code": code, "name": name, "reason": "ST股"})
                continue

            # Rule 2: 当日涨停
            if zt_codes and code in zt_codes:
                rejected.append({"code": code, "name": name, "reason": "当日涨停"})
                continue

            # 加载估值/累计涨幅/基本面/连板
            metrics = _load_latest_daily_metrics(conn, code, trade_date) or {}
            cum_5d = _compute_cum_gain(conn, code, trade_date, 5)
            cum_20d = _compute_cum_gain(conn, code, trade_date, 20)
            cum_60d = _compute_cum_gain(conn, code, trade_date, 60)
            fund = _load_fundamental_brief(conn, code) or {}
            lu_times = _load_latest_limit_up_times(conn, code, trade_date)

            pe_ttm = metrics.get("pe_ttm")
            pe_ttm_val = _parse_float(pe_ttm)

            # Rule 3: 连板 >= MAX
            if lu_times >= RECOMMENDATION_LIMIT_UP_TIMES_MAX:
                rejected.append({"code": code, "name": name, "reason": f"连板≥{RECOMMENDATION_LIMIT_UP_TIMES_MAX}({lu_times})"})
                continue

            # Rule 4: PE > MAX（亏损/None 放行）
            if pe_ttm_val is not None and pe_ttm_val > 0 and pe_ttm_val > RECOMMENDATION_PE_TTM_MAX:
                rejected.append({"code": code, "name": name, "reason": f"PE过高({pe_ttm_val:.0f})"})
                continue

            # Rule 5: 累计涨幅任一超限
            over_limits: list[str] = []
            if cum_5d is not None and cum_5d > RECOMMENDATION_CUM_GAIN_5D_MAX:
                over_limits.append(f"近5日+{cum_5d:.1f}%")
            if cum_20d is not None and cum_20d > RECOMMENDATION_CUM_GAIN_20D_MAX:
                over_limits.append(f"近20日+{cum_20d:.1f}%")
            if cum_60d is not None and cum_60d > RECOMMENDATION_CUM_GAIN_60D_MAX:
                over_limits.append(f"近60日+{cum_60d:.1f}%")
            if over_limits:
                rejected.append({"code": code, "name": name, "reason": f"累计涨幅过大({','.join(over_limits)})"})
                continue

            # 通过：追加 enrichment 字段
            enriched = dict(cand)
            enriched.update({
                "pe_ttm": pe_ttm_val,
                "pe_static": _parse_float(metrics.get("pe_static")),
                "pb": _parse_float(metrics.get("pb")),
                "total_market_cap": _parse_float(metrics.get("total_market_cap")),
                "close": _parse_float(metrics.get("close")),
                "prev_close": _parse_float(metrics.get("prev_close")),
                "change_pct": _parse_float(metrics.get("change_pct")),
                "main_net_inflow": _parse_float(metrics.get("main_net_inflow")),
                "turnover_rate": _parse_float(metrics.get("turnover_rate")),
                "amount": _parse_float(metrics.get("amount")),
                "cum_gain_5d": cum_5d,
                "cum_gain_20d": cum_20d,
                "cum_gain_60d": cum_60d,
                "roe": _parse_float(fund.get("roe")),
                "revenue_growth": _parse_float(fund.get("revenue_growth")),
                "profit_growth": _parse_float(fund.get("profit_growth")),
                "gross_margin": _parse_float(fund.get("gross_margin")),
                "net_margin": _parse_float(fund.get("net_margin")),
                "limit_up_times": lu_times,
                "risk_proximity_tags": _classify_risk_proximity(
                    pe_ttm_val, cum_5d, cum_20d, lu_times,
                ),
            })
            passed.append(enriched)
    finally:
        conn.close()

    logger.info(
        "[%s] 候选股硬过滤：%d 通过，%d 被拒 rejected=%s",
        phase, len(passed), len(rejected),
        [{"code": r["code"], "name": r["name"], "reason": r["reason"]} for r in rejected],
    )
    return passed, rejected


def _is_price_stale(
    real_price: float,
    prev_close: float,
    trade_date: str,
    now: datetime,
    tolerance_pct: float | None = None,
) -> bool:
    """判断实时价是否疑似"未刷新/停牌"。

    全部满足才算 stale：
      1. abs(real_price - prev_close) / prev_close < tolerance_pct（默认 0.05%）
      2. 当前时间在 A 股交易时段内（9:30~11:30 或 13:00~15:00）
      3. trade_date 是工作日

    说明：盘前 (9:15~9:30) 竞价阶段 real_price 等于昨收是正常的，不应触发 stale。
    """
    if tolerance_pct is None:
        from app.services.constants import RECOMMENDATION_STALE_PRICE_TOLERANCE_PCT
        tolerance_pct = RECOMMENDATION_STALE_PRICE_TOLERANCE_PCT

    if not prev_close or prev_close <= 0:
        return False
    deviation = abs(real_price - prev_close) / prev_close
    if deviation >= tolerance_pct:
        return False

    # trade_date 工作日检查（1-5 = 周一~周五）
    try:
        td = datetime.strptime(trade_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    if td.weekday() >= 5:
        return False

    # 当前时间须在 A 股交易时段
    t = now.time()
    in_morning = t >= datetime.strptime("09:30:00", "%H:%M:%S").time() and t <= datetime.strptime("11:30:00", "%H:%M:%S").time()
    in_afternoon = t >= datetime.strptime("13:00:00", "%H:%M:%S").time() and t <= datetime.strptime("15:00:00", "%H:%M:%S").time()
    return in_morning or in_afternoon


def _score_recommendation_candidate(item: dict, phase: str) -> dict:
    from app.services.constants import (
        RECOMMENDATION_AMOUNT_MIN,
        RECOMMENDATION_HIGH_AMPLITUDE,
        RECOMMENDATION_IDEAL_TURNOVER_MAX,
        RECOMMENDATION_IDEAL_TURNOVER_MIN,
    )

    score = 5.0
    signals = list(item.get("signals") or item.get("signal_tags") or [])
    penalties: list[str] = []
    amount = item.get("amount")
    change_pct = item.get("change_pct")
    amplitude = item.get("amplitude")
    turnover = item.get("turnover_rate") or item.get("turnover")
    main_net = item.get("main_net_inflow")
    main_pct = item.get("main_inflow_pct")
    large_net = item.get("large_net_inflow")
    current = item.get("current")
    open_price = item.get("open")
    prev_close = item.get("prev_close")
    high = item.get("high")

    if amount is not None:
        if amount >= RECOMMENDATION_AMOUNT_MIN:
            score += 0.8
            signals.append("流动性达标")
        else:
            score -= 0.8
            penalties.append("成交额偏低")

    if turnover is not None:
        if RECOMMENDATION_IDEAL_TURNOVER_MIN <= turnover <= RECOMMENDATION_IDEAL_TURNOVER_MAX:
            score += 0.6
            signals.append("换手合理")
        elif turnover > RECOMMENDATION_IDEAL_TURNOVER_MAX:
            score -= 0.5
            penalties.append("换手偏高")
        else:
            score -= 0.3
            penalties.append("换手不足")

    if amplitude is not None and amplitude > RECOMMENDATION_HIGH_AMPLITUDE:
        score -= 0.6
        penalties.append("振幅偏大")

    if change_pct is not None:
        if phase == "morning":
            if 0 <= change_pct <= 5:
                score += 0.8
                signals.append("竞价强且未过热")
            elif change_pct > 8:
                score -= 0.5
                penalties.append("竞价过热")
        elif phase == "midday":
            if 1 <= change_pct <= 5:
                score += 0.8
                signals.append("午后延续区间")
            elif -2 <= change_pct < 1:
                score += 0.4
                signals.append("回踩低吸区间")
            elif change_pct > 6:
                score -= 0.4
                penalties.append("上午涨幅偏高")
        elif phase == "afternoon":
            if 0 <= change_pct <= 5:
                score += 0.8
                signals.append("明日延续区间")
            elif -2 <= change_pct < 0:
                score += 0.5
                signals.append("尾盘低吸区间")
            elif change_pct > 6:
                score -= 0.4
                penalties.append("尾盘追高")

    if main_net is not None and main_net > 0:
        score += 0.7
        signals.append("主力净流入为正")
    if main_pct is not None:
        if main_pct >= 5:
            score += 0.8
            signals.append("主力占比强")
        elif main_pct < 3:
            score -= 0.4
            penalties.append("主力占比不足")
    if large_net is not None and large_net > 0:
        score += 0.4
        signals.append("大单净流入")

    if current and open_price and prev_close:
        if current > open_price and current > prev_close:
            score += 0.5
            signals.append("阳线确认")
        elif current < open_price:
            score -= 0.3
            penalties.append("盘中走弱")

    if current and high and high > 0:
        fallback = (high - current) / high * 100
        item["high_pullback_pct"] = round(fallback, 2)
        if fallback > 4:
            score -= 0.5
            penalties.append("高位回落")

    item["quant_score"] = round(max(0, min(10, score)), 1)
    item["signals"] = list(dict.fromkeys(signals))
    item["signal_tags"] = item["signals"]
    item["penalty_tags"] = list(dict.fromkeys(penalties))
    return item


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

    passed, _rejected = _apply_hard_filters(
        list(candidates.values()),
        trade_date=trade_date,
        phase="morning",
        zt_codes=None,
    )
    return passed[:20]


def _fetch_one_stock_auction_sina(code: str) -> dict | None:
    """Fallback: fetch basic auction data from Sina HQ API."""
    sina_code = _code_to_sina(code)
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={sina_code}",
            headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        r.raise_for_status()
        m = _SINA_HQ_PATTERN.match(r.text.strip())
        if not m:
            return None
        parts = m.group(2).split(",")
        if len(parts) < 10:
            return None
        prev_close = _parse_float(parts[2])
        current = _parse_float(parts[3])
        open_price = _parse_float(parts[1])
        volume = _parse_float(parts[8])
        amount = _parse_float(parts[9])
        change_pct = _round2(((current or 0) - (prev_close or 0)) / prev_close * 100) if prev_close else None
        signal_tags: list[str] = []
        if current and prev_close and current >= prev_close * 1.095:
            signal_tags.append("竞价涨停")
        return {
            "code": code,
            "current": current,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "volume": volume,
            "amount": amount,
            "volume_ratio": None,
            "turnover": None,
            "limit_up": None,
            "limit_down": None,
            "total_buy_vol": 0,
            "total_sell_vol": 0,
            "buy_sell_ratio": None,
            "order_ratio": None,
            "is_limit_up": bool(current and prev_close and current >= prev_close * 1.095),
            "signal_tags": signal_tags,
        }
    except Exception:
        logger.debug("Sina fallback auction fetch failed: %s", code, exc_info=True)
        return None


def _fetch_one_stock_auction(code: str) -> dict | None:
    """Fetch auction order book data for a single stock from East Money push2 API, fallback to Sina."""
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
        logger.debug("East Money auction fetch failed, trying Sina fallback: %s", code)
        return _fetch_one_stock_auction_sina(code)

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
                _merge_enrichment(result, cand)
                results.append(_score_recommendation_candidate(result, "morning"))

    return results


def _format_risk_metrics_inline(d: dict) -> str:
    """渲染估值与风险指标 inline 字符串（接在 candidate 行尾，节省 token）。

    输出形如：
      | PE76 PB5 市值850亿 累计5日+18% 累计20日+52% 营收+119% 利润+522% 连板0 风险标签:[PE偏高,近20日涨幅偏大]

    所有缺失值渲染为空（保持紧凑）。LLM 应据此推断 catalyst 与 high_position_risk。
    """
    def _num(val, suffix: str = "", fmt: str = ".0f") -> str:
        if val is None:
            return ""
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""
        if v != v:  # NaN
            return ""
        return f"{v:{fmt}}{suffix}"

    parts: list[str] = []
    pe = d.get("pe_ttm")
    if pe is not None:
        parts.append(f"PE{_num(pe, '', '.0f')}")
    pb = d.get("pb")
    if pb is not None:
        parts.append(f"PB{_num(pb, '', '.1f')}")
    mcap = d.get("total_market_cap")
    if mcap is not None:
        mcap_yi = float(mcap) / 1e8
        parts.append(f"市值{mcap_yi:.0f}亿")
    cg5 = d.get("cum_gain_5d")
    if cg5 is not None:
        parts.append(f"累计5日{cg5:+.1f}%")
    cg20 = d.get("cum_gain_20d")
    if cg20 is not None:
        parts.append(f"累计20日{cg20:+.1f}%")
    cg60 = d.get("cum_gain_60d")
    if cg60 is not None:
        parts.append(f"累计60日{cg60:+.1f}%")
    rg = d.get("revenue_growth")
    if rg is not None:
        parts.append(f"营收{rg:+.0f}%")
    pg = d.get("profit_growth")
    if pg is not None:
        parts.append(f"利润{pg:+.0f}%")
    roe = d.get("roe")
    if roe is not None:
        parts.append(f"ROE{_num(roe, '%', '.1f')}")
    lu = d.get("limit_up_times")
    if lu:
        parts.append(f"连板{lu}")
    tags = d.get("risk_proximity_tags") or []
    if tags:
        parts.append(f"风险标签:[{','.join(tags)}]")

    if not parts:
        return ""
    return " | " + " ".join(parts)


# Enrichment 字段透传白名单：fetch 函数从 input candidate 拷到 output item 时用
_ENRICHMENT_KEYS = (
    "pe_ttm", "pe_static", "pb", "total_market_cap",
    "cum_gain_5d", "cum_gain_20d", "cum_gain_60d",
    "roe", "revenue_growth", "profit_growth", "gross_margin", "net_margin",
    "limit_up_times", "risk_proximity_tags",
)


def _merge_enrichment(target: dict, source: dict) -> dict:
    """把 source 中的 enrichment 字段拷到 target，返回 target。"""
    for k in _ENRICHMENT_KEYS:
        if k in source and target.get(k) is None:
            target[k] = source[k]
    return target


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
        penalty_tags = d.get("penalty_tags") or []
        penalty_str = f" 风险:[{','.join(penalty_tags)}]" if penalty_tags else ""
        quant_score = d.get("quant_score")
        score_str = f" 量化分{quant_score}" if quant_score is not None else ""

        lines.append(
            f"  {name}({code}) 竞价{pct_str}% 竞价价{current} 昨收{prev_close} "
            f"买盘{total_buy}股 卖盘{total_sell}股 买卖比{buy_sell_ratio} "
            f"量比{vol_ratio} 来源:{source}{score_str}{signal_str}{penalty_str}"
            f"{_format_risk_metrics_inline(d)}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Midday (午盘) Analysis
# ---------------------------------------------------------------------------

def _preselect_midday_candidates(trade_date: str) -> list[dict]:
    """午盘候选：上午盘实际强势股（涨幅启动 + 主力净流入为正）。

    与早盘（盘前预期）口径完全错开，避免候选池重合导致重复计票。
    采用两段式过滤：严格档（3–7%）候选不足 10 只时放宽下限到 2%。
    """
    raw = _fetch_main_fund_flow_rank(top_n=80)
    if not raw:
        logger.warning("午盘候选股预筛：主力净流入排行抓取为空")
        return []

    def _qualifying(r: dict, low_pct: float) -> bool:
        chg = r.get("change_pct")
        inflow = r.get("main_net_inflow")
        inflow_pct = r.get("main_inflow_pct")
        turnover = r.get("turnover_rate")
        if chg is None or inflow is None:
            return False
        if not (low_pct <= chg <= 7.0):
            return False
        if inflow <= 0:
            return False
        if low_pct >= 3.0:
            if inflow_pct is None or inflow_pct < 3:
                return False
            if turnover is None or not (2.0 <= turnover <= 18.0):
                return False
        return True

    strict = [r for r in raw if _qualifying(r, 3.0)]
    if len(strict) >= 10:
        chosen = strict
        logger.info("午盘候选严格档：%d 只（涨幅3-7%%）", len(strict))
    else:
        relaxed = [r for r in raw if _qualifying(r, 2.0)]
        chosen = relaxed
        logger.info(
            "午盘候选放宽档：%d 只（严格档仅 %d 只，下限放宽到 2%%）",
            len(relaxed), len(strict),
        )

    candidates: dict[str, dict] = {}
    for r in chosen:
        code = r["code"]
        if not _is_main_board(code):
            continue
        candidates[code] = {
            "code": code,
            "name": r["name"],
            "current": r.get("current"),
            "change_pct": r.get("change_pct"),
            "main_net_inflow": r.get("main_net_inflow"),
            "main_inflow_pct": r.get("main_inflow_pct"),
            "turnover_rate": r.get("turnover_rate"),
            "amount": r.get("amount"),
            "source": (
                f"上午强势(涨{r.get('change_pct') or 0:.1f}%/"
                f"主力流入{(r.get('main_net_inflow') or 0) / 1e8:.2f}亿)"
            ),
        }

    try:
        zt_codes_midday = {it["code"] for it in fetch_limit_up_stocks(trade_date)}
    except Exception:
        logger.warning("午盘候选股预筛：今日涨停池获取失败", exc_info=True)
        zt_codes_midday = set()

    passed, _rejected = _apply_hard_filters(
        list(candidates.values()),
        trade_date=trade_date,
        phase="midday",
        zt_codes=zt_codes_midday or None,
    )
    return passed[:25]


def _preselect_afternoon_candidates(trade_date: str) -> list[dict]:
    """尾盘候选股：主力净流入 TOP30 过滤掉涨停/ST/非主板/负流入，留 ≤20 只。"""
    from app.services.constants import (
        AFTERNOON_AMOUNT_MIN,
        AFTERNOON_RANK_TOP_N,
        AFTERNOON_CANDIDATE_MAX,
        AFTERNOON_CHANGE_PCT_MIN,
        AFTERNOON_CHANGE_PCT_MAX,
        AFTERNOON_MAIN_INFLOW_PCT_MIN,
        AFTERNOON_TURNOVER_MAX,
        AFTERNOON_TURNOVER_MIN,
    )
    rank = _fetch_main_fund_flow_rank(top_n=AFTERNOON_RANK_TOP_N)
    if not rank:
        logger.warning("尾盘候选股预筛：主力净流入排行抓取失败，无候选")
        return []

    try:
        zt_codes = {it["code"] for it in fetch_limit_up_stocks(trade_date)}
    except Exception:
        logger.warning("尾盘候选股预筛：今日涨停池获取失败，仅按涨幅过滤", exc_info=True)
        zt_codes = set()

    candidates: list[dict] = []
    for it in rank:
        code = it["code"]
        name = it.get("name", "")
        if not _is_main_board(code):
            continue
        if "ST" in name.upper():
            continue
        pct = it.get("change_pct")
        if pct is not None and (pct < AFTERNOON_CHANGE_PCT_MIN or pct > AFTERNOON_CHANGE_PCT_MAX):
            continue
        if code in zt_codes:
            continue
        if (it.get("main_net_inflow") or 0) <= 0:
            continue
        amount = it.get("amount")
        if amount is not None and amount < AFTERNOON_AMOUNT_MIN:
            continue
        main_pct = it.get("main_inflow_pct")
        if main_pct is not None and main_pct < AFTERNOON_MAIN_INFLOW_PCT_MIN:
            continue
        turnover = it.get("turnover_rate")
        if turnover is not None and (turnover < AFTERNOON_TURNOVER_MIN or turnover > AFTERNOON_TURNOVER_MAX):
            continue
        candidates.append({
            "code": code,
            "name": name,
            "source": "主力净流入TOP",
            "current": it.get("current"),
            "change_pct": pct,
            "amount": it.get("amount"),
            "main_net_inflow": it.get("main_net_inflow"),
            "main_inflow_pct": it.get("main_inflow_pct"),
            "large_net_inflow": it.get("large_net_inflow"),
            "turnover_rate": it.get("turnover_rate"),
        })
        if len(candidates) >= AFTERNOON_CANDIDATE_MAX:
            break

    logger.info("尾盘候选股预筛：%d 只（主力净流入 TOP%d 过滤后）", len(candidates), AFTERNOON_RANK_TOP_N)

    passed, _rejected = _apply_hard_filters(
        candidates,
        trade_date=trade_date,
        phase="afternoon",
        zt_codes=zt_codes or None,
    )
    return passed


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

        item = {
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
        }
        _merge_enrichment(item, cand)
        results.append(_score_recommendation_candidate(item, "midday"))

    return results


def _fetch_afternoon_session_data(candidates: list[dict]) -> list[dict]:
    """Sina HQ 补全 open/high/low/振幅/量，资金流字段从候选股预筛结果带过来。"""
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
        logger.warning("尾盘候选股行情获取失败", exc_info=True)
        return []

    sina_map: dict[str, dict] = {}
    for line in r.text.strip().split("\n"):
        m = _SINA_HQ_PATTERN.match(line.strip())
        if not m:
            continue
        parts = m.group(2).split(",")
        if len(parts) < 10:
            continue
        code = m.group(1)[2:]
        sina_map[code] = {
            "open": _parse_float(parts[1]),
            "prev_close": _parse_float(parts[2]),
            "current": _parse_float(parts[3]),
            "high": _parse_float(parts[4]),
            "low": _parse_float(parts[5]),
            "volume": _parse_float(parts[8]),
            "amount": _parse_float(parts[9]),
        }

    for cand in candidates:
        code = cand["code"]
        sd = sina_map.get(code)
        if not sd:
            continue
        current = sd["current"]
        prev_close = sd["prev_close"]
        open_price = sd["open"]
        high = sd["high"]
        low = sd["low"]
        change_pct = _round2(((current or 0) - (prev_close or 0)) / prev_close * 100) if prev_close else cand.get("change_pct")
        amplitude = _round2(((high or 0) - (low or 0)) / prev_close * 100) if prev_close else None
        main_net = cand.get("main_net_inflow") or 0
        main_pct = cand.get("main_inflow_pct")
        large_net = cand.get("large_net_inflow") or 0
        from app.services.constants import AFTERNOON_AMPLITUDE_MAX
        if amplitude is not None and amplitude > AFTERNOON_AMPLITUDE_MAX:
            continue

        signals: list[str] = []
        if main_pct is not None:
            signals.append(f"主力净流入{main_pct}%")
        if change_pct is not None:
            if 0 <= change_pct <= 7:
                signals.append("尾盘强势")
            elif -2 <= change_pct < 0:
                signals.append("回调低吸")
        if amplitude is not None and amplitude > 8:
            signals.append("振幅较大")
        if open_price and current and prev_close:
            if current > open_price and current > prev_close:
                signals.append("阳线")
            elif current < open_price:
                signals.append("阴线")

        item = {
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
            "volume": sd["volume"],
            "amount": sd["amount"] or cand.get("amount"),
            "main_net_inflow": main_net,
            "main_inflow_pct": main_pct,
            "large_net_inflow": large_net,
            "turnover_rate": cand.get("turnover_rate"),
            "signals": signals,
        }
        _merge_enrichment(item, cand)
        results.append(_score_recommendation_candidate(item, "afternoon"))

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
        penalty_tags = d.get("penalty_tags") or []
        penalty_str = f" 风险:[{','.join(penalty_tags)}]" if penalty_tags else ""
        quant_score = d.get("quant_score")
        score_str = f" 量化分{quant_score}" if quant_score is not None else ""
        pullback = d.get("high_pullback_pct")
        pullback_str = f" 高位回落{pullback}%" if pullback is not None else ""

        lines.append(
            f"  {d['name']}({d['code']}) 涨幅{pct_str}% 现价{d['current']} "
            f"开{d['open']} 高{d['high']} 低{d['low']} "
            f"成交额{amt:.2f}亿 振幅{d['amplitude']}%{pullback_str} "
            f"来源:{d['source']}{score_str}{signal_str}{penalty_str}"
            f"{_format_risk_metrics_inline(d)}"
        )

    return "\n".join(lines)


def _format_afternoon_context(afternoon_data: list[dict]) -> str:
    """Format afternoon (尾盘) data as context text for AI recommendation."""
    if not afternoon_data:
        return ""

    sorted_data = sorted(afternoon_data, key=lambda x: (x.get("quant_score") or 0, x.get("main_net_inflow") or 0), reverse=True)

    lines = [f"=== 尾盘资金动向分析 ({len(sorted_data)}只候选) ==="]
    lines.append("说明: 基于14:45左右尾盘数据，已过滤涨停股，候选股均为非涨停+主力净流入为正+沪深主板")

    for d in sorted_data:
        pct_str = f"{d['change_pct']:+.2f}" if d["change_pct"] is not None else "N/A"
        amt = (d["amount"] or 0) / 1e8
        main_net = (d.get("main_net_inflow") or 0) / 1e8
        large_net = (d.get("large_net_inflow") or 0) / 1e8
        main_pct = d.get("main_inflow_pct")
        main_pct_str = f"{main_pct}" if main_pct is not None else "N/A"
        turnover = d.get("turnover_rate")
        turnover_str = f"{turnover}" if turnover is not None else "N/A"
        signal_str = f" 信号:[{','.join(d['signals'])}]" if d.get("signals") else ""
        penalty_tags = d.get("penalty_tags") or []
        penalty_str = f" 风险:[{','.join(penalty_tags)}]" if penalty_tags else ""
        quant_score = d.get("quant_score")
        score_str = f" 量化分{quant_score}" if quant_score is not None else ""
        pullback = d.get("high_pullback_pct")
        pullback_str = f" 高位回落{pullback}%" if pullback is not None else ""

        lines.append(
            f"  {d['name']}({d['code']}) 涨幅{pct_str}% 现价{d['current']} "
            f"开{d['open']} 高{d['high']} 低{d['low']} "
            f"成交额{amt:.2f}亿 振幅{d['amplitude']}%{pullback_str} "
            f"主力净流{main_net:.2f}亿({main_pct_str}%) 大单{large_net:.2f}亿 "
            f"换手{turnover_str}% 来源:{d['source']}{score_str}{signal_str}{penalty_str}"
            f"{_format_risk_metrics_inline(d)}"
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
   - catalyst: 催化剂类型 "业绩预增"/"行业景气"/"资金承接"/"连板情绪"/"技术突破"/"无明显催化剂"
   - high_position_risk: 高位风险 "high"/"medium"/"low"（基于当日收盘价相对推荐价重新评估）
   - risk_note: 具体风险描述（必须含数值）
   - pe_ttm_echo: 回显你读到的 PE(TTM) 数值（便于审计）
   - cum_gain_20d_echo: 回显你读到的近20日累计涨幅%（便于审计）

复盘原则：
   - 收盘价在买入区间内：说明买入机会出现，评估后续空间
   - 收盘价高于买入区间且接近目标价：推荐成功，评估是否继续持有
   - 收盘价低于止损价：推荐失败，分析原因
   - 收盘价高于目标价或达到止盈价：超预期表现
   - 结合当日板块整体表现评估个股相对强弱
   - reason 中要具体说明盘中走势特征（是否触达买入区间、最高/最低价表现等）
   - 对未达预期的推荐，必须在 reason 中归因到至少一类：追高、板块退潮、资金背离、消息兑现、流动性不足、盘中破位
   - 对表现较好的推荐，必须说明成功来自：板块共振、资金延续、低吸有效、强势突破或风险控制有效

估值与安全边际原则（强制，违反将导致复盘被拒绝）：
   - 复盘时 current_price 为当日收盘价，所有累计涨幅与 PE 口径均以收盘价计算；high_position_risk 应基于"收盘价相对推荐价的位置"重新评估
   - 必须读取 context 行尾的 "| PE.. PB.. 累计5日.. 累计20日.." 等指标，禁止忽略；缺失值按 "无法评估" 处理
   - 当 PE(TTM) > 80 且 利润增速 < 20% 时，risk_note 必须写明 "PE={pe} 远超利润增速={g}% 支撑"
   - 当 20 日累计涨幅 > 50% 或 5 日 > 20% 时，high_position_risk 必须为 "high"，且 risk_note 必须写明 "近20日累计+{x}%，追高风险大"
   - catalyst 字段：基于 context 中能观测到的信号推断（业绩预增/行业景气/资金承接/连板情绪/技术突破/无明显催化剂）
   - reason 字段必须引用具体数值（如 "收盘 36.5 距推荐价 36.38 涨 0.3%"、"PE 229 持续高估"），禁止只写"走势符合预期"这类无信息量描述

输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""

_REC_MORNING_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责根据集合竞价数据和市场信息为用户挑选具有投资价值的个股。

请根据以下市场数据和竞价分析，优先参考量化分、信号标签和风险标签，推荐 3-6 只可交易性较好的个股。要求：

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
   - catalyst: 催化剂类型 "业绩预增"/"行业景气"/"资金承接"/"连板情绪"/"技术突破"/"无明显催化剂"
   - high_position_risk: 高位风险 "high"/"medium"/"low"
   - risk_note: 具体风险描述（必须含数值）
   - pe_ttm_echo: 回显你读到的 PE(TTM) 数值（便于审计）
   - cum_gain_20d_echo: 回显你读到的近20日累计涨幅%（便于审计）

2. 推荐原则：
   - 重点参考集合竞价数据、量化分、信号标签和风险标签，优先选择可成交、有换手、有板块共振的股票
   - 买卖比 > 3 说明买盘远强于卖盘，但若同时出现“竞价过热”“成交额偏低”等风险标签，应降级为观察
   - 量比异常(>5)说明市场关注度高，需结合成交额和昨日强势来源确认，不单独作为推荐理由
   - 竞价涨停的股票封板概率高但风险也大，除非量化分高且无明显风险标签，否则不作为普通买入推荐
   - 昨日涨停今日继续高开的股票具有强延续性，但必须确认没有一字不可买或高开过热问题
   - 结合热门板块和隔夜新闻利好，寻找竞价强势+消息面共振的品种
   - 不推荐ST、*ST股票
   - 只推荐沪深主板股票（代码以60或00开头），禁止推荐科创板(688)、创业板(30)、北交所(8/4开头）
   - 买入区间应基于竞价价格合理设定，buy_low 不高于竞价价，buy_high 可略高于竞价价
   - 止盈价和目标价应体现合理盈利预期

2.5 估值与安全边际原则（强制，违反将导致推荐被拒绝）：
   - 必须读取 context 行尾的 "| PE.. PB.. 市值.. 累计5日.. 累计20日.. 营收.. 利润.. 风险标签:[..]" 等指标，禁止忽略；缺失值（行尾无对应字段）按 "无法评估" 处理
   - 当 PE(TTM) > 80 且 利润增速 < 20% 时，视作"高估值无业绩支撑"，confidence 上限 0.5，risk_note 必须写明 "PE={pe} 远超利润增速={g}% 支撑"
   - 当 20 日累计涨幅 > 50% 或 5 日 > 20% 时，必须把 high_position_risk 标为 "high"，且 buy_low 必须 <= 现价 × (1 - 累计涨幅×0.003)，禁止把 buy_low 设在现价 2% 以内
   - 止损位 stop_loss_price：高位股（high_position_risk=high）必须 <= buy_low × 0.96，普通股 <= buy_low × 0.97；禁止沿用"买入区间下方 2-5%"这种宽泛规则
   - 催化剂识别（catalyst）：基于 context 中能观测到的信号推断，禁止臆造。允许类型与推断依据：
       "业绩预增"  - 利润增速 > 50% 或 ROE > 15%
       "行业景气"  - source 标签含 "行业领涨"
       "资金承接"  - source 含 "主力净流入TOP" 或主力净流入显著为正
       "连板情绪"  - 连板 >= 2
       "技术突破"  - 累计 5 日涨幅 > 15% 且 PE < 80（非情绪型上涨）
       "无明显催化剂" - 以上都不满足，confidence 必须 <= 0.4
   - reason 字段必须包含至少 2 条理由，其中至少 1 条引用具体数值（如 "PE 42.9 处于中性"、"近 20 日累计 +52%"、"竞价买卖比 3.5"），禁止只写"上午收阳线涨1.37%"这类无信息量描述

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


_REC_MIDDAY_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责基于上午盘实际资金行为筛选出的强势股，为用户挑选午后有潜力的个股。

候选股池已经过严格筛选——全部为上午盘涨幅 2%-7%（已启动但未透支）、主力净流入为正的真实强势股。你的任务不是判断是否强势（已经确认），而是聚焦下午能否延续、合理买入区间、风险点。

请根据以下上午盘面数据和市场信息，优先参考量化分、信号标签和风险标签，推荐 3-6 只午后有潜力的个股。要求：

1. 每只股票必须包含以下字段，以 JSON 数组格式输出：
   - code: 股票代码（如 600519）
   - name: 股票名称
   - reason: 推荐理由（50-100字，重点结合上午盘面表现和午后预期分析）
   - strategy: 操作策略（如 午盘追涨 / 午后低吸 / 半日强势延续 / 午后反弹）
   - current_price: 当前价格（根据上午行情数据填写）
   - buy_low: 建议买入区间下限
   - buy_high: 建议买入区间上限
   - target_price: 目标价
   - stop_loss_price: 止损价
   - take_profit_price: 止盈价
   - risk_level: 风险等级 low / medium / high
   - confidence: 信心度 0-1 之间的小数
   - sector: 所属行业/板块
   - score: 综合评分 1-10
   - catalyst: 催化剂类型 业绩预增 / 行业景气 / 资金承接 / 连板情绪 / 技术突破 / 无明显催化剂
   - high_position_risk: 高位风险 high / medium / low
   - risk_note: 具体风险描述（必须含数值）
   - pe_ttm_echo: 回显你读到的 PE(TTM) 数值（便于审计）
   - cum_gain_20d_echo: 回显你读到的近20日累计涨幅%（便于审计）

2. 推荐原则：
   - 必须明确推荐逻辑属于半日强势延续或午后低吸，不要把两类策略混写
   - 延续型优先选择量化分高、上午涨幅稳健（3%-7%）、成交额达标、阳线确认且风险标签少的股票
   - 低吸型优先选择上午涨幅 2%-3% 的温和启动股，回踩未破关键区间、板块仍强的标的
   - 关注上午板块轮动方向，午后可能继续发酵的热点板块龙头优先
   - 不推荐ST、*ST股票
   - 只推荐沪深主板股票（代码以60或00开头），禁止推荐科创板(688)、创业板(30)、北交所(8/4开头）
   - 买入区间应基于上午收盘价合理设定，buy_low 不高于当前价，buy_high 可略高于当前价
   - 止盈价和目标价应体现合理盈利预期

2.5 估值与安全边际原则（强制，违反将导致推荐被拒绝）：
   - 必须读取 context 行尾的 PE/PB/市值/累计5日/累计20日/营收/利润/风险标签 等指标，禁止忽略；缺失值按 无法评估 处理
   - 当 PE(TTM) > 80 且 利润增速 < 20% 时，视作高估值无业绩支撑，confidence 上限 0.5，risk_note 必须写明 PE 远超利润增速
   - 当 20 日累计涨幅 > 50% 或 5 日 > 20% 时，必须把 high_position_risk 标为 high，且 buy_low 必须 <= 现价 × (1 - 累计涨幅×0.003)，禁止把 buy_low 设在现价 2% 以内
   - 止损位 stop_loss_price：高位股（high_position_risk=high）必须 <= buy_low × 0.96，普通股 <= buy_low × 0.97；禁止沿用买入区间下方 2-5% 这种宽泛规则
   - 催化剂识别（catalyst）：基于 context 中能观测到的信号推断，禁止臆造。允许类型与推断依据：
       业绩预增  - 利润增速 > 50% 或 ROE > 15%
       行业景气  - source 标签含 行业领涨
       资金承接  - source 含 上午强势 或主力净流入显著为正
       连板情绪  - 连板 >= 2
       技术突破  - 累计 5 日涨幅 > 15% 且 PE < 80（非情绪型上涨）
       无明显催化剂 - 以上都不满足，confidence 必须 <= 0.4
   - reason 字段必须包含至少 2 条理由，其中至少 1 条引用具体数值（如 PE 42.9 处于中性 / 近 20 日累计 +52% / 上午成交 3.2 亿），禁止只写上午收阳线涨1.37% 这类无信息量描述

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


_REC_AFTERNOON_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责基于尾盘资金动向为用户挑选明日有望高开的个股。

以下是 14:45 左右的尾盘资金流向数据（候选股均已过滤掉今日涨停股、ST股、非主板股，且主力净流入为正）。请优先参考量化分、信号标签和风险标签，推荐 3-5 只明日有望高开或继续走强的个股。要求：

1. 每只股票必须包含以下字段，以 JSON 数组格式输出：
   - code: 股票代码（如 "600519"）
   - name: 股票名称
   - reason: 推荐理由（80-120字，重点结合主力资金动向、尾盘走势、板块联动分析明日高开概率）
   - strategy: 操作策略（如 "尾盘低吸"、"尾盘追涨"、"明日高开跟进"、"强势延续持有"）
   - current_price: 当前价格（根据尾盘行情数据填写）
   - buy_low: 建议买入区间下限（基于尾盘价设定）
   - buy_high: 建议买入区间上限
   - target_price: 目标价（明日或短期目标）
   - stop_loss_price: 止损价
   - take_profit_price: 止盈价
   - risk_level: 风险等级 "low"/"medium"/"high"
   - confidence: 信心度 0-1 之间的小数
   - sector: 所属行业/板块
   - score: 综合评分 1-10
   - catalyst: 催化剂类型 "业绩预增"/"行业景气"/"资金承接"/"连板情绪"/"技术突破"/"无明显催化剂"
   - high_position_risk: 高位风险 "high"/"medium"/"low"
   - risk_note: 具体风险描述（必须含数值）
   - pe_ttm_echo: 回显你读到的 PE(TTM) 数值（便于审计）
   - cum_gain_20d_echo: 回显你读到的近20日累计涨幅%（便于审计）

2. 推荐原则：
   - **核心信号：主力净流入金额大且占比高（>5%）** 说明资金真金白银介入，明日高开概率大
   - 优先选择量化分靠前、风险标签少、成交额达标、主力占比强且阳线确认的股票
   - 尾盘涨幅 -2% ~ 7% 区间最理想：包含小幅回调的强势股和稳步上涨的活跃股，既反映资金介入，又留有明日上涨空间
   - 涨幅已经接近 7% 上限的需要谨慎（可能已透支，追高风险大），除非主力占比、板块联动和成交额同时很强，否则降级为观察
   - 小幅回调（-2% ~ 0%）但主力净流入仍为正的股票，可能是明日低开高走的好机会
   - 量价配合：成交额放大 + 主力净流入同向 + 阳线 + 换手率合理（3%-15%）
   - 板块联动：优先选择所在板块整体强势的龙头，明日板块继续发酵时龙头最先受益
   - 大单/超大单净流入为正且金额较大，是机构资金介入的重要信号
   - 振幅较大（>8%）但最终收阳线的，说明尾盘抢筹明显
   - 不推荐ST、*ST股票
   - 只推荐沪深主板股票（代码以60或00开头），禁止推荐科创板(688)、创业板(30)、北交所(8/4开头）
   - 止盈价和目标价应体现明日高开的合理预期（如目标价 = 尾盘价 × 1.03~1.08）

2.5 估值与安全边际原则（强制，违反将导致推荐被拒绝）：
   - 必须读取 context 行尾的 "| PE.. PB.. 市值.. 累计5日.. 累计20日.. 营收.. 利润.. 风险标签:[..]" 等指标，禁止忽略；缺失值按 "无法评估" 处理
   - 当 PE(TTM) > 80 且 利润增速 < 20% 时，视作"高估值无业绩支撑"，confidence 上限 0.5，risk_note 必须写明 "PE={pe} 远超利润增速={g}% 支撑"
   - 当 20 日累计涨幅 > 50% 或 5 日 > 20% 时，必须把 high_position_risk 标为 "high"，且 buy_low 必须 <= 现价 × (1 - 累计涨幅×0.003)，禁止把 buy_low 设在现价 2% 以内
   - 止损位 stop_loss_price：高位股（high_position_risk=high）必须 <= buy_low × 0.96，普通股 <= buy_low × 0.97；禁止沿用"买入区间下方 2-5%"这种宽泛规则
   - 催化剂识别（catalyst）：基于 context 中能观测到的信号推断，禁止臆造。允许类型与推断依据：
       "业绩预增"  - 利润增速 > 50% 或 ROE > 15%
       "行业景气"  - source 标签含 "行业领涨"
       "资金承接"  - source 含 "主力净流入TOP" 或主力净流入显著为正
       "连板情绪"  - 连板 >= 2
       "技术突破"  - 累计 5 日涨幅 > 15% 且 PE < 80（非情绪型上涨）
       "无明显催化剂" - 以上都不满足，confidence 必须 <= 0.4
   - reason 字段必须包含至少 2 条理由，其中至少 1 条引用具体数值（如 "PE 42.9 处于中性"、"近 20 日累计 +52%"、"主力净流入 1.2 亿"），禁止只写"上午收阳线涨1.37%"这类无信息量描述

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


def _get_rec_context(trade_date: str, phase: str = "afternoon", auction_data: list[dict] | None = None, midday_data: list[dict] | None = None, afternoon_data: list[dict] | None = None) -> str:
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

    # Afternoon (尾盘) fund flow analysis
    if phase == "afternoon" and afternoon_data:
        afternoon_text = _format_afternoon_context(afternoon_data)
        if afternoon_text:
            parts.append(afternoon_text)

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
            # afternoon / review / 其它都按"今日涨停股"展示
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
        if not rows and phase in ("midday", "afternoon"):
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
    return llm.parse_json_response(text, expect="array")


def _run_recommendations_sync(trade_date: str, phase: str) -> dict:
    """同步执行推荐生成流程（候选股/复盘数据准备 → LLM → 实时价覆盖 → 落库）。

    供后台 worker 与同步入口共同使用。
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Morning phase: preselect candidates and fetch auction data
    auction_data: list[dict] | None = None
    midday_data: list[dict] | None = None
    afternoon_data: list[dict] | None = None
    enriched_candidates_map: "dict[str, dict]" = {}

    if phase == "morning":
        candidates = _preselect_morning_candidates(trade_date)
        if candidates:
            logger.info("早盘候选股: %d 只，开始获取竞价数据", len(candidates))
            auction_data = _fetch_auction_data(candidates)
            logger.info("竞价数据获取完成: %d 只成功", len(auction_data or []))
            enriched_candidates_map = {c["code"]: c for c in candidates}

    elif phase == "midday":
        candidates = _preselect_midday_candidates(trade_date)
        if candidates:
            logger.info("午盘候选股: %d 只，开始获取上午行情数据", len(candidates))
            midday_data = _fetch_morning_session_data(candidates)
            logger.info("上午行情数据获取完成: %d 只成功", len(midday_data or []))
            enriched_candidates_map = {c["code"]: c for c in candidates}

    elif phase == "afternoon":
        candidates = _preselect_afternoon_candidates(trade_date)
        if candidates:
            logger.info("尾盘候选股: %d 只，开始获取尾盘行情数据", len(candidates))
            afternoon_data = _fetch_afternoon_session_data(candidates)
            logger.info("尾盘行情数据获取完成: %d 只成功", len(afternoon_data or []))
            enriched_candidates_map = {c["code"]: c for c in candidates}

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
        # Review 从 DB 反查 enrichment 字段（沿用 morning/midday 落库的值）
        _conn = get_connection()
        try:
            _rows = _conn.execute(
                "SELECT code, pe_ttm, pe_static, pb, total_market_cap, "
                "cum_gain_5d, cum_gain_20d, cum_gain_60d, "
                "roe, revenue_growth, profit_growth, risk_tags "
                "FROM stock_recommendation "
                "WHERE trade_date = ? AND phase IN ('morning','midday','afternoon')",
                (trade_date,),
            ).fetchall()
            for r in _rows:
                d = dict(r)
                tags_raw = d.pop("risk_tags", "") or ""
                try:
                    tags = json.loads(tags_raw) if tags_raw else []
                except (ValueError, TypeError):
                    tags = []
                enriched_candidates_map[d["code"]] = {**d, "risk_proximity_tags": tags}
        finally:
            _conn.close()

    context = _get_rec_context(
        trade_date, phase,
        auction_data=auction_data,
        midday_data=midday_data,
        afternoon_data=afternoon_data,
    )

    if phase == "morning":
        system_prompt = _REC_MORNING_SYSTEM_PROMPT
    elif phase == "midday":
        system_prompt = _REC_MIDDAY_SYSTEM_PROMPT
    elif phase == "afternoon":
        system_prompt = _REC_AFTERNOON_SYSTEM_PROMPT
    else:
        system_prompt = _REC_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ]
    response = llm.function_chat("stock_recommendation", messages)
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
    if phase in ("morning", "midday", "afternoon", "review") and recs:
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
                prev_close_map: dict[str, float | None] = {}
                for line in r.text.strip().split("\n"):
                    m = _SINA_HQ_PATTERN.match(line.strip())
                    if m:
                        parts = m.group(2).split(",")
                        if len(parts) >= 4:
                            code = m.group(1)[2:]
                            real_price[code] = _parse_float(parts[3])
                            prev_close_map[code] = _parse_float(parts[2])
                now_dt = datetime.now()
                stale_count = 0
                override_count = 0
                for rec in recs:
                    code = rec.get("code", "")
                    rp = real_price.get(code)
                    pc = prev_close_map.get(code)
                    if rp is None:
                        continue
                    # Stale price protection: 实时价≈昨收且在交易时段 → 疑似停牌/数据未刷新
                    if pc is not None and pc > 0 and _is_price_stale(rp, pc, trade_date, now_dt):
                        rec["price_stale"] = 1
                        rec["stale_reason"] = f"实时价{rp}≈昨收{pc}，疑似停牌/数据未刷新"
                        stale_count += 1
                        logger.warning("股 %s 实时价 %s ≈ 昨收 %s，跳过覆盖（保留 LLM 价）", code, rp, pc)
                        continue
                    llm_price = _parse_float(rec.get("current_price"))
                    rec["current_price"] = rp
                    override_count += 1
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
                logger.info(
                    "覆盖 %d 只推荐股的 current_price 为实时价格，%d 只疑似数据未刷新跳过",
                    override_count, stale_count,
                )
            except Exception:
                logger.warning("实时价格覆盖失败，使用 LLM 生成价格", exc_info=True)

    conn = get_connection()
    try:
        # Remove existing recommendations for this date and phase
        conn.execute("DELETE FROM stock_recommendation WHERE trade_date = ? AND phase = ?", (trade_date, phase))

        for rec in recs:
            code = rec.get("code", "")
            m = enriched_candidates_map.get(code, {})
            # LLM echo 审计：若 LLM 回显的 pe_ttm 与 enrichment 真值差异 > 1，告警
            llm_pe_echo = _parse_float(rec.get("pe_ttm_echo"))
            true_pe = _parse_float(m.get("pe_ttm"))
            if llm_pe_echo is not None and true_pe is not None and abs(llm_pe_echo - true_pe) > 1:
                logger.warning(
                    "股 %s LLM pe_ttm_echo=%.2f 与真值=%.2f 差异过大，可能未读取 context",
                    code, llm_pe_echo, true_pe,
                )
            tags_value = m.get("risk_proximity_tags") or []
            try:
                tags_json = json.dumps(tags_value, ensure_ascii=False)
            except (ValueError, TypeError):
                tags_json = "[]"
            conn.execute(
                """INSERT INTO stock_recommendation
                   (trade_date, code, name, reason, strategy, target_price, stop_loss_price,
                    risk_level, confidence, sector, score, model_used, status,
                    current_price, buy_low, buy_high, take_profit_price,
                    phase, created_at, updated_at,
                    pe_ttm, pe_static, pb, total_market_cap,
                    cum_gain_5d, cum_gain_20d, cum_gain_60d,
                    roe, revenue_growth, profit_growth,
                    catalyst, high_position_risk, risk_note, risk_tags, price_stale)
                   VALUES (?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?, ?,?,?,?,?, ?,?,?, ?,?,?, ?,?,?,?, ?)""",
                (
                    trade_date,
                    code,
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
                    true_pe,
                    _parse_float(m.get("pe_static")),
                    _parse_float(m.get("pb")),
                    _parse_float(m.get("total_market_cap")),
                    _parse_float(m.get("cum_gain_5d")),
                    _parse_float(m.get("cum_gain_20d")),
                    _parse_float(m.get("cum_gain_60d")),
                    _parse_float(m.get("roe")),
                    _parse_float(m.get("revenue_growth")),
                    _parse_float(m.get("profit_growth")),
                    rec.get("catalyst", ""),
                    rec.get("high_position_risk", ""),
                    rec.get("risk_note", ""),
                    tags_json,
                    int(rec.get("price_stale") or 0),
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


# ---------------------------------------------------------------------------
# 异步任务管理（参考 limit_up_analysis / tomorrow_strategy 的范式）
# 任务 key 用 (trade_date, phase) 元组，不同 phase 互不干扰
# ---------------------------------------------------------------------------

_rec_tasks_lock = threading.Lock()
_running_rec_tasks: dict[tuple[str, str], dict] = {}


def _set_rec_stage(key: tuple[str, str], stage: str) -> None:
    with _rec_tasks_lock:
        if key in _running_rec_tasks:
            _running_rec_tasks[key]["stage"] = stage


def get_recommendation_task_status(trade_date: str, phase: str) -> dict:
    """查询推荐生成任务进度，供前端轮询。"""
    key = (trade_date, phase)
    with _rec_tasks_lock:
        task = _running_rec_tasks.get(key)
        if not task:
            return {
                "active": False,
                "status": "idle",
                "trade_date": trade_date,
                "phase": phase,
                "started_at": None,
                "finished_at": None,
                "stage": None,
                "total": 0,
                "error": None,
            }
        return {
            "active": task["active"],
            "status": task.get("status", "idle"),
            "trade_date": trade_date,
            "phase": phase,
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "stage": task.get("stage"),
            "total": task.get("total", 0),
            "error": task.get("error"),
        }


def _recommendation_worker(trade_date: str, phase: str) -> None:
    """后台线程：跑完整推荐流程，更新任务状态。"""
    key = (trade_date, phase)
    phase_label = {"morning": "早盘", "midday": "午盘", "review": "收盘复盘", "afternoon": "尾盘"}.get(phase, phase)
    try:
        if phase == "morning":
            _set_rec_stage(key, "候选股预筛+竞价数据")
        elif phase == "midday":
            _set_rec_stage(key, "候选股预筛+上午行情")
        elif phase == "afternoon":
            _set_rec_stage(key, "候选股预筛+尾盘资金流")
        elif phase == "review":
            _set_rec_stage(key, "更新早盘/午盘实际收益")
        else:
            _set_rec_stage(key, "数据准备")

        _set_rec_stage(key, "LLM 分析中（最久环节，约 1-3 分钟）")
        result = _run_recommendations_sync(trade_date, phase)
        total = result.get("total", 0) if isinstance(result, dict) else 0

        with _rec_tasks_lock:
            if key in _running_rec_tasks:
                _running_rec_tasks[key]["active"] = False
                _running_rec_tasks[key]["status"] = "completed"
                _running_rec_tasks[key]["stage"] = None
                _running_rec_tasks[key]["total"] = total
                _running_rec_tasks[key]["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("%s推荐任务完成 trade_date=%s 共 %d 条", phase_label, trade_date, total)
    except Exception as e:
        logger.exception("%s推荐任务异常 trade_date=%s", phase_label, trade_date)
        with _rec_tasks_lock:
            if key in _running_rec_tasks:
                _running_rec_tasks[key]["active"] = False
                _running_rec_tasks[key]["status"] = "failed"
                _running_rec_tasks[key]["error"] = str(e)
                _running_rec_tasks[key]["stage"] = None
                _running_rec_tasks[key]["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def start_recommendation_task(trade_date: str, phase: str) -> dict:
    """立即启动后台推荐生成任务。重复触发同一 date+phase 时，若仍在跑则复用。"""
    key = (trade_date, phase)
    with _rec_tasks_lock:
        existing = _running_rec_tasks.get(key)
        if existing and existing.get("active"):
            return {
                "started": False,
                "already_running": True,
                "trade_date": trade_date,
                "phase": phase,
                "started_at": existing.get("started_at"),
                "stage": existing.get("stage"),
            }
        _running_rec_tasks[key] = {
            "active": True,
            "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
            "stage": "初始化",
            "total": 0,
            "error": None,
        }

    t = threading.Thread(target=_recommendation_worker, args=(trade_date, phase), daemon=True)
    t.start()
    logger.info("已启动推荐生成任务 phase=%s trade_date=%s", phase, trade_date)

    return {
        "started": True,
        "already_running": False,
        "trade_date": trade_date,
        "phase": phase,
        "started_at": _running_rec_tasks[key]["started_at"],
        "stage": _running_rec_tasks[key]["stage"],
    }


def generate_recommendations(trade_date: str | None = None, phase: str = "afternoon") -> dict:
    """同步入口（供定时任务 main.py 调用，与原签名兼容）。

    若已有同 date+phase 任务在跑则直接复用，避免定时任务与手动触发重复执行。
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    with _rec_tasks_lock:
        existing = _running_rec_tasks.get((trade_date, phase))
        if existing and existing.get("active"):
            logger.info("已有同 date+phase 任务在跑，复用 phase=%s", phase)
        else:
            start_recommendation_task(trade_date, phase)

    # 同步等待完成
    import time
    while True:
        with _rec_tasks_lock:
            task = _running_rec_tasks.get((trade_date, phase))
            if not task or not task["active"]:
                break
        time.sleep(2)

    items = get_recommendations_by_date(trade_date, phase)
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


def _fetch_stock_prices_from_sina(codes: list[str]) -> dict[str, dict[str, float | None]]:
    if not codes:
        return {}

    sina_codes = ",".join(_code_to_sina(c) for c in codes)
    r = requests.get(
        f"https://hq.sinajs.cn/list={sina_codes}",
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    r.raise_for_status()

    prices: dict[str, dict[str, float | None]] = {}
    for line in r.text.strip().split("\n"):
        m = _SINA_HQ_PATTERN.match(line.strip())
        if not m:
            continue
        parts = m.group(2).split(",")
        if len(parts) < 4:
            continue
        code = m.group(1)[2:]
        prices[code] = {
            "current": _parse_float(parts[3]),
            "prev_close": _parse_float(parts[2]),
        }
    return prices


def update_recommendation_performance(trade_date: str | None = None, phase: str = "morning") -> dict:
    """Update actual_return_pct for recommendations of a given phase using live prices."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, code FROM stock_recommendation WHERE trade_date = ? AND phase = ?",
            (trade_date, phase),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"updated": 0, "total": 0, "trade_date": trade_date}

    codes = [r["code"] for r in rows]
    try:
        price_map = _fetch_stock_prices_from_sina(codes)
    except Exception:
        logger.warning("Failed to fetch prices for recommendation performance update", exc_info=True)
        return {"updated": 0, "total": len(rows), "trade_date": trade_date}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = 0
    conn = get_connection()
    try:
        for row in rows:
            code = row["code"]
            price = price_map.get(code)
            if not price:
                continue
            current = price.get("current")
            prev_close = price.get("prev_close")
            if current is not None and prev_close and prev_close > 0:
                ret_pct = _round2((current - prev_close) / prev_close * 100)
                conn.execute(
                    "UPDATE stock_recommendation SET current_price = ?, actual_return_pct = ?, updated_at = ? WHERE id = ?",
                    (current, ret_pct, now, row["id"]),
                )
                updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to update recommendation performance")
    finally:
        conn.close()

    logger.info("Updated %s performance for %d / %d stocks on %s", phase, updated, len(rows), trade_date)
    return {"updated": updated, "total": len(rows), "trade_date": trade_date}
