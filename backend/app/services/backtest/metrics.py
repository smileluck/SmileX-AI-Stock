"""回测指标计算：年化收益、最大回撤、夏普、卡玛、胜率、盈亏比、超额收益。"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def compute(equity_curve: list[dict], trades: list[dict],
            initial_capital: float, n_days: int) -> dict:
    """计算 6 个核心指标。

    Args:
        equity_curve: 引擎返回的曲线 list
        trades: 引擎返回的 trades list
        initial_capital: 初始资金
        n_days: 交易日总数
    """
    if not equity_curve:
        return _empty_metrics()

    eq = pd.DataFrame(equity_curve)
    eq = eq.sort_values("trade_date").reset_index(drop=True)
    equity = eq["equity"].astype(float)

    total_return = float(equity.iloc[-1] / initial_capital - 1)
    annual_return = _annualized_return(total_return, n_days)

    # 最大回撤（已在 engine 算过 max_drawdown，这里重算以备调用方独立使用）
    cummax = equity.cummax()
    drawdowns = (equity - cummax) / cummax
    max_drawdown = float(drawdowns.min())

    # 夏普（日收益率 × sqrt(252) / std）
    daily_ret = equity.pct_change().dropna()
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std() * math.sqrt(252))
    else:
        sharpe = 0.0

    # 卡玛
    calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0.0

    # 基准超额收益（基准净值在 equity_curve['benchmark']）
    bench_total_return = None
    excess_return = None
    if "benchmark" in eq.columns and eq["benchmark"].notna().any():
        bench_series = eq["benchmark"].dropna()
        if len(bench_series) >= 2:
            bench_total_return = float(bench_series.iloc[-1] - bench_series.iloc[0])
            excess_return = total_return - bench_total_return

    # 胜率/盈亏比（基于卖出 trade）
    sell_trades = [t for t in trades if t.get("side") == "sell"]
    closed_pnl = _match_trade_pnl(trades)
    if closed_pnl:
        wins = [p for p in closed_pnl if p > 0]
        losses = [p for p in closed_pnl if p < 0]
        win_rate = len(wins) / len(closed_pnl)
        if wins and losses:
            avg_win = sum(wins) / len(wins)
            avg_loss = abs(sum(losses) / len(losses))
            profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
        else:
            profit_loss_ratio = 0.0
    else:
        win_rate = 0.0
        profit_loss_ratio = 0.0

    return {
        "total_return": round(total_return * 100, 2),              # 百分数
        "annual_return": round(annual_return * 100, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "sharpe": round(sharpe, 3),
        "calmar": round(calmar, 3),
        "win_rate": round(win_rate * 100, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 3),
        "n_trades": len(trades),
        "n_sells": len(sell_trades),
        "benchmark_total_return": (
            round(bench_total_return * 100, 2) if bench_total_return is not None else None
        ),
        "excess_return": (
            round(excess_return * 100, 2) if excess_return is not None else None
        ),
        "n_days": n_days,
    }


def _annualized_return(total_return: float, n_days: int) -> float:
    if n_days <= 0:
        return 0.0
    if total_return <= -1.0:
        return -1.0
    return (1 + total_return) ** (252 / n_days) - 1


def _match_trade_pnl(trades: list[dict]) -> list[float]:
    """简单 FIFO 匹配 buy/sell，计算每笔卖出对应的盈亏。"""
    holdings: dict[str, list[tuple[float, int]]] = {}  # code -> [(price, shares)]
    pnls: list[float] = []
    for t in trades:
        code = t.get("code")
        side = t.get("side")
        if not code or not side:
            continue
        if side == "buy":
            holdings.setdefault(code, []).append((float(t["price"]), int(t["shares"])))
        elif side == "sell":
            queue = holdings.get(code, [])
            remaining = int(t["shares"])
            sell_price = float(t["price"])
            while remaining > 0 and queue:
                buy_price, buy_shares = queue[0]
                matched = min(remaining, buy_shares)
                pnls.append((sell_price - buy_price) * matched)
                buy_shares -= matched
                remaining -= matched
                if buy_shares == 0:
                    queue.pop(0)
                else:
                    queue[0] = (buy_price, buy_shares)
    return pnls


def _empty_metrics() -> dict:
    return {
        "total_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
        "calmar": 0.0,
        "win_rate": 0.0,
        "profit_loss_ratio": 0.0,
        "n_trades": 0,
        "n_sells": 0,
        "benchmark_total_return": None,
        "excess_return": None,
        "n_days": 0,
    }
