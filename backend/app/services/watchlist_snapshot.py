"""自选股每日快照服务。

工作日 15:30 定时执行（也支持手动触发）：拉取所有 watching 状态关注股的完整 OHLC +
资金流，写入 watchlist_stock_daily，作为买入时机分析的 K 线数据源。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from app.database import get_connection
from app.services.stock_daily import _fetch_one_stock_spot

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _get_watching_codes() -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code FROM watchlist_stock WHERE status = 'watching' ORDER BY id"
        ).fetchall()
        return [r["code"] for r in rows]
    finally:
        conn.close()


def _insert_watchlist_daily(item: dict, trade_date: str) -> bool:
    """INSERT OR REPLACE 单条 watchlist_stock_daily。item 来自 _fetch_one_stock_spot。"""
    if not item or not item.get("close"):
        return False
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO watchlist_stock_daily
               (code, trade_date, open, high, low, close, prev_close,
                change_pct, change, volume, amount, turnover_rate,
                main_net_inflow, main_net_inflow_pct, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.get("code"),
                trade_date,
                item.get("open"),
                item.get("high"),
                item.get("low"),
                item.get("close"),
                item.get("prev_close"),
                item.get("change_pct"),
                item.get("change"),
                item.get("volume"),
                item.get("amount"),
                item.get("turnover_rate"),
                item.get("main_net_inflow"),
                item.get("main_net_inflow_pct"),
                now,
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def snapshot_watchlist_daily(trade_date: str | None = None, trigger: str = "manual") -> dict:
    """拉取所有 watching 关注股的当日行情快照，写入 watchlist_stock_daily。

    返回 {trade_date, total, success, failed, missing_codes}
    """
    if not trade_date:
        trade_date = _today()

    codes = _get_watching_codes()
    if not codes:
        logger.info("watchlist_snapshot: no watching stocks, skip")
        return {"trade_date": trade_date, "total": 0, "success": 0, "failed": 0, "missing_codes": []}

    logger.info("watchlist_snapshot start: %d codes, trigger=%s", len(codes), trigger)

    success = 0
    failed: list[str] = []

    # 并发拉取（max_workers=8 与 stock.py 推荐场景一致，避免被风控）
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one_stock_spot, c): c for c in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                item = fut.result()
            except Exception:
                item = None
            if item:
                if _insert_watchlist_daily(item, trade_date):
                    success += 1
                else:
                    failed.append(code)
            else:
                failed.append(code)

    logger.info(
        "watchlist_snapshot done: success=%d failed=%d total=%d",
        success, len(failed), len(codes),
    )

    return {
        "trade_date": trade_date,
        "total": len(codes),
        "success": success,
        "failed": len(failed),
        "missing_codes": failed,
    }
