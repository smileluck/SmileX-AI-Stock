import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class MeanReversionParams(StrategyParams):
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    kdj_oversold: float = 20.0
    volume_ratio_min: float = 1.0


class MeanReversionBT(bt.Strategy):
    params = (
        ("rsi_period", 14),
        ("rsi_oversold", 30.0),
        ("rsi_overbought", 70.0),
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.boll = bt.indicators.BollingerBands(self.data.close, period=20, devfactor=2.0)
        self.trades: list[dict] = []

    def next(self):
        if self.rsi[0] > self.p.rsi_oversold and self.rsi[-1] <= self.p.rsi_oversold:
            if self.data.close[0] > self.boll.lines.bot[0]:
                if not self.position:
                    size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                    if size > 0:
                        self.buy(size=size)
                        self.trades.append({
                            "type": "BUY", "date": self.data.datetime.date(0),
                            "price": self.data.close[0], "size": size,
                        })
        elif self.rsi[0] > self.p.rsi_overbought:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


class MeanReversionStrategy(BaseStrategy):

    def __init__(self, params: MeanReversionParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="mean_reversion",
            display_name="均值回归",
            description="RSI超卖 + 布林下轨反弹，适合震荡市抄底",
            category="均值回归",
        )

    @property
    def _params_cls(self) -> type:
        return MeanReversionParams

    @property
    def required_indicators(self) -> list[str]:
        return ["rsi", "bollinger", "kdj", "ma", "macd", "volume_ratio"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val):
            if rsi_val < p.rsi_oversold:
                score += 25
                reasons.append(f"RSI超卖({rsi_val:.0f})")
            elif rsi_val < 40:
                score += 10
                reasons.append(f"RSI偏低({rsi_val:.0f})")

        close = latest.get("close", 0)
        boll_lower = latest.get("boll_lower")
        if pd.notna(boll_lower) and close < boll_lower:
            score += 25
            reasons.append("跌破布林下轨")

        kdj_k = latest.get("kdj_k")
        if pd.notna(kdj_k) and kdj_k < p.kdj_oversold:
            score += 15
            reasons.append(f"KDJ超卖(K={kdj_k:.0f})")

        ma60 = latest.get("ma60")
        if pd.notna(ma60) and close > ma60:
            score += 15
            reasons.append("站上MA60(中期趋势向上)")

        macd_hist = latest.get("macd_hist")
        if pd.notna(macd_hist):
            if macd_hist > 0:
                score += 10
                reasons.append("MACD柱转正")
            elif pd.notna(latest.get("macd_hist")) and len(str(latest.get("macd_hist", ""))) > 0:
                pass

        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio) and vol_ratio > p.volume_ratio_min:
            score += 10
            reasons.append(f"量比正常({vol_ratio:.1f})")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params

        rsi_col = f"rsi{p.rsi_period}" if f"rsi{p.rsi_period}" in df.columns else "rsi14"
        boll_lower = "boll_lower" if "boll_lower" in df.columns else None

        buy_mask = pd.Series(False, index=df.index)
        sell_mask = pd.Series(False, index=df.index)

        if rsi_col in df.columns:
            rsi_cross_up = (df[rsi_col] > p.rsi_oversold) & (df[rsi_col].shift(1) <= p.rsi_oversold)
            if boll_lower and boll_lower in df.columns:
                buy_mask = rsi_cross_up & (df["close"] > df[boll_lower])
            else:
                buy_mask = rsi_cross_up

            rsi_over = df[rsi_col] > p.rsi_overbought
            sell_mask = rsi_over

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
        return MeanReversionBT
