"""
回填 stock_daily 历史数据脚本。

用法：
    cd backend
    python -m app.services.backfill_daily            # 回填自选股+关注股票
    python -m app.services.backfill_daily --all       # 回填所有A股（耗时较长）
    python -m app.services.backfill_daily --codes 600519,000001
"""

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.database import get_connection
from app.services.stock_daily import _classify_board

logger = logging.getLogger(__name__)

_BATCH_INTERVAL = 1.5
_RETRY_DELAYS = [10, 30, 60]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
    "Connection": "keep-alive",
}


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


def _get_watchlist_codes() -> list[str]:
    conn = get_connection()
    try:
        codes = set()
        rows = conn.execute("SELECT code FROM watchlist_stock").fetchall()
        codes.update(r["code"] for r in rows)
        rows = conn.execute(
            "SELECT DISTINCT code FROM stock_recommendation "
            "WHERE created_at >= date('now', '-90 days')"
        ).fetchall()
        codes.update(r["code"] for r in rows)
        rows = conn.execute(
            "SELECT DISTINCT code FROM stock_analysis "
            "WHERE created_at >= date('now', '-30 days')"
        ).fetchall()
        codes.update(r["code"] for r in rows)
        return sorted(codes)
    finally:
        conn.close()


def _get_all_codes() -> list[str]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT MAX(trade_date) as d FROM stock_daily").fetchone()
        if not row or not row["d"]:
            return []
        rows = conn.execute(
            "SELECT DISTINCT code FROM stock_daily WHERE trade_date = ?", (row["d"],)
        ).fetchall()
        return sorted(r["code"] for r in rows)
    finally:
        conn.close()


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


# ---------------------------------------------------------------------------
# Source 1: akshare (primary)
# ---------------------------------------------------------------------------

def _fetch_hist_akshare(code: str, start_date: str, end_date: str):
    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            return df
        except Exception:
            logger.warning("akshare attempt %d failed for %s, retry in %ds", attempt + 1, code, delay)
            time.sleep(delay)
    logger.warning("akshare exhausted for %s", code)
    return None


# ---------------------------------------------------------------------------
# Source 2: East Money kline HTTPS
# ---------------------------------------------------------------------------

def _fetch_hist_em(code: str, start_date: str, end_date: str):
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    session = _build_session()
    try:
        r = session.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101, "fqt": 1, "beg": start_date, "end": end_date,
            },
            headers=_HEADERS, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        klines = (data.get("data") or {}).get("klines") or []
        if not klines:
            return None

        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 11:
                rows.append({
                    "日期": parts[0], "股票代码": code,
                    "开盘": parts[1], "收盘": parts[2],
                    "最高": parts[3], "最低": parts[4],
                    "成交量": parts[5], "成交额": parts[6],
                    "振幅": parts[7], "涨跌幅": parts[8],
                    "涨跌额": parts[9], "换手率": parts[10],
                })
        return pd.DataFrame(rows) if rows else None
    except Exception:
        logger.warning("EM kline failed for %s", code, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Source 3: Sina Finance (last fallback)
# ---------------------------------------------------------------------------

_SINA_KLINE_RE = re.compile(r'"(.+)"')

def _code_to_sina(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith("8") or code.startswith("4"):
        return f"bj{code}"
    return f"sz{code}"


def _fetch_hist_sina(code: str, datalen: int = 150):
    """Fetch historical daily kline from Sina Finance."""
    sina_code = _code_to_sina(code)
    session = _build_session()
    try:
        r = session.get(
            f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var=/CN_MarketDataService.getKLineData",
            params={"symbol": sina_code, "scale": 240, "ma": "no", "datalen": datalen},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
            },
            timeout=20,
        )
        r.raise_for_status()
        m = _SINA_KLINE_RE.search(r.text)
        if not m:
            return None
        import json
        records = json.loads(m.group(1))
        if not records:
            return None

        rows = []
        for rec in records:
            rows.append({
                "日期": rec.get("day", "")[:10], "股票代码": code,
                "开盘": rec.get("open"), "收盘": rec.get("close"),
                "最高": rec.get("high"), "最低": rec.get("low"),
                "成交量": rec.get("volume"), "成交额": None,
                "振幅": None, "涨跌幅": None, "涨跌额": None,
                "换手率": None,
            })
        return pd.DataFrame(rows) if rows else None
    except Exception:
        logger.warning("Sina kline failed for %s", code, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Unified fetch
# ---------------------------------------------------------------------------

def _df_to_items(code: str, df) -> list[dict]:
    """Convert a DataFrame from any source to standard stock_daily items."""
    if df is None or df.empty:
        return []

    items = []
    for _, row in df.iterrows():
        items.append({
            "trade_date": str(row.get("日期", ""))[:10],
            "code": code,
            "name": str(row.get("股票代码", code)),
            "board": _classify_board(code),
            "open": _parse_float(row.get("开盘")),
            "close": _parse_float(row.get("收盘")),
            "high": _parse_float(row.get("最高")),
            "low": _parse_float(row.get("最低")),
            "prev_close": None,
            "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
            "change": _round2(_parse_float(row.get("涨跌额"))),
            "volume": _parse_float(row.get("成交量")),
            "amount": _parse_float(row.get("成交额")),
            "turnover_rate": _round2(_parse_float(row.get("换手率"))),
            "amplitude": _round2(_parse_float(row.get("振幅"))),
            "volume_ratio": None,
            "pe_ttm": None, "pe_static": None, "pb": None,
            "total_market_cap": None, "circulating_market_cap": None,
            "main_net_inflow": None, "main_net_inflow_pct": None,
            "super_large_net": None, "large_net": None,
            "medium_net": None, "small_net": None,
        })

    # Compute prev_close from consecutive closes
    for i in range(len(items) - 1, 0, -1):
        items[i]["prev_close"] = items[i - 1]["close"]

    return items


def _fetch_hist_one(code: str, days: int = 120) -> list[dict]:
    """Fetch historical daily data with 3 sources and retries."""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=int(days * 1.8))).strftime("%Y%m%d")

    # Source 1: akshare
    df = _fetch_hist_akshare(code, start_date, end_date)
    if df is not None and not df.empty:
        logger.info("  %s: got data from akshare (%d rows)", code, len(df))
        return _df_to_items(code, df)

    # Source 2: East Money HTTPS
    df = _fetch_hist_em(code, start_date, end_date)
    if df is not None and not df.empty:
        logger.info("  %s: got data from EM kline (%d rows)", code, len(df))
        return _df_to_items(code, df)

    # Source 3: Sina Finance
    df = _fetch_hist_sina(code, datalen=days + 30)
    if df is not None and not df.empty:
        logger.info("  %s: got data from Sina (%d rows)", code, len(df))
        return _df_to_items(code, df)

    logger.warning("  %s: all 3 sources failed", code)
    return []


