"""数据加载层：从 stock_daily / benchmark_daily 加载历史数据。

回测与策略信号生成全部依赖这里，禁止调用任何实时 API。
"""
from __future__ import annotations

import logging
from typing import Iterable

import pandas as pd

from app.database import get_connection

logger = logging.getLogger(__name__)

# 沪深300 akshare 代码
_BENCHMARK_AK_CODE = {
    "hs300": "sh000300",
    "sz50": "sh000016",
    "czb": "sh399006",
}


def load_trade_dates(start: str, end: str) -> list[str]:
    """返回 [start, end] 区间内 stock_daily 实际有数据的交易日升序列表。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM stock_daily "
            "WHERE trade_date >= ? AND trade_date <= ? "
            "ORDER BY trade_date ASC",
            (start, end),
        ).fetchall()
        return [r["trade_date"] for r in rows]
    finally:
        conn.close()


def load_daily_panel(trade_date: str, board: str = "all") -> pd.DataFrame:
    """加载某日全市场（或指定板块）的 stock_daily 快照。

    Args:
        trade_date: YYYY-MM-DD
        board: all / main / sh_main / sz_main / gem / star / watchlist

    Returns:
        DataFrame，字段对齐 stock_daily schema。
    """
    conn = get_connection()
    try:
        sql = "SELECT * FROM stock_daily WHERE trade_date = ?"
        params: list = [trade_date]
        if board == "main":
            sql += " AND substr(code,1,2) IN ('60','00')"
        elif board == "sh_main":
            sql += " AND substr(code,1,2) = '60'"
        elif board == "sz_main":
            sql += " AND substr(code,1,2) = '00'"
        elif board == "gem":
            sql += " AND substr(code,1,2) = '30'"
        elif board == "star":
            sql += " AND substr(code,1,3) = '688'"
        elif board == "watchlist":
            sql += " AND code IN (SELECT code FROM watchlist_stock)"
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    finally:
        conn.close()


def load_klines(code: str, start: str, end: str) -> pd.DataFrame:
    """加载单只股票 [start, end] 区间的 K 线，按 trade_date 升序。"""
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM stock_daily "
            "WHERE code = ? AND trade_date >= ? AND trade_date <= ? "
            "ORDER BY trade_date ASC",
            conn,
            params=[code, start, end],
        )
        return df
    finally:
        conn.close()


def load_klines_batch(codes: Iterable[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """批量加载多只股票 K 线，返回 {code: DataFrame}。"""
    codes = list(codes)
    if not codes:
        return {}
    placeholders = ",".join("?" * len(codes))
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            f"SELECT * FROM stock_daily "
            f"WHERE code IN ({placeholders}) AND trade_date >= ? AND trade_date <= ? "
            f"ORDER BY code, trade_date ASC",
            conn,
            params=[*codes, start, end],
        )
    finally:
        conn.close()
    return {code: g for code, g in df.groupby("code")}


def load_prev_close_map(trade_date: str) -> dict[str, float]:
    """返回 {code: prev_close}，用于涨停/跌停判断。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code, prev_close FROM stock_daily WHERE trade_date = ? AND prev_close IS NOT NULL",
            (trade_date,),
        ).fetchall()
        return {r["code"]: float(r["prev_close"]) for r in rows}
    finally:
        conn.close()


def load_benchmark(code: str, start: str, end: str) -> pd.DataFrame:
    """加载基准指数日线。若 benchmark_daily 表中数据不全，从 akshare 拉取并缓存。

    返回 DataFrame: trade_date, close（升序）。
    """
    _maybe_fetch_benchmark_from_akshare(code, start, end)
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT trade_date, close FROM benchmark_daily "
            "WHERE code = ? AND trade_date >= ? AND trade_date <= ? "
            "ORDER BY trade_date ASC",
            conn,
            params=[code, start, end],
        )
        return df
    finally:
        conn.close()


def _maybe_fetch_benchmark_from_akshare(code: str, start: str, end: str) -> None:
    """检查 benchmark_daily 是否已覆盖 [start, end]，不够则从 akshare 拉取。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c, MIN(trade_date) AS mn, MAX(trade_date) AS mx "
            "FROM benchmark_daily WHERE code = ? AND trade_date >= ? AND trade_date <= ?",
            (code, start, end),
        ).fetchone()
        if row and row["c"] and row["mn"] <= start and row["mx"] >= end:
            return
    finally:
        conn.close()

    ak_code = _BENCHMARK_AK_CODE.get(code)
    if not ak_code:
        logger.warning("Unknown benchmark code: %s", code)
        return

    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol=ak_code)
        if df is None or df.empty:
            return
        # akshare 返回字段：date, open, high, low, close, volume
        df = df.rename(columns={"date": "trade_date"})
        df["trade_date"] = df["trade_date"].astype(str).str[:10]
        df = df[["trade_date", "close"]].copy()
        df["code"] = code
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]

        conn = get_connection()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO benchmark_daily (code, trade_date, close) VALUES (?, ?, ?)",
                [(code, r["trade_date"], float(r["close"])) for _, r in df.iterrows()],
            )
            conn.commit()
            logger.info("benchmark_daily %s cached %d rows", code, len(df))
        finally:
            conn.close()
    except Exception:
        logger.warning("Fetch benchmark %s from akshare failed", code, exc_info=True)


def check_coverage(universe: str = "main") -> dict:
    """数据深度检查：返回交易日总数、股票池规模、日期范围。"""
    conn = get_connection()
    try:
        sql = (
            "SELECT COUNT(DISTINCT trade_date) AS n_days, "
            "COUNT(DISTINCT code) AS n_codes, "
            "MIN(trade_date) AS min_date, MAX(trade_date) AS max_date "
            "FROM stock_daily"
        )
        params: list = []
        if universe == "main":
            sql += " WHERE substr(code,1,2) IN ('60','00')"
        row = conn.execute(sql, params).fetchone()
        return {
            "n_days": int(row["n_days"] or 0),
            "n_codes": int(row["n_codes"] or 0),
            "min_date": row["min_date"],
            "max_date": row["max_date"],
            "universe": universe,
            "sufficient": int(row["n_days"] or 0) >= 20,
        }
    finally:
        conn.close()
