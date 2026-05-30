import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class MomentumParams(StrategyParams):
    lookback_period: int = 20
    momentum_threshold: float = 0.05
    volume_momentum_fast: int = 5
    volume_momentum_slow: int = 20
    volume_momentum_min: float = 1.3
    rsi_overbought: float = 80.0
    consecutive_days: int = 3


class MomentumBT(bt.Strategy):
    params = (
        ("lookback_period", 20),
        ("momentum_threshold", 0.05),
        ("rsi_overbought", 80.0),
    )

    def __init__(self):
        self.mom = bt.indicators.ROC(self.data.close, period=self.p.lookback_period)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.trades: list[dict] = []

    def next(self):
        if self.mom[0] / 100 > self.p.momentum_threshold:
            if not self.position:
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
                    self.trades.append({
                        "type": "BUY", "date": self.data.datetime.date(0),
                        "price": self.data.close[0], "size": size,
                    })
        elif self.mom[0] / 100 < 0 or self.rsi[0] > self.p.rsi_overbought:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


class MomentumStrategy(BaseStrategy):

    def __init__(self, params: MomentumParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="momentum",
            display_name="动量策略",
            description="价格动量 + 量能确认，追逐强势股",
            category="动量",
        )

    @property
    def _params_cls(self) -> type:
        return MomentumParams

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "rsi", "volume_ratio", "price_returns", "volume_momentum"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        ret_col = f"return_{p.lookback_period}d"
        ret_val = latest.get(ret_col, 0)
        if pd.notna(ret_val) and ret_val > p.momentum_threshold:
            score += 25
            reasons.append(f"{p.lookback_period}日涨幅{ret_val*100:.1f}%")
        elif pd.notna(ret_val) and ret_val > 0:
            score += 10
            reasons.append(f"{p.lookback_period}日涨幅{ret_val*100:.1f}%")

        vol_mom = latest.get("volume_momentum", 0)
        if pd.notna(vol_mom) and vol_mom > p.volume_momentum_min:
            score += 20
            reasons.append(f"成交量动量{vol_mom:.1f}")

        dif = latest.get("macd_dif")
        if pd.notna(dif) and dif > 0:
            score += 15
            reasons.append("MACD DIF>0")

        ma5 = latest.get("ma5")
        ma20 = latest.get("ma20")
        if pd.notna(ma5) and pd.notna(ma20) and ma5 > ma20:
            score += 15
            reasons.append("MA5>MA20")

        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val):
            if 50 < rsi_val < p.rsi_overbought:
                score += 15
                reasons.append(f"RSI强势({rsi_val:.0f})")
            elif rsi_val >= p.rsi_overbought:
                score += 5
                reasons.append(f"RSI过高({rsi_val:.0f})")

        # Check consecutive up days (need recent data - simplified check)
        close = latest.get("close", 0)
        open_val = latest.get("open", 0)
        if pd.notna(close) and pd.notna(open_val) and close > open_val:
            score += 10
            reasons.append("当日收阳")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params
        ret_col = f"return_{p.lookback_period}d"
        if ret_col not in df.columns:
            df[ret_col] = df["close"].pct_change(periods=p.lookback_period)

        buy_mask = df[ret_col] > p.momentum_threshold
        sell_mask = (df[ret_col] < 0) | (df.get("rsi14", pd.Series(0, index=df.index)) > p.rsi_overbought)

        df["signal"] = 0
        df.loc[buy_mask, "signal"] = 1
        df.loc[sell_mask, "signal"] = -1
        df["position"] = 0
        in_pos = False
        for i in range(len(df)):
            if df.iloc[i]["signal"] == 1 and not in_pos:
                in_pos = True
            elif df.iloc[i]["signal"] == -1 and in_pos:
                in_pos = False
            df.iloc[i, df.columns.get_loc("position")] = 1 if in_pos else 0
        return df

    @property
    def backtest_class(self) -> type:
        return MomentumBT