# ---------------------------------------------------------------------------
# DB insert
# ---------------------------------------------------------------------------

def _insert_hist_rows(items: list[dict]) -> int:
    """Insert historical rows, skipping dates that already exist."""
    if not items:
        return 0

    code = items[0]["code"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT trade_date FROM stock_daily WHERE code = ?", (code,)
        ).fetchall()
        existing_dates = {r["trade_date"] for r in existing}

        new_items = [i for i in items if i["trade_date"] not in existing_dates]
        if not new_items:
            return 0

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
                    i["trade_date"], i["code"], i["name"], i["board"],
                    i["open"], i["close"], i["high"], i["low"], i["prev_close"],
                    i["change_pct"], i["change"], i["volume"], i["amount"],
                    i["turnover_rate"], i["volume_ratio"], i["amplitude"],
                    i["pe_ttm"], i["pe_static"], i["pb"],
                    i["total_market_cap"], i["circulating_market_cap"],
                    i["main_net_inflow"], i["main_net_inflow_pct"],
                    i["super_large_net"], i["large_net"], i["medium_net"], i["small_net"],
                    now,
                )
                for i in new_items
            ],
        )
        conn.commit()
        return len(new_items)
    except Exception:
        conn.rollback()
        logger.exception("Failed to insert hist rows for %s", code)
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def backfill_daily(codes: list[str] | None = None, days: int = 120) -> dict:
    """Backfill historical daily data for given codes."""
    if not codes:
        codes = _get_watchlist_codes()
    if not codes:
        logger.warning("No target codes found. Run --all or --codes to specify.")
        return {"processed": 0, "failed": 0, "total_rows": 0, "total_codes": 0}

    total_processed = 0
    total_failed = 0
    total_rows = 0

    for idx, code in enumerate(codes, 1):
        logger.info("[%d/%d] Backfilling %s ...", idx, len(codes), code)
        items = _fetch_hist_one(code, days=days)
        if not items:
            total_failed += 1
            time.sleep(_BATCH_INTERVAL)
            continue

        inserted = _insert_hist_rows(items)
        total_rows += inserted
        total_processed += 1
        logger.info("  %s: %d fetched, %d new", code, len(items), inserted)

        if idx < len(codes):
            time.sleep(_BATCH_INTERVAL)

    logger.info(
        "Backfill complete: %d/%d codes, %d rows, %d failed",
        total_processed, len(codes), total_rows, total_failed,
    )
    return {
        "processed": total_processed,
        "failed": total_failed,
        "total_rows": total_rows,
        "total_codes": len(codes),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill stock_daily historical data")
    parser.add_argument("--all", action="store_true", help="Backfill all A-share stocks")
    parser.add_argument("--codes", type=str, help="Comma-separated stock codes")
    parser.add_argument("--days", type=int, default=120, help="Number of trading days (default: 120)")
    args = parser.parse_args()

    target_codes = None
    if args.codes:
        target_codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.all:
        target_codes = _get_all_codes()
        if not target_codes:
            print("No stocks found in stock_daily. Run a snapshot first.")
            sys.exit(1)
        print(f"Found {len(target_codes)} stocks from latest snapshot")

    result = backfill_daily(codes=target_codes, days=args.days)
    print(f"\nResult: {result}")
