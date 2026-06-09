import logging
from datetime import datetime

import akshare as ak
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.database import get_connection

logger = logging.getLogger(__name__)

_EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
}

# East Money push2 clist API field codes for individual stocks
_STOCK_FIELDS = (
    "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,"
    "f15,f16,f17,f18,f20,f21,f23,f62,f115,f184,"
    "f66,f72,f78,f84"
)

# fs parameter: all A-share stocks (SH main + SZ main + ChiNext + STAR + BSE)
_STOCK_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

_ALLOWED_SORTS = frozenset({
    "change_pct", "amount", "turnover_rate", "volume", "main_net_inflow",
    "close", "pe_ttm", "pb", "total_market_cap", "volume_ratio", "amplitude",
    "main_net_inflow_pct", "change",
})


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _round2(val) -> float | None:
    if val is None:
        return None
    return round(val, 2)


def _classify_board(code: str) -> str:
    if code.startswith("688"):
        return "科创板"
    if code.startswith("60") or code.startswith("00"):
        return "沪深主板"
    if code.startswith("30"):
        return "创业板"
    if code.startswith("8") or code.startswith("4"):
        return "北交所"
    return "其他"


# ---------------------------------------------------------------------------
# Source 1: East Money push2 (primary)
# ---------------------------------------------------------------------------

