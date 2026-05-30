import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class TrendFollowingParams(StrategyParams):
    short_period: int = 5
    long_period: int = 20
    adx_period: int = 14
    adx_threshold: float = 20.0
    volume_ratio_min: float = 1.5
    rsi_lower: float = 50.0
    rsi_upper: float = 70.0


class TrendFollowingBT(bt.Strategy):
    params = (
        ("short_period", 5),
        ("long_period", 20),
        ("adx_period", 14),
        ("adx_threshold", 20.0),
    )

    def __init__(self):
        self.ma_short = bt.indicators.SMA(self.data.close, period=self.p.short_period)
        self.ma_long = bt.indicators.SMA(self.data.close, period=self.p.long_period)
        self.crossover = bt.indicators.CrossOver(self.ma_short, self.ma_long)
        self.adx = bt.indicators.ADX(self.data, period=self.p.adx_period)
        self.trades: list[dict] = []

    def next(self):
        if self.crossover > 0 and self.adx[0] > self.p.adx_threshold:
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


class TrendFollowingStrategy(BaseStrategy):

    def __init__(self, params: TrendFollowingParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="trend_following",
            display_name="趋势跟踪",
            description="均线多头排列 + ADX 趋势确认，适合牛市行情",
            category="趋势",
        )

    @property
    def _params_cls(self) -> type:
        return TrendFollowingParams

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "rsi", "bollinger", "volume_ratio", "adx"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        ma5 = latest.get("ma5")
        ma10 = latest.get("ma10")
        ma20 = latest.get("ma20")
        ma60 = latest.get("ma60")
        if all(pd.notna(v) for v in [ma5, ma10, ma20, ma60]):
            if ma5 > ma10 > ma20 > ma60:
                score += 25
                reasons.append("均线多头排列")

        dif = latest.get("macd_dif")
        dea = latest.get("macd_dea")
        if all(pd.notna(v) for v in [dif, dea]):
            if dif > dea:
                score += 15
                reasons.append("MACD金叉")
            elif pd.notna(dif) and pd.notna(dea) and abs(dif - dea) / max(abs(dea), 0.01) < 0.05:
                score += 8
                reasons.append("MACD即将金叉")

        adx_val = latest.get("adx")
        if pd.notna(adx_val) and adx_val > p.adx_threshold:
            score += 15
            reasons.append(f"ADX趋势确认({adx_val:.0f})")

        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio) and vol_ratio > p.volume_ratio_min:
            score += 15
            reasons.append(f"放量(量比{vol_ratio:.1f})")

        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val):
            if p.rsi_lower < rsi_val < p.rsi_upper:
                score += 15
                reasons.append(f"RSI适中({rsi_val:.0f})")
            elif rsi_val < p.rsi_lower:
                score += 5
                reasons.append(f"RSI偏低({rsi_val:.0f})")

        close = latest.get("close", 0)
        boll_mid = latest.get("boll_mid")
        if pd.notna(boll_mid) and close > boll_mid:
            score += 15
            reasons.append("站上布林中轨")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params
        df[f"ma{p.short_period}"] = df["close"].rolling(window=p.short_period).mean()
        df[f"ma{p.long_period}"] = df["close"].rolling(window=p.long_period).mean()

        golden = (
            (df[f"ma{p.short_period}"] > df[f"ma{p.long_period}"]) &
            (df[f"ma{p.short_period}"].shift(1) <= df[f"ma{p.long_period}"].shift(1))
        )
        death = (
            (df[f"ma{p.short_period}"] < df[f"ma{p.long_period}"]) &
            (df[f"ma{p.short_period}"].shift(1) >= df[f"ma{p.long_period}"].shift(1))
        )

        df["signal"] = 0
        df.loc[golden, "signal"] = 1
        df.loc[death, "signal"] = -1
        df["position"] = np.where(df[f"ma{p.short_period}"] > df[f"ma{p.long_period}"], 1, 0)
        return df

    @property
    def backtest_class(self) -> type:
        return TrendFollowingBT
