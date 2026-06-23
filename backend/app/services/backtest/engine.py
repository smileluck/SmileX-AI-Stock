"""回测撮合引擎。

主循环：每个交易日 T，
  1) 用 T-1 数据生成信号（避免未来函数）
  2) 处理止损止盈（用 T 收盘价）
  3) 调仓：卖出不在信号的持仓（满足 T+1）
  4) 买入：新信号等权分配，跳过一字涨停/ST
  5) 盘后估值

A股规则：T+1、最小 100 股、佣金双边万2.5最低5元、印花税卖方千1。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

import pandas as pd

from app.services.backtest import data_loader, strategies

logger = logging.getLogger(__name__)


# 默认参数
COMMISSION_BPS = 2.5      # 万分之2.5
STAMP_DUTY_BPS = 1.0      # 千分之1（卖方）
MIN_COMMISSION = 5.0      # 单笔最低佣金


@dataclass
class BacktestParams:
    strategy_type: str = "midday"
    universe: str = "main"
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 100000.0
    top_n: int = 5
    rebalance: str = "daily"            # daily / weekly
    stop_loss: float = -0.07
    take_profit: float = 0.15
    commission_bps: float = COMMISSION_BPS
    stamp_duty_bps: float = STAMP_DUTY_BPS
    benchmark: str = "hs300"
    custom_factors: dict[str, float] = field(default_factory=dict)
    name: str = ""

    def to_json_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class Position:
    code: str
    name: str
    shares: int
    entry_price: float
    entry_date: str


@dataclass
class Trade:
    trade_date: str
    code: str
    name: str
    side: str               # buy / sell
    price: float
    shares: int
    amount: float
    cost: float
    reason: str


def _calc_commission(amount: float, bps: float) -> float:
    """单边佣金：max(amount * bps/10000, MIN_COMMISSION)。"""
    return max(amount * bps / 10000.0, MIN_COMMISSION)


def _calc_stamp_duty(amount: float, bps: float) -> float:
    return amount * bps / 1000.0


def _is_one_word_limit_up(open_price: float | None, prev_close: float | None,
                          board: str | None = None) -> bool:
    """一字板判断：开盘价已触及涨停价（涨幅 ≥ 9.9% / 创业板科创板 19.9% / ST 4.9%）。"""
    if open_price is None or prev_close is None or prev_close <= 0:
        return False
    threshold = 0.099
    if board == "创业板" or board == "科创板":
        threshold = 0.199
    return open_price >= prev_close * (1 + threshold)


def _calc_buy_shares(budget: float, price: float) -> int:
    """等权分配下，单只股票可买股数（向下取整到 100 股）。"""
    if price <= 0:
        return 0
    raw = int(budget / price)
    return (raw // 100) * 100


def run_backtest(params: BacktestParams) -> dict:
    """执行回测，返回完整结果 dict（含 metrics/equity/trades 摘要）。"""
    dates = data_loader.load_trade_dates(params.start_date, params.end_date)
    if len(dates) < 20:
        raise ValueError(
            f"回测区间不足 20 个交易日（实际 {len(dates)} 天），请先补数。"
            f"使用 python -m app.services.backfill_daily --universe all_market --days 365"
        )

    # 预加载基准
    benchmark_df = data_loader.load_benchmark(params.benchmark, params.start_date, dates[-1])
    benchmark_close = (
        dict(zip(benchmark_df["trade_date"].astype(str), benchmark_df["close"].astype(float)))
        if not benchmark_df.empty else {}
    )
    bench_first = next((benchmark_close.get(d) for d in dates if benchmark_close.get(d)), None)

    cash = float(params.initial_capital)
    positions: dict[str, Position] = {}
    trades: list[Trade] = []
    equity_curve: list[dict] = []

    for i, today in enumerate(dates):
        # 决策日：T-1（首个交易日无法决策，跳过买卖）
        decision_day = dates[i - 1] if i > 0 else None

        # 加载今日 panel（用于撮合：open/high/low/close/prev_close）
        today_panel = data_loader.load_daily_panel(today, board=params.universe)
        today_panel = _index_panel_by_code(today_panel)

        # ---- 1) 生成信号（T-1）----
        if decision_day is None:
            signal_codes: list[str] = []
        elif params.rebalance == "weekly" and i % 5 != 0:
            signal_codes = list(positions.keys())  # 非调仓日，保持持仓
        else:
            try:
                signals = strategies.generate_signals(
                    params.strategy_type, decision_day,
                    board=params.universe, top_n=max(params.top_n * 4, 20),
                    custom_factors=params.custom_factors,
                )
                signal_codes = [s["code"] for s in signals]
            except Exception:
                logger.warning("signal gen failed for %s", decision_day, exc_info=True)
                signal_codes = []

        # ---- 2) 止损止盈（用今日收盘价）----
        for code in list(positions.keys()):
            pos = positions[code]
            row = today_panel.get(code)
            if row is None or row.get("close") is None:
                continue  # 停牌
            ret = (float(row["close"]) - pos.entry_price) / pos.entry_price
            if ret <= params.stop_loss:
                cash = _do_sell(trades, positions, code, row, today, cash, params,
                                reason="stop_loss")
            elif ret >= params.take_profit:
                cash = _do_sell(trades, positions, code, row, today, cash, params,
                                reason="take_profit")

        # ---- 3) 调仓卖出：不在信号且满足 T+1 ----
        for code in list(positions.keys()):
            if code in signal_codes:
                continue
            pos = positions[code]
            if pos.entry_date >= today:
                continue  # T+1
            row = today_panel.get(code)
            if row is None:
                continue
            cash = _do_sell(trades, positions, code, row, today, cash, params,
                            reason="rebalance")

        # ---- 4) 买入：等权分配 ----
        n_slots = params.top_n - len(positions)
        if n_slots > 0 and signal_codes and cash > 0:
            budget_per = cash / n_slots if n_slots > 0 else 0
            bought = 0
            for code in signal_codes:
                if bought >= n_slots:
                    break
                if code in positions:
                    continue
                row = today_panel.get(code)
                if row is None:
                    continue
                open_price = row.get("open")
                prev_close = row.get("prev_close")
                name = row.get("name") or code
                board = row.get("board")
                if _is_one_word_limit_up(open_price, prev_close, board):
                    continue  # 一字板买不进
                if open_price is None or open_price <= 0:
                    continue
                shares = _calc_buy_shares(budget_per, float(open_price))
                if shares <= 0:
                    continue
                amount = shares * float(open_price)
                commission = _calc_commission(amount, params.commission_bps)
                if amount + commission > cash:
                    shares = _calc_buy_shares(cash - commission, float(open_price))
                    if shares <= 0:
                        continue
                    amount = shares * float(open_price)
                    commission = _calc_commission(amount, params.commission_bps)
                cash -= (amount + commission)
                positions[code] = Position(
                    code=code, name=name, shares=shares,
                    entry_price=float(open_price), entry_date=today,
                )
                trades.append(Trade(
                    trade_date=today, code=code, name=name, side="buy",
                    price=float(open_price), shares=shares, amount=amount,
                    cost=commission, reason="signal",
                ))
                bought += 1

        # ---- 5) 盘后估值 ----
        position_value = 0.0
        for pos in positions.values():
            row = today_panel.get(pos.code)
            close = row.get("close") if row else None
            if close is not None and close > 0:
                position_value += pos.shares * float(close)
            else:
                # 停牌：用 entry_price 估值
                position_value += pos.shares * pos.entry_price
        equity = cash + position_value

        # 基准净值（归一化到首日=1）
        bench_val = None
        if bench_first and benchmark_close.get(today):
            bench_val = benchmark_close[today] / bench_first

        # 回撤（运行中）
        if equity_curve:
            peak = max(e["equity"] for e in equity_curve)
            drawdown = (equity - peak) / peak if peak > 0 else 0
        else:
            drawdown = 0.0

        equity_curve.append({
            "trade_date": today,
            "equity": equity,
            "cash": cash,
            "position_value": position_value,
            "benchmark": bench_val,
            "drawdown": drawdown,
        })

    # 最大回撤（最终计算）
    equities = [e["equity"] for e in equity_curve]
    if equities:
        cummax = pd.Series(equities).cummax()
        drawdowns = (pd.Series(equities) - cummax) / cummax
        max_drawdown = float(drawdowns.min())
    else:
        max_drawdown = 0.0

    return {
        "params": params.to_json_dict(),
        "equity_curve": equity_curve,
        "trades": [t.__dict__ for t in trades],
        "max_drawdown": max_drawdown,
        "n_days": len(dates),
    }


def _index_panel_by_code(panel: pd.DataFrame) -> dict[str, dict]:
    """将 panel DataFrame 转为 {code: row_dict}，便于 O(1) 查询。"""
    out: dict[str, dict] = {}
    for _, row in panel.iterrows():
        code = str(row.get("code") or "")
        if not code:
            continue
        out[code] = {
            "code": code,
            "name": row.get("name"),
            "board": row.get("board"),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "prev_close": row.get("prev_close"),
        }
    return out


def _do_sell(trades: list[Trade], positions: dict[str, Position],
             code: str, row: dict, today: str, cash: float,
             params: BacktestParams, *, reason: str) -> float:
    """卖出 pos 并返回新的 cash 余额。"""
    pos = positions.get(code)
    if not pos:
        return cash
    close = row.get("close")
    if close is None or close <= 0:
        return cash
    amount = pos.shares * float(close)
    commission = _calc_commission(amount, params.commission_bps)
    stamp = _calc_stamp_duty(amount, params.stamp_duty_bps)
    trades.append(Trade(
        trade_date=today, code=code, name=pos.name, side="sell",
        price=float(close), shares=pos.shares, amount=amount,
        cost=commission + stamp, reason=reason,
    ))
    del positions[code]
    return cash + amount - commission - stamp
