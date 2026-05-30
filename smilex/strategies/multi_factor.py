import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class MultiFactorParams(StrategyParams):
    lookback_period: int = 20
    volatility_period: int = 20
    trend_weight: float = 0.25
    momentum_weight: float = 0.20
    volatility_weight: float = 0.15
    volume_weight: float = 0.15
    technical_weight: float = 0.15
    adx_weight: float = 0.10
    buy_threshold: float = 60.0
    sell_threshold: float = 30.0


class MultiFactorBT(bt.Strategy):
    params = (
        ("short_period", 5),
        ("long_period", 20),
        ("lookback_period", 20),
    )

    def __init__(self):
        self.ma_short = bt.indicators.SMA(self.data.close, period=self.p.short_period)
        self.ma_long = bt.indicators.SMA(self.data.close, period=self.p.long_period)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.macd = bt.indicators.MACD(self.data.close)
        self.trades: list[dict] = []

    def next(self):
        trend_score = 50 if self.ma_short[0] > self.ma_long[0] else 0
        mom_score = min(max((self.data.close[0] / self.data.close[-self.p.lookback_period] - 1) * 500, 0), 100)
        tech_score = 50 if self.macd.lines.macd[0] > self.macd.lines.signal[0] else 0
        tech_score += min(max((70 - abs(self.rsi[0] - 50)) / 20 * 50, 0), 50)

        total = trend_score * 0.25 + mom_score * 0.20 + tech_score * 0.15 + 50 * 0.15 + 50 * 0.15 + 50 * 0.10

        if total > 60 and not self.position:
            size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
            if size > 0:
                self.buy(size=size)
                self.trades.append({
                    "type": "BUY", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": size,
                })
        elif total < 30 and self.position:
            self.close()
            self.trades.append({
                "type": "SELL", "date": self.data.datetime.date(0),
                "price": self.data.close[0], "size": self.position.size,
            })


class MultiFactorStrategy(BaseStrategy):

    def __init__(self, params: MultiFactorParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="multi_factor",
            display_name="多因子打分",
            description="趋势+动量+波动+量能+技术+ADX六因子加权评分",
            category="多因子",
        )

    @property
    def _params_cls(self) -> type:
        return MultiFactorParams

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "rsi", "volume_ratio", "adx", "price_returns", "volume_momentum"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        scores: dict[str, float] = {}
        reasons: list[str] = []
        p = self.params

        # Trend factor (0-100)
        ma5 = latest.get("ma5")
        ma10 = latest.get("ma10")
        ma20 = latest.get("ma20")
        ma60 = latest.get("ma60")
        trend_cnt = 0
        if pd.notna(ma5) and pd.notna(ma10) and ma5 > ma10:
            trend_cnt += 1
        if pd.notna(ma10) and pd.notna(ma20) and ma10 > ma20:
            trend_cnt += 1
        if pd.notna(ma20) and pd.notna(ma60) and ma20 > ma60:
            trend_cnt += 1
        scores["trend"] = trend_cnt / 3 * 100
        if trend_cnt == 3:
            reasons.append("趋势满分")

        # Momentum factor (0-100)
        ret_col = f"return_{p.lookback_period}d"
        ret_val = latest.get(ret_col, 0)
        if pd.notna(ret_val):
            scores["momentum"] = min(max(ret_val / 0.1 * 100, 0), 100)
            if ret_val > 0.05:
                reasons.append(f"动量强({ret_val*100:.1f}%)")

        # Volatility factor (0-100, inverse)
        close = latest.get("close", 0)
        scores["volatility"] = 50  # Default, full calc needs more data

        # Volume factor (0-100)
        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio):
            scores["volume"] = min(vol_ratio / 3 * 100, 100)
            if vol_ratio > 1.5:
                reasons.append(f"量能强({vol_ratio:.1f})")

        # Technical factor (MACD + RSI)
        tech_score = 0
        dif = latest.get("macd_dif")
        dea = latest.get("macd_dea")
        if pd.notna(dif) and pd.notna(dea) and dif > dea:
            tech_score += 50
        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val) and 40 < rsi_val < 70:
            tech_score += 50
        scores["technical"] = tech_score
        if tech_score >= 75:
            reasons.append("技术面优秀")

        # ADX factor (0-100)
        adx_val = latest.get("adx")
        if pd.notna(adx_val):
            scores["adx"] = min(adx_val / 50 * 100, 100)
            if adx_val > 25:
                reasons.append(f"趋势强(ADX={adx_val:.0f})")

        # Weighted sum
        weights = {
            "trend": p.trend_weight,
            "momentum": p.momentum_weight,
            "volatility": p.volatility_weight,
            "volume": p.volume_weight,
            "technical": p.technical_weight,
            "adx": p.adx_weight,
        }
        total = sum(scores.get(k, 0) * w for k, w in weights.items())
        total = round(total)

        if not reasons:
            reasons.append(f"综合得分{total}")

        return int(total), reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params

        ret_col = f"return_{p.lookback_period}d"
        if ret_col not in df.columns:
            df[ret_col] = df["close"].pct_change(periods=p.lookback_period)

        df["factor_score"] = 50.0  # Simplified inline scoring
        df.loc[df[ret_col] > 0.05, "factor_score"] += 20
        df.loc[df["close"] > df.get("ma20", df["close"]), "factor_score"] += 15

        dif = df.get("macd_dif")
        dea = df.get("macd_dea")
        if dif is not None and dea is not None:
            df.loc[dif > dea, "factor_score"] += 15

        buy_mask = df["factor_score"] > p.buy_threshold
        sell_mask = df["factor_score"] < p.sell_threshold

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
        return MultiFactorBT
