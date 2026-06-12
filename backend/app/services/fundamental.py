import logging
import time
from datetime import datetime

import akshare as ak

from app.database import get_connection

logger = logging.getLogger(__name__)


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _code_to_ak_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    return f"sz{code}"


def fetch_stock_fundamental(code: str) -> dict | None:
    """Fetch fundamental financial indicators for a single stock via akshare."""
    try:
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2023")
        if df is None or df.empty:
            return None

        row = df.iloc[0]
        cols = df.columns.tolist()

        report_date = str(row.iloc[0])
        eps = _parse_float(row.iloc[2])           # 加权每股收益
        roe = _parse_float(row.iloc[29])           # 加权净资产收益率
        revenue_growth = _parse_float(row.iloc[31])  # 主营业务收入增长率
        profit_growth = _parse_float(row.iloc[32])   # 净利润增长率
        net_margin = _parse_float(row.iloc[17])       # 销售净利率
        gross_margin = _parse_float(row.iloc[21])     # 销售毛利率

        return {
            "code": code,
            "report_date": report_date,
            "roe": roe,
            "eps": eps,
            "revenue_growth": revenue_growth,
            "profit_growth": profit_growth,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
        }
    except Exception:
        logger.warning("Failed to fetch fundamental data for %s", code, exc_info=True)
        return None


def _get_target_codes() -> list[str]:
    """Get list of stock codes that need fundamental data."""
    conn = get_connection()
    try:
        codes = set()
        # Watchlist stocks
        rows = conn.execute("SELECT code FROM watchlist_stock").fetchall()
        codes.update(r["code"] for r in rows)
        # Recently recommended stocks (last 30 days)
        rows = conn.execute(
            "SELECT DISTINCT code FROM stock_recommendation "
            "WHERE created_at >= date('now', '-30 days')"
        ).fetchall()
        codes.update(r["code"] for r in rows)
        # Stocks with recent analysis
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

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    processed = 0
    failed = 0

    for code in codes:
        data = fetch_stock_fundamental(code)
        if not data:
            failed += 1
            continue

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
                    code, "", data["report_date"],
                    data["roe"], data["eps"],
                    data["revenue_growth"], data["profit_growth"],
                    data["gross_margin"], data["net_margin"],
                    now, now,
                ),
            )
            conn.commit()
            processed += 1
        except Exception:
            conn.rollback()
            logger.warning("Failed to store fundamental data for %s", code, exc_info=True)
            failed += 1
        finally:
            conn.close()

        time.sleep(0.5)

    logger.info(
        "Fundamental snapshot: %d/%d processed, %d failed (trigger=%s)",
        processed, len(codes), failed, trigger,
    )
    return {"processed": processed, "failed": failed, "total": len(codes)}


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
