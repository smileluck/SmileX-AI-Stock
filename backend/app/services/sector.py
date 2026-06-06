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

INDUSTRY_FS = "m:90+t:2"
CONCEPT_FS = "m:90+t:3"

_SECTOR_FIELDS = "f2,f3,f4,f5,f6,f12,f14,f104,f105,f106,f128,f140,f141,f136"
_CAPITAL_FIELDS = "f2,f3,f12,f14,f62,f66,f72,f78,f84,f184,f184"

_SNAPSHOT_FIELDS = (
    "code", "name", "price", "change_pct", "change", "volume", "amount",
    "up_count", "down_count", "flat_count",
    "leading_stock", "leading_stock_code", "leading_stock_change_pct",
    "main_net_inflow", "main_net_inflow_pct",
    "super_large_net", "large_net", "medium_net", "small_net",
)


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


# ---------------------------------------------------------------------------
# Source 1: East Money (东方财富)
# ---------------------------------------------------------------------------

def _fetch_eastmoney(fs: str, fields: str) -> list[dict]:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    try:
        r = session.get(
            "http://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 500, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3",
                "fs": fs, "fields": fields,
            },
            timeout=10,
            headers=_EASTMONEY_HEADERS,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("data") and data["data"].get("diff"):
            return data["data"]["diff"]
    except Exception:
        logger.debug("East Money fetch failed (fs=%s)", fs, exc_info=True)
    return []


def _parse_em_overview(item: dict) -> dict:
    return {
        "code": item.get("f12", ""),
        "name": item.get("f14", ""),
        "price": _parse_float(item.get("f2")),
        "change_pct": _round2(_parse_float(item.get("f3"))),
        "change": _parse_float(item.get("f4")),
        "volume": _parse_float(item.get("f5")),
        "amount": _parse_float(item.get("f6")),
        "up_count": _parse_float(item.get("f104")),
        "down_count": _parse_float(item.get("f105")),
        "flat_count": _parse_float(item.get("f106")),
        "leading_stock": item.get("f140"),
        "leading_stock_code": item.get("f128"),
        "leading_stock_change_pct": _round2(_parse_float(item.get("f136"))),
    }


def _parse_em_capital_flow(item: dict) -> dict:
    return {
        "code": item.get("f12", ""),
        "name": item.get("f14", ""),
        "change_pct": _round2(_parse_float(item.get("f3"))),
        "main_net_inflow": _parse_float(item.get("f62")),
        "main_net_inflow_pct": _round2(_parse_float(item.get("f184"))),
        "super_large_net": _parse_float(item.get("f66")),
        "large_net": _parse_float(item.get("f72")),
        "medium_net": _parse_float(item.get("f78")),
        "small_net": _parse_float(item.get("f84")),
    }


# ---------------------------------------------------------------------------
# Source 2: THS via akshare (同花顺)
# ---------------------------------------------------------------------------

def _fetch_ths_industry_overview() -> list[dict]:
    try:
        df = ak.stock_board_industry_summary_ths()
        # Columns: 序号, 板块, 涨跌幅, 总成交量, 总成交额, 净流入,
        #          上涨家数, 下跌家数, 均价, 领涨股, 领涨股-最新价, 领涨股-涨跌幅
        results = []
        for _, row in df.iterrows():
            results.append({
                "code": "",
                "name": str(row.get("板块", "")),
                "price": _parse_float(row.get("均价")),
                "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
                "change": None,
                "volume": _parse_float(row.get("总成交量")),
                "amount": _parse_float(row.get("总成交额")),
                "up_count": _parse_float(row.get("上涨家数")),
                "down_count": _parse_float(row.get("下跌家数")),
                "flat_count": None,
                "leading_stock": str(row.get("领涨股", "")),
                "leading_stock_code": None,
                "leading_stock_change_pct": _round2(_parse_float(row.get("领涨股-涨跌幅"))),
                "main_net_inflow": _parse_float(row.get("净流入")),
                "main_net_inflow_pct": None,
                "super_large_net": None,
                "large_net": None,
                "medium_net": None,
                "small_net": None,
            })
        return results
    except Exception:
        logger.debug("THS industry fetch failed", exc_info=True)
    return []


