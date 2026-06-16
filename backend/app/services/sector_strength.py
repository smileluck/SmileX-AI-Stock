import logging
from collections import defaultdict
from datetime import datetime, timedelta

from app.database import get_connection

logger = logging.getLogger(__name__)


def _fetch_recent_snapshots(end_date: str, lookback_days: int) -> list[dict]:
    """取 end_date 当天 + 往前 lookback_days 个自然日内的板块快照。"""
    dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_date = (dt - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT trade_date, sector_type, code, name, change_pct, main_net_inflow, "
            "leading_stock, leading_stock_code, leading_stock_change_pct, up_count, down_count "
            "FROM sector_snapshot_item "
            "WHERE trade_date BETWEEN ? AND ? "
            "ORDER BY trade_date DESC",
            (start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def calc_sector_streak(end_date: str, lookback_days: int = 8, top_k: int = 30) -> list[dict]:
    """从 sector_snapshot_item 派生连续强势板块。

    streak_up_days：从 end_date 当天往前，change_pct>0 的连续天数。
    排序键：(streak_up_days DESC, avg_change_pct DESC)。
    """
    rows = _fetch_recent_snapshots(end_date, lookback_days)
    if not rows:
        return []

    # 按 (code, sector_type) 聚合
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["code"], r["sector_type"])].append(r)

    # 取 end_date 当天有数据的板块作为候选池（避免历史已退潮板块污染）
    today_codes = {(r["code"], r["sector_type"]) for r in rows if r["trade_date"] == end_date}

    results = []
    for key, items in grouped.items():
        if key not in today_codes:
            continue
        items.sort(key=lambda x: x["trade_date"], reverse=True)
        today = items[0]

        streak = 0
        for it in items:
            cp = it.get("change_pct")
            if cp is not None and cp > 0:
                streak += 1
            else:
                break

        cps = [it.get("change_pct") or 0 for it in items]
        avg_cp = sum(cps) / len(cps) if cps else 0
        total_inflow = sum((it.get("main_net_inflow") or 0) for it in items)
        best_cp = max(cps) if cps else 0
        trading_days = len(items)

        results.append(
            {
                "code": today["code"],
                "name": today["name"],
                "sector_type": today["sector_type"],
                "change_pct_today": today.get("change_pct"),
                "streak_up_days": streak,
                "avg_change_pct": round(avg_cp, 2),
                "cumulative_main_net_inflow": round(total_inflow, 0),
                "best_single_day_pct": round(best_cp, 2),
                "trading_days": trading_days,
                "leading_stock": today.get("leading_stock"),
                "leading_stock_code": today.get("leading_stock_code"),
                "leading_stock_change_pct": today.get("leading_stock_change_pct"),
                "up_count": today.get("up_count"),
                "down_count": today.get("down_count"),
                "main_net_inflow_today": today.get("main_net_inflow"),
            }
        )

    results.sort(
        key=lambda x: (x["streak_up_days"], x["avg_change_pct"], x["main_net_inflow_today"] or 0),
        reverse=True,
    )
    return results[:top_k]


def get_sector_snapshot_top(trade_date: str, top_k: int = 20) -> list[dict]:
    """取当天按 change_pct + main_net_inflow 综合排序的板块。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code, name, sector_type, change_pct, main_net_inflow, "
            "leading_stock, leading_stock_code, leading_stock_change_pct, "
            "up_count, down_count "
            "FROM sector_snapshot_item WHERE trade_date=? "
            "ORDER BY change_pct DESC",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows][:top_k]
