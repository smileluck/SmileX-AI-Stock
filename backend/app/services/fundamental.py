import logging
import time
from datetime import datetime

import akshare as ak

from app.database import get_connection

logger = logging.getLogger(__name__)

_FIELD_ALIASES = {
    "eps": ("加权每股收益", "每股收益", "基本每股收益", "稀释每股收益"),
    "roe": ("加权净资产收益率", "净资产收益率", "ROE"),
    "revenue_growth": ("主营业务收入增长率", "营业收入增长率", "营收增长率"),
    "profit_growth": ("净利润增长率", "归母净利润增长率"),
    "gross_margin": ("销售毛利率", "毛利率"),
    "net_margin": ("销售净利率", "净利率"),
}

_POSITION_FALLBACKS = {
    "eps": 2,
    "roe": 29,
    "revenue_growth": 31,
    "profit_growth": 32,
    "net_margin": 17,
    "gross_margin": 21,
}

_METRIC_KEYS = tuple(_FIELD_ALIASES.keys())


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = [(col, str(col).replace(" ", "").lower()) for col in columns]
    for alias in aliases:
        target = alias.replace(" ", "").lower()
        for original, compact in normalized:
            if compact == target:
                return original
    for alias in aliases:
        target = alias.replace(" ", "").lower()
        for original, compact in normalized:
            if target in compact:
                return original
    return None


def _latest_report_row(df):
    first_col = df.columns[0]
    sorted_df = df.copy()
    sorted_df[first_col] = sorted_df[first_col].astype(str)
    sorted_df = sorted_df[sorted_df[first_col].str.strip() != ""]
    if sorted_df.empty:
        return None
    return sorted_df.sort_values(first_col, ascending=False).iloc[0]


def _extract_metric(row, columns: list[str], key: str) -> float | None:
    column = _find_column(columns, _FIELD_ALIASES[key])
    if column is not None:
        value = _parse_float(row.get(column))
        if value is not None:
            return value
    fallback = _POSITION_FALLBACKS[key]
    if len(row) > fallback:
        return _parse_float(row.iloc[fallback])
    return None


def fetch_stock_fundamental(code: str) -> dict | None:
    """Fetch fundamental financial indicators for a single stock via akshare."""
    try:
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2023")
        if df is None or df.empty:
            return None

        columns = [str(col) for col in df.columns.tolist()]
        row = _latest_report_row(df)
        if row is None:
            return None

        report_date = str(row.iloc[0]).strip()
        if not report_date:
            return None

        metrics = {key: _extract_metric(row, columns, key) for key in _METRIC_KEYS}
        missing_fields = [key for key, value in metrics.items() if value is None]
        if all(value is None for value in metrics.values()):
            logger.warning("No fundamental metrics extracted for %s; columns=%s", code, columns)
            return None
        if missing_fields:
            logger.debug("Fundamental data missing fields for %s: %s", code, missing_fields)

        return {
            "code": code,
            "report_date": report_date,
            **metrics,
            "missing_fields": missing_fields,
        }
    except Exception:
        logger.warning("Failed to fetch fundamental data for %s", code, exc_info=True)
        return None


def upsert_fundamental(data: dict, name: str = "") -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO stock_fundamental
               (code, name, report_date, roe, eps, revenue_growth,
                profit_growth, gross_margin, net_margin, update_time, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(code, report_date) DO UPDATE SET
                   roe=excluded.roe, eps=excluded.eps,
                   revenue_growth=excluded.revenue_growth,
                   profit_growth=excluded.profit_growth,
                   gross_margin=excluded.gross_margin,
                   net_margin=excluded.net_margin,
                   update_time=excluded.update_time""",
            (
                data["code"], name, data["report_date"],
                data.get("roe"), data.get("eps"),
                data.get("revenue_growth"), data.get("profit_growth"),
                data.get("gross_margin"), data.get("net_margin"),
                now, now,
            ),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        logger.warning("Failed to store fundamental data for %s", data.get("code"), exc_info=True)
        return False
    finally:
        conn.close()


def _get_target_codes() -> list[str]:
    """Get list of stock codes that need fundamental data."""
    conn = get_connection()
    try:
        codes = set()
        rows = conn.execute("SELECT code FROM watchlist_stock").fetchall()
        codes.update(r["code"] for r in rows)
        rows = conn.execute(
            "SELECT DISTINCT code FROM stock_recommendation "
            "WHERE created_at >= date('now', '-30 days')"
        ).fetchall()
        codes.update(r["code"] for r in rows)
        rows = conn.execute(
            "SELECT DISTINCT code FROM stock_analysis "
            "WHERE created_at >= date('now', '-7 days')"
        ).fetchall()
        codes.update(r["code"] for r in rows)
        return sorted(codes)
    finally:
        conn.close()


def snapshot_fundamental_batch(codes: list[str] | None = None, trigger: str = "manual") -> dict:
    """Fetch and store fundamental data for target stocks."""
    if not codes:
        codes = _get_target_codes()
    if not codes:
        return {"processed": 0, "failed": 0, "total": 0}

    processed = 0
    failed = 0

    for code in codes:
        data = fetch_stock_fundamental(code)
        if not data:
            failed += 1
            continue
        if upsert_fundamental(data):
            processed += 1
        else:
            failed += 1

        time.sleep(0.5)

    logger.info(
        "Fundamental snapshot: %d/%d processed, %d failed (trigger=%s)",
        processed, len(codes), failed, trigger,
    )
    return {"processed": processed, "failed": failed, "total": len(codes)}


def refresh_one_fundamental(code: str) -> dict:
    """实时抓取单只股票基本面并入库。"""
    data = fetch_stock_fundamental(code)
    if not data:
        return {
            "code": code,
            "success": False,
            "message": "AkShare 无可用财报指标",
        }
    if not upsert_fundamental(data):
        return {
            "code": code,
            "success": False,
            "report_date": data.get("report_date"),
            "missing_fields": data.get("missing_fields", []),
            "message": "抓取成功但入库失败",
        }
    return {
        "code": code,
        "success": True,
        "report_date": data.get("report_date"),
        "missing_fields": data.get("missing_fields", []),
        "message": "基本面已更新",
    }


def get_latest_fundamental(code: str) -> dict | None:
    """Get the latest fundamental data for a stock."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM stock_fundamental WHERE code = ? ORDER BY report_date DESC LIMIT 1",
            (code,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None