def _fetch_ths_fund_flow(sector_type: str) -> list[dict]:
    """Fetch capital flow from THS data.10jqka.com.cn with pagination."""
    import py_mini_racer
    from io import StringIO
    import pandas as pd
    from akshare.stock_feature.stock_board_industry_ths import _get_file_content_ths

    try:
        js_code = py_mini_racer.MiniRacer()
        js_content = _get_file_content_ths("ths.js")
        js_code.eval(js_content)
        v_code = js_code.call("v")
    except Exception:
        logger.debug("THS JS challenge failed", exc_info=True)
        return []

    path = "hyzjl" if sector_type == "industry" else "gnzjl"
    referer = f"http://data.10jqka.com.cn/funds/{path}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Host": "data.10jqka.com.cn",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": f"v={v_code}",
    }

    all_dfs = []
    for page in range(1, 20):
        url = f"http://data.10jqka.com.cn/funds/{path}/field/tradezdf/order/desc/page/{page}/ajax/1/free/1/"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200 or len(r.text) < 100:
                break
            tables = pd.read_html(StringIO(r.text))
            if not tables or tables[0].shape[0] == 0:
                break
            all_dfs.append(tables[0])
        except Exception:
            break

    if not all_dfs:
        return []

    df = pd.concat(all_dfs, ignore_index=True)
    # Columns: 序号, 行业, 行业指数, 涨跌幅, 流入资金(亿), 流出资金(亿), 净额(亿),
    #          公司家数, 领涨股, 涨跌幅.1, 当前价(元)
    results = []
    for _, row in df.iterrows():
        name = str(row.get("行业", ""))
        inflow = _parse_float(row.get("流入资金(亿)"))
        outflow = _parse_float(row.get("流出资金(亿)"))
        net = _parse_float(row.get("净额(亿)"))
        pct_str = str(row.get("涨跌幅", ""))
        pct = _round2(_parse_float(pct_str.replace("%", "")))

        # net is in 亿, convert to 元 for consistency with EM data
        net_yuan = net * 1e8 if net is not None else None

        results.append({
            "code": "",
            "name": name,
            "change_pct": pct,
            "main_net_inflow": net_yuan,
            "main_net_inflow_pct": None,
            "super_large_net": None,
            "large_net": None,
            "medium_net": None,
            "small_net": None,
        })
    logger.info("THS fund flow (%s): %d items", sector_type, len(results))
    return results


def _fetch_ths_industry_capital_flow() -> list[dict]:
    data = _fetch_ths_fund_flow("industry")
    if data:
        return data
    # Fallback to overview data (has 净流入 but no breakdown)
    data = _fetch_ths_industry_overview()
    return [
        {
            "code": item["code"],
            "name": item["name"],
            "change_pct": item["change_pct"],
            "main_net_inflow": item["main_net_inflow"],
            "main_net_inflow_pct": item["main_net_inflow_pct"],
            "super_large_net": item["super_large_net"],
            "large_net": item["large_net"],
            "medium_net": item["medium_net"],
            "small_net": item["small_net"],
        }
        for item in data
    ]


def _fetch_ths_concept_capital_flow() -> list[dict]:
    return _fetch_ths_fund_flow("concept")


# ---------------------------------------------------------------------------
# Source 3: DB snapshot fallback
# ---------------------------------------------------------------------------