def _fetch_all_stocks_em() -> list[dict]:
    """Fetch all A-share spot data + capital flow from East Money in one call."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))

    all_items: list[dict] = []
    page = 1
    page_size = 6000

    while True:
        try:
            r = session.get(
                "http://push2.eastmoney.com/api/qt/clist/get",
                params={
                    "pn": page, "pz": page_size, "po": 1, "np": 1,
                    "fltt": 2, "invt": 2, "fid": "f3",
                    "fs": _STOCK_FS, "fields": _STOCK_FIELDS,
                },
                timeout=20,
                headers=_EASTMONEY_HEADERS,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            logger.warning("East Money stock fetch failed (page %d)", page, exc_info=True)
            break

        diff = (data.get("data") or {}).get("diff") or []
        if not diff:
            break

        for item in diff:
            code = str(item.get("f12", ""))
            all_items.append({
                "code": code,
                "name": str(item.get("f14", "")),
                "board": _classify_board(code),
                "close": _parse_float(item.get("f2")),
                "change_pct": _round2(_parse_float(item.get("f3"))),
                "change": _parse_float(item.get("f4")),
                "volume": _parse_float(item.get("f5")),
                "amount": _parse_float(item.get("f6")),
                "amplitude": _round2(_parse_float(item.get("f7"))),
                "turnover_rate": _round2(_parse_float(item.get("f8"))),
                "pe_ttm": _round2(_parse_float(item.get("f9"))),
                "volume_ratio": _round2(_parse_float(item.get("f10"))),
                "high": _parse_float(item.get("f15")),
                "low": _parse_float(item.get("f16")),
                "open": _parse_float(item.get("f17")),
                "prev_close": _parse_float(item.get("f18")),
                "total_market_cap": _parse_float(item.get("f20")),
                "circulating_market_cap": _parse_float(item.get("f21")),
                "pb": _round2(_parse_float(item.get("f23"))),
                "main_net_inflow": _parse_float(item.get("f62")),
                "super_large_net": _parse_float(item.get("f66")),
                "large_net": _parse_float(item.get("f72")),
                "medium_net": _parse_float(item.get("f78")),
                "small_net": _parse_float(item.get("f84")),
                "pe_static": _round2(_parse_float(item.get("f115"))),
                "main_net_inflow_pct": _round2(_parse_float(item.get("f184"))),
            })

        total = (data.get("data") or {}).get("total", 0)
        if page * page_size >= total:
            break
        page += 1

    logger.info("Fetched %d A-share stocks from East Money", len(all_items))
    return all_items


# ---------------------------------------------------------------------------
# Source 2: akshare fallback
# ---------------------------------------------------------------------------

def _fetch_all_stocks_akshare() -> list[dict]:
    """Fallback: fetch all A-share spot data via akshare."""
    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return []
        items = []
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            items.append({
                "code": code,
                "name": str(row.get("名称", "")),
                "board": _classify_board(code),
                "close": _parse_float(row.get("最新价")),
                "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
                "change": _parse_float(row.get("涨跌额")),
                "volume": _parse_float(row.get("成交量")),
                "amount": _parse_float(row.get("成交额")),
                "amplitude": _round2(_parse_float(row.get("振幅"))),
                "turnover_rate": _round2(_parse_float(row.get("换手率"))),
                "pe_ttm": _round2(_parse_float(row.get("市盈率-动态"))),
                "volume_ratio": _round2(_parse_float(row.get("量比"))),
                "high": _parse_float(row.get("最高")),
                "low": _parse_float(row.get("最低")),
                "open": _parse_float(row.get("今开")),
                "prev_close": _parse_float(row.get("昨收")),
                "total_market_cap": _parse_float(row.get("总市值")),
                "circulating_market_cap": _parse_float(row.get("流通市值")),
                "pb": _round2(_parse_float(row.get("市净率"))),
                "main_net_inflow": None,
                "super_large_net": None,
                "large_net": None,
                "medium_net": None,
                "small_net": None,
                "pe_static": None,
                "main_net_inflow_pct": None,
            })
        logger.info("Fetched %d A-share stocks via akshare", len(items))
        return items
    except Exception:
        logger.warning("akshare stock_zh_a_spot_em failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Snapshot (scheduled task entry)
# ---------------------------------------------------------------------------

def snapshot_stock_daily(trade_date: str | None = None, trigger: str = "manual") -> dict:
    """Fetch all A-share daily data and persist to stock_daily table."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    items = _fetch_all_stocks_em()
    if not items:
        logger.info("East Money empty, trying akshare fallback")
        items = _fetch_all_stocks_akshare()
    if not items:
        return {"trade_date": trade_date, "item_count": 0, "success": False, "message": "所有数据源均失败"}

    conn = get_connection()
    try:
        conn.execute("DELETE FROM stock_daily WHERE trade_date = ?", (trade_date,))
        conn.executemany(
            """INSERT INTO stock_daily
               (trade_date, code, name, board,
                open, close, high, low, prev_close,
                change_pct, change, volume, amount,
                turnover_rate, volume_ratio, amplitude,
                pe_ttm, pe_static, pb,
                total_market_cap, circulating_market_cap,
                main_net_inflow, main_net_inflow_pct,
                super_large_net, large_net, medium_net, small_net,
                created_at)
               VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?, ?,?)""",
            [
                (
                    trade_date, i["code"], i["name"], i["board"],
                    i["open"], i["close"], i["high"], i["low"], i["prev_close"],
                    i["change_pct"], i["change"], i["volume"], i["amount"],
                    i["turnover_rate"], i["volume_ratio"], i["amplitude"],
                    i["pe_ttm"], i["pe_static"], i["pb"],
                    i["total_market_cap"], i["circulating_market_cap"],
                    i["main_net_inflow"], i["main_net_inflow_pct"],
                    i["super_large_net"], i["large_net"], i["medium_net"], i["small_net"],
                    now,
                )
                for i in items
            ],
        )
        conn.execute(
            "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            ("stock_daily_snapshot", trigger, "[]", len(items), "ok", 0, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to snapshot stock daily data")
        return {"trade_date": trade_date, "item_count": 0, "success": False, "message": "快照失败"}
    finally:
        conn.close()

    logger.info("Stock daily snapshot for %s: %d items", trade_date, len(items))
    return {"trade_date": trade_date, "item_count": len(items), "success": True, "message": "ok"}


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def get_stock_daily(
    trade_date: str,
    sort_by: str = "change_pct",
    sort_order: str = "desc",
    board: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    if sort_by not in _ALLOWED_SORTS:
        sort_by = "change_pct"
    order_dir = "DESC" if sort_order == "desc" else "ASC"
    nulls = "NULLS LAST" if sort_order == "desc" else "NULLS FIRST"

    conditions = ["trade_date = ?"]
    params: list = [trade_date]
    if board:
        conditions.append("board = ?")
        params.append(board)
    if keyword:
        conditions.append("(code LIKE ? OR name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    where = " AND ".join(conditions)

    conn = get_connection()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM stock_daily WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM stock_daily WHERE {where} ORDER BY {sort_by} {order_dir} {nulls} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows], total


def get_stock_daily_detail(code: str, trade_date: str | None = None) -> dict | None:
    conn = get_connection()
    try:
        if trade_date:
            row = conn.execute(
                "SELECT * FROM stock_daily WHERE code = ? AND trade_date = ?",
                (code, trade_date),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM stock_daily WHERE code = ? ORDER BY trade_date DESC LIMIT 1",
                (code,),
            ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_stock_daily_ranking(
    trade_date: str,
    metric: str = "change_pct",
    board: str | None = None,
    top_n: int = 20,
) -> list[dict]:
    if metric not in _ALLOWED_SORTS:
        metric = "change_pct"

    conditions = ["trade_date = ?"]
    params: list = [trade_date]
    if board:
        conditions.append("board = ?")
        params.append(board)

    where = " AND ".join(conditions)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT * FROM stock_daily WHERE {where} ORDER BY {metric} DESC NULLS LAST LIMIT ?",
            params + [top_n],
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_stock_daily_dates(limit: int = 90) -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM stock_daily ORDER BY trade_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["trade_date"] for r in rows]
    finally:
        conn.close()


def get_stock_daily_summary(trade_date: str) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                COUNT(*) as total_count,
                SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) as up_count,
                SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) as down_count,
                SUM(CASE WHEN change_pct = 0 OR change_pct IS NULL THEN 1 ELSE 0 END) as flat_count,
                AVG(change_pct) as avg_change_pct,
                AVG(turnover_rate) as avg_turnover_rate,
                SUM(amount) as total_amount,
                SUM(CASE WHEN change_pct >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
                SUM(CASE WHEN change_pct <= -9.9 THEN 1 ELSE 0 END) as limit_down_count
               FROM stock_daily WHERE trade_date = ?""",
            (trade_date,),
        ).fetchone()

        board_rows = conn.execute(
            """SELECT board,
                COUNT(*) as count,
                AVG(change_pct) as avg_change_pct,
                SUM(amount) as total_amount,
                SUM(main_net_inflow) as total_net_inflow
               FROM stock_daily WHERE trade_date = ?
               GROUP BY board ORDER BY avg_change_pct DESC NULLS LAST""",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "trade_date": trade_date,
        "overview": dict(row) if row else {},
        "by_board": [dict(r) for r in board_rows],
    }
