import logging
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.database import get_connection

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


_SNAPSHOT_FIELDS = (
    "code", "name", "price", "change_pct", "change", "volume", "amount",
    "up_count", "down_count", "flat_count",
    "leading_stock", "leading_stock_code", "leading_stock_change_pct",
    "main_net_inflow", "main_net_inflow_pct",
    "super_large_net", "large_net", "medium_net", "small_net",
)


def _get_latest_snapshot(sector_type: str) -> list[dict]:
    """Return items from the latest snapshot as a fallback."""
    conn = get_connection()
    try:
        date_row = conn.execute(
            "SELECT trade_date FROM sector_snapshot WHERE sector_type = ? AND status = 'ok' ORDER BY trade_date DESC LIMIT 1",
            (sector_type,),
        ).fetchone()
        if not date_row:
            return []
        rows = conn.execute(
            f"SELECT {','.join(_SNAPSHOT_FIELDS)} FROM sector_snapshot_item WHERE trade_date = ? AND sector_type = ? ORDER BY change_pct DESC NULLS LAST",
            (date_row["trade_date"], sector_type),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


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

    industry = [_parse_item(i) for i in industry_raw]
    concept = [_parse_item(i) for i in concept_raw]

    if not industry and not concept:
        logger.info("Real-time API empty, falling back to latest snapshot")
        industry = _get_latest_snapshot("industry")
        concept = _get_latest_snapshot("concept")

    return {
        "industry": industry,
        "concept": concept,
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

    industry = [_parse_item(i) for i in industry_raw]
    concept = [_parse_item(i) for i in concept_raw]

    if not industry and not concept:
        logger.info("Real-time capital flow API empty, falling back to latest snapshot")
        industry = _get_latest_snapshot("industry")
        concept = _get_latest_snapshot("concept")

    return {
        "industry": industry,
        "concept": concept,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def snapshot_sector_data(trade_date: str | None = None, trigger: str = "manual") -> dict:
    """Fetch current sector overview + capital flow and persist to database."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        overview = get_sector_overview()
        flow = get_sector_capital_flow()

        result = {"trade_date": trade_date, "industry_count": 0, "concept_count": 0, "success": True, "message": "ok"}

        for sector_type in ("industry", "concept"):
            row = conn.execute(
                "SELECT id, item_count FROM sector_snapshot WHERE trade_date = ? AND sector_type = ?",
                (trade_date, sector_type),
            ).fetchone()
            if row:
                logger.info("Snapshot already exists for %s %s, skipping", trade_date, sector_type)
                result[f"{sector_type}_count"] = row["item_count"]
                continue

            overview_items = {item["code"]: item for item in overview[sector_type]}
            flow_items = {item["code"]: item for item in flow[sector_type]}

            all_codes = set(overview_items.keys()) | set(flow_items.keys())
            if not all_codes:
                logger.warning("No %s sector data fetched", sector_type)
                continue

            cursor = conn.execute(
                "INSERT INTO sector_snapshot (trade_date, sector_type, item_count, status, created_at) VALUES (?, ?, ?, 'ok', ?)",
                (trade_date, sector_type, len(all_codes), now),
            )
            snapshot_id = cursor.lastrowid

            rows = []
            for code in all_codes:
                ov = overview_items.get(code, {})
                fl = flow_items.get(code, {})
                rows.append((
                    snapshot_id, trade_date, sector_type, code,
                    fl.get("name") or ov.get("name", ""),
                    ov.get("price"), ov.get("change_pct"), ov.get("change"),
                    ov.get("volume"), ov.get("amount"),
                    ov.get("up_count"), ov.get("down_count"), ov.get("flat_count"),
                    ov.get("leading_stock"), ov.get("leading_stock_code"), ov.get("leading_stock_change_pct"),
                    fl.get("main_net_inflow"), fl.get("main_net_inflow_pct"),
                    fl.get("super_large_net"), fl.get("large_net"), fl.get("medium_net"), fl.get("small_net"),
                ))

            conn.executemany(
                """INSERT INTO sector_snapshot_item
                   (snapshot_id, trade_date, sector_type, code, name,
                    price, change_pct, change, volume, amount,
                    up_count, down_count, flat_count,
                    leading_stock, leading_stock_code, leading_stock_change_pct,
                    main_net_inflow, main_net_inflow_pct,
                    super_large_net, large_net, medium_net, small_net)
                   VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?, ?,?,?, ?,?,?)""",
                rows,
            )
            result[f"{sector_type}_count"] = len(all_codes)

        conn.commit()
        conn.execute(
            "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            ("sector_snapshot", trigger, "[]", result["industry_count"] + result["concept_count"], "ok", 0, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to snapshot sector data")
        result["success"] = False
        result["message"] = "快照失败，请查看日志"
    finally:
        conn.close()
    return result


def get_sector_history_by_date(trade_date: str, sector_type: str) -> dict:
    """Return all sector items for a single date."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM sector_snapshot_item
               WHERE trade_date = ? AND sector_type = ?
               ORDER BY change_pct DESC NULLS LAST""",
            (trade_date, sector_type),
        ).fetchall()
        items = [dict(r) for r in rows]
        return {
            "trade_date": trade_date,
            "sector_type": sector_type,
            "items": items,
            "item_count": len(items),
        }
    finally:
        conn.close()


def get_sector_history_range(start_date: str, end_date: str, sector_type: str) -> dict:
    """Return aggregated sector data over a date range."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT code, name,
                      AVG(change_pct) as avg_change_pct,
                      SUM(COALESCE(main_net_inflow, 0)) as total_main_net_inflow,
                      AVG(main_net_inflow_pct) as avg_main_net_inflow_pct,
                      MAX(change_pct) as best_change_pct,
                      MIN(change_pct) as worst_change_pct,
                      COUNT(*) as trading_days
               FROM sector_snapshot_item
               WHERE trade_date BETWEEN ? AND ? AND sector_type = ?
               GROUP BY code
               ORDER BY avg_change_pct DESC NULLS LAST""",
            (start_date, end_date, sector_type),
        ).fetchall()
        sectors = [dict(r) for r in rows]
        return {
            "start_date": start_date,
            "end_date": end_date,
            "sector_type": sector_type,
            "sectors": sectors,
        }
    finally:
        conn.close()


def get_sector_trend(code: str, sector_type: str, start_date: str, end_date: str) -> dict:
    """Return daily time-series for a single sector."""
    conn = get_connection()
    try:
        name_row = conn.execute(
            "SELECT name FROM sector_snapshot_item WHERE code = ? AND sector_type = ? LIMIT 1",
            (code, sector_type),
        ).fetchone()
        name = name_row["name"] if name_row else code

        rows = conn.execute(
            """SELECT trade_date as date, change_pct, main_net_inflow, price, volume
               FROM sector_snapshot_item
               WHERE code = ? AND sector_type = ? AND trade_date BETWEEN ? AND ?
               ORDER BY trade_date""",
            (code, sector_type, start_date, end_date),
        ).fetchall()
        return {
            "code": code,
            "name": name,
            "sector_type": sector_type,
            "data": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def get_sector_dates(sector_type: str, limit: int = 90) -> list[str]:
    """Return available snapshot dates, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM sector_snapshot WHERE sector_type = ? ORDER BY trade_date DESC LIMIT ?",
            (sector_type, limit),
        ).fetchall()
        return [r["trade_date"] for r in rows]
    finally:
        conn.close()