def _get_latest_snapshot(sector_type: str) -> list[dict]:
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
        return [
            {**dict(r), "change_pct": _round2(r["change_pct"]), "leading_stock_change_pct": _round2(r["leading_stock_change_pct"])}
            for r in rows
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Unified getters with fallback chain: THS -> East Money -> DB snapshot
# ---------------------------------------------------------------------------

def _get_industry_overview() -> list[dict]:
    # THS primary
    data = _fetch_ths_industry_overview()
    if data:
        logger.info("Industry overview from THS (%d items)", len(data))
        return data

    # East Money fallback
    raw = _fetch_eastmoney(INDUSTRY_FS, _SECTOR_FIELDS)
    if raw:
        logger.info("Industry overview from East Money (%d items)", len(raw))
        return [_parse_em_overview(i) for i in raw]

    # DB fallback
    data = _get_latest_snapshot("industry")
    if data:
        logger.info("Industry overview from DB snapshot (%d items)", len(data))
    return data


def _get_concept_overview() -> list[dict]:
    # East Money primary (THS has no bulk concept summary)
    raw = _fetch_eastmoney(CONCEPT_FS, _SECTOR_FIELDS)
    if raw:
        logger.info("Concept overview from East Money (%d items)", len(raw))
        return [_parse_em_overview(i) for i in raw]

    # DB fallback
    data = _get_latest_snapshot("concept")
    if data:
        logger.info("Concept overview from DB snapshot (%d items)", len(data))
    return data


def _get_industry_capital_flow() -> list[dict]:
    # THS primary
    data = _fetch_ths_industry_capital_flow()
    if data:
        logger.info("Industry capital flow from THS (%d items)", len(data))
        return data

    # East Money fallback
    raw = _fetch_eastmoney(INDUSTRY_FS, _CAPITAL_FIELDS)
    if raw:
        logger.info("Industry capital flow from East Money (%d items)", len(raw))
        return [_parse_em_capital_flow(i) for i in raw]

    # DB fallback
    data = _get_latest_snapshot("industry")
    if data:
        logger.info("Industry capital flow from DB snapshot (%d items)", len(data))
    return data


def _get_concept_capital_flow() -> list[dict]:
    # THS primary
    data = _fetch_ths_concept_capital_flow()
    if data:
        logger.info("Concept capital flow from THS (%d items)", len(data))
        return data

    # East Money fallback
    raw = _fetch_eastmoney(CONCEPT_FS, _CAPITAL_FIELDS)
    if raw:
        logger.info("Concept capital flow from East Money (%d items)", len(raw))
        return [_parse_em_capital_flow(i) for i in raw]

    # DB fallback
    data = _get_latest_snapshot("concept")
    if data:
        logger.info("Concept capital flow from DB snapshot (%d items)", len(data))
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_sector_overview() -> dict:
    return {
        "industry": _get_industry_overview(),
        "concept": _get_concept_overview(),
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_sector_capital_flow() -> dict:
    return {
        "industry": _get_industry_capital_flow(),
        "concept": _get_concept_capital_flow(),
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

            overview_items = {item["code"]: item for item in overview[sector_type] if item.get("code")}
            flow_items = {item["code"]: item for item in flow[sector_type] if item.get("code")}

            # For THS data where code is empty, use name as key
            if not overview_items and overview[sector_type]:
                overview_items = {item["name"]: item for item in overview[sector_type] if item.get("name")}
                flow_items = {item["name"]: item for item in flow[sector_type] if item.get("name")}

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
                    fl.get("main_net_inflow"), ov.get("main_net_inflow"),
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
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM sector_snapshot_item
               WHERE trade_date = ? AND sector_type = ?
               ORDER BY change_pct DESC NULLS LAST""",
            (trade_date, sector_type),
        ).fetchall()
        items = [{**dict(r), "change_pct": _round2(r["change_pct"]), "leading_stock_change_pct": _round2(r["leading_stock_change_pct"])} for r in rows]
        return {
            "trade_date": trade_date,
            "sector_type": sector_type,
            "items": items,
            "item_count": len(items),
        }
    finally:
        conn.close()


def get_sector_history_range(start_date: str, end_date: str, sector_type: str) -> dict:
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
        sectors = [{**dict(r), "avg_change_pct": _round2(r["avg_change_pct"]), "best_change_pct": _round2(r["best_change_pct"]), "worst_change_pct": _round2(r["worst_change_pct"])} for r in rows]
        return {
            "start_date": start_date,
            "end_date": end_date,
            "sector_type": sector_type,
            "sectors": sectors,
        }
    finally:
        conn.close()


def get_sector_trend(code: str, sector_type: str, start_date: str, end_date: str) -> dict:
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
            "data": [{**dict(r), "change_pct": _round2(r["change_pct"])} for r in rows],
        }
    finally:
        conn.close()


def get_sector_dates(sector_type: str, limit: int = 90) -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM sector_snapshot WHERE sector_type = ? ORDER BY trade_date DESC LIMIT ?",
            (sector_type, limit),
        ).fetchall()
        return [r["trade_date"] for r in rows]
    finally:
        conn.close()
