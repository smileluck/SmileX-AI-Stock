import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class BreakoutParams(StrategyParams):
    entry_period: int = 20
    exit_period: int = 10
    volume_ratio_min: float = 2.0
    adx_threshold: float = 25.0


class BreakoutBT(bt.Strategy):
    params = (
        ("entry_period", 20),
        ("exit_period", 10),
    )

    def __init__(self):
        self.high_channel = bt.indicators.Highest(self.data.high, period=self.p.entry_period)
        self.low_channel = bt.indicators.Lowest(self.data.low, period=self.p.exit_period)
        self.trades: list[dict] = []

    def next(self):
        if self.data.close[0] > self.high_channel[-1]:
            if not self.position:
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
                    self.trades.append({
                        "type": "BUY", "date": self.data.datetime.date(0),
                        "price": self.data.close[0], "size": size,
                    })
        elif self.data.close[0] < self.low_channel[-1]:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


class BreakoutStrategy(BaseStrategy):

    def __init__(self, params: BreakoutParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="breakout",
            display_name="突破策略",
            description="唐奇安通道突破，海龟交易法则核心逻辑",
            category="突破",
        )

    @property
    def _params_cls(self) -> type:
        return BreakoutParams

    @property
    def required_indicators(self) -> list[str]:
        return ["donchian", "ma", "rsi", "volume_ratio", "adx"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        close = latest.get("close", 0)
        donchian_upper = latest.get("donchian_upper")
        if pd.notna(donchian_upper) and close >= donchian_upper:
            score += 30
            reasons.append(f"突破{p.entry_period}日新高")
        elif pd.notna(donchian_upper) and close > donchian_upper * 0.97:
            score += 10
            reasons.append("接近突破位")

        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio) and vol_ratio > p.volume_ratio_min:
            score += 25
            reasons.append(f"放量突破(量比{vol_ratio:.1f})")

        ma20 = latest.get("ma20")
        ma20_prev = latest.get("ma20")
        if pd.notna(ma20) and ma20 > 0:
            score += 15
            reasons.append("MA20上方")

        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val) and rsi_val < 80:
            score += 15
            reasons.append(f"RSI未超买({rsi_val:.0f})")

        adx_val = latest.get("adx")
        if pd.notna(adx_val) and adx_val > p.adx_threshold:
            score += 15
            reasons.append(f"趋势强劲(ADX={adx_val:.0f})")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params

        if "donchian_upper" not in df.columns:
            df["donchian_upper"] = df["high"].rolling(window=p.entry_period).max().shift(1)
        if "donchian_lower" not in df.columns:
            df["donchian_lower"] = df["low"].rolling(window=p.exit_period).min().shift(1)

        buy_mask = df["close"] > df["donchian_upper"]
        sell_mask = df["close"] < df["donchian_lower"]

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
        return BreakoutBT
