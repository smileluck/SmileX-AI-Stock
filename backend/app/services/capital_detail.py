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


def _is_shanghai(code: str) -> bool:
    return code.startswith("6")


def _fetch_northbound(code: str, trade_date: str) -> dict | None:
    """Fetch northbound holding data for a single stock."""
    try:
        df = ak.stock_hsgt_individual_em(symbol=code)
        if df is None or df.empty:
            return None

        # Filter to the trade_date or the closest date before it
        df["持股日期"] = df["持股日期"].astype(str)
        df = df[df["持股日期"] <= trade_date]
        if df.empty:
            return None

        row = df.iloc[-1]
        return {
            "north_hold_qty": _parse_float(row.get("持股数量")),
            "north_hold_market_cap": _parse_float(row.get("持股市值")),
            "north_hold_pct": _parse_float(row.get("持股数量占A股百分比")),
        }
    except (TypeError, KeyError):
        # Stock not in HK Connect program — expected for many stocks
        logger.debug("Northbound data unavailable for %s", code)
        return None
    except Exception:
        logger.warning("Northbound fetch failed for %s", code, exc_info=True)
        return None


def _load_margin_sse(trade_date: str) -> dict[str, dict]:
    """Fetch SSE margin data for all stocks on a given date. Returns {code: data}."""
    try:
        date_str = trade_date.replace("-", "")
        df = ak.stock_margin_detail_sse(date=date_str)
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            code = str(row.get("标的证券代码", ""))
            if not code:
                continue
            result[code] = {
                "margin_buy": _parse_float(row.get("融资买入额")),
                "margin_balance": _parse_float(row.get("融资余额")),
                "short_sell_volume": _parse_float(row.get("融券卖出量")),
                "short_balance": _parse_float(row.get("融券余量")),
            }
        logger.info("SSE margin data loaded: %d stocks for %s", len(result), trade_date)
        return result
    except (ValueError, TypeError):
        # API returned empty data for this date — expected on non-trading days
        logger.debug("SSE margin data unavailable for %s", trade_date)
        return {}
    except Exception:
        logger.warning("SSE margin fetch failed for %s", trade_date, exc_info=True)
        return {}


def _load_margin_szse(trade_date: str) -> dict[str, dict]:
    """Fetch SZSE margin data for all stocks on a given date. Returns {code: data}."""
    try:
        date_str = trade_date.replace("-", "")
        df = ak.stock_margin_detail_szse(date=date_str)
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            code = str(row.get("证券代码", ""))
            if not code:
                continue
            result[code] = {
                "margin_buy": _parse_float(row.get("融资买入额")),
                "margin_balance": _parse_float(row.get("融资余额")),
                "short_sell_volume": _parse_float(row.get("融券卖出量")),
                "short_balance": _parse_float(row.get("融券余量")),
            }
        logger.info("SZSE margin data loaded: %d stocks for %s", len(result), trade_date)
        return result
    except (ValueError, TypeError):
        logger.debug("SZSE margin data unavailable for %s", trade_date)
        return {}
    except Exception:
        logger.warning("SZSE margin fetch failed for %s", trade_date, exc_info=True)
        return {}


def _get_target_codes() -> list[str]:
    """Get list of stock codes that need capital detail data."""
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
        # Only SH and SZ main-board stocks have margin trading
        return sorted(c for c in codes if c.startswith(("6", "0", "3")))
    finally:
        conn.close()


def snapshot_capital_detail(trade_date: str | None = None, trigger: str = "manual") -> dict:
    """Fetch and store capital detail data for target stocks."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    codes = _get_target_codes()
    if not codes:
        return {"trade_date": trade_date, "processed": 0, "failed": 0, "total": 0}

    # Batch-fetch margin data once per exchange (instead of per stock)
    sse_margin = _load_margin_sse(trade_date)
    szse_margin = _load_margin_szse(trade_date)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    processed = 0
    failed = 0

    for code in codes:
        north = _fetch_northbound(code, trade_date)
        if _is_shanghai(code):
            margin = sse_margin.get(code)
        else:
            margin = szse_margin.get(code)

        if not north and not margin:
            failed += 1
            continue

        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO stock_capital_detail
                   (trade_date, code, name,
                    north_hold_qty, north_hold_market_cap, north_hold_pct,
                    margin_balance, margin_buy, short_sell_volume, short_balance,
                    created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(trade_date, code) DO UPDATE SET
                       north_hold_qty=excluded.north_hold_qty,
                       north_hold_market_cap=excluded.north_hold_market_cap,
                       north_hold_pct=excluded.north_hold_pct,
                       margin_balance=excluded.margin_balance,
                       margin_buy=excluded.margin_buy,
                       short_sell_volume=excluded.short_sell_volume,
                       short_balance=excluded.short_balance""",
                (
                    trade_date, code, "",
                    (north or {}).get("north_hold_qty"),
                    (north or {}).get("north_hold_market_cap"),
                    (north or {}).get("north_hold_pct"),
                    (margin or {}).get("margin_balance"),
                    (margin or {}).get("margin_buy"),
                    (margin or {}).get("short_sell_volume"),
                    (margin or {}).get("short_balance"),
                    now,
                ),
            )
            conn.commit()
            processed += 1
        except Exception:
            conn.rollback()
            logger.warning("Failed to store capital detail for %s", code, exc_info=True)
            failed += 1
        finally:
            conn.close()

        time.sleep(0.3)

    logger.info(
        "Capital detail snapshot for %s: %d/%d processed, %d failed (trigger=%s)",
        trade_date, processed, len(codes), failed, trigger,
    )
    return {"trade_date": trade_date, "processed": processed, "failed": failed, "total": len(codes)}


def get_latest_capital_detail(code: str, trade_date: str | None = None) -> dict | None:
    """Get the latest capital detail data for a stock."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM stock_capital_detail WHERE code = ? AND trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT 1",
            (code, trade_date),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None
