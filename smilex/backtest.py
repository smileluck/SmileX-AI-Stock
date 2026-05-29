import backtrader as bt
import pandas as pd
from smilex.config import INITIAL_CAPITAL, MA_SHORT_PERIOD, MA_LONG_PERIOD


class MAStrategy(bt.Strategy):
    params = (
        ("short_period", MA_SHORT_PERIOD),
        ("long_period", MA_LONG_PERIOD),
    )

    def __init__(self):
        self.ma_short = bt.indicators.SMA(self.data.close, period=self.p.short_period)
        self.ma_long = bt.indicators.SMA(self.data.close, period=self.p.long_period)
        self.crossover = bt.indicators.CrossOver(self.ma_short, self.ma_long)
        self.trades: list[dict] = []

    def next(self):
        if self.crossover > 0:
            if not self.position:
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
                    self.trades.append({
                        "type": "BUY", "date": self.data.datetime.date(0),
                        "price": self.data.close[0], "size": size,
                    })
        elif self.crossover < 0:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


def run(df: pd.DataFrame, short_period: int = MA_SHORT_PERIOD,
        long_period: int = MA_LONG_PERIOD,
        cash: float = INITIAL_CAPITAL) -> dict:
    """运行回测并返回绩效报告"""
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

    data = bt.feeds.PandasData(
        dataview=df,
        open="open", high="high", low="low", close="close", volume="volume",
    )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(MAStrategy, short_period=short_period, long_period=long_period)
    cerebro.adddata(data)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.00025)

    start_value = cerebro.broker.getvalue()
    strat = cerebro.run()[0]
    end_value = cerebro.broker.getvalue()
    trades = strat.trades

    total_return = (end_value - start_value) / start_value
    trading_days = len(df)
    annual_return = (1 + total_return) ** (252 / max(trading_days, 1)) - 1 if trading_days > 0 else 0

    equity_curve = _build_equity_curve(df, trades, cash)
    max_dd = _calc_max_drawdown(equity_curve)
    win_rate = _calc_win_rate(trades)

    return {
        "total_return": round(total_return * 100, 2),
        "annual_return": round(annual_return * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "win_rate": round(win_rate * 100, 2),
        "start_value": round(start_value, 2),
        "end_value": round(end_value, 2),
        "trade_count": len(trades) // 2,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _build_equity_curve(df: pd.DataFrame, trades: list[dict], cash: float) -> list[float]:
    running_value = cash
    position_size = 0
    curve = []
    for i in range(len(df)):
        row = df.iloc[i]
        for t in trades:
            if str(t["date"]) == str(row.name.date()):
                if t["type"] == "BUY":
                    position_size = t["size"]
                    running_value -= t["price"] * t["size"] * 1.00025
                elif t["type"] == "SELL":
                    running_value += t["price"] * t["size"] * 0.99975
                    position_size = 0
        curve.append(running_value + position_size * row["close"])
    return curve


def _calc_max_drawdown(curve: list[float]) -> float:
    if not curve:
        return 0.0
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)
    return max_dd


def _calc_win_rate(trades: list[dict]) -> float:
    wins = []
    for i in range(0, len(trades) - 1, 2):
        if i + 1 < len(trades):
            profit = (trades[i + 1]["price"] - trades[i]["price"]) * trades[i]["size"]
            wins.append(profit > 0)
    return sum(wins) / len(wins) if wins else 0.0
