import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class SectorRotationParams(StrategyParams):
    lookback_period: int = 20
    top_sectors: int = 3
    min_up_ratio: float = 0.6
    volume_expansion: float = 1.3


class SectorRotationBT(bt.Strategy):
    params = (
        ("lookback_period", 20),
        ("ma_period", 20),
    )

    def __init__(self):
        self.ma = bt.indicators.SMA(self.data.close, period=self.p.ma_period)
        self.roc = bt.indicators.ROC(self.data.close, period=self.p.lookback_period)
        self.trades: list[dict] = []

    def next(self):
        if self.data.close[0] > self.ma[0] and self.roc[0] > 5:
            if not self.position:
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
                    self.trades.append({
                        "type": "BUY", "date": self.data.datetime.date(0),
                        "price": self.data.close[0], "size": size,
                    })
        elif self.roc[0] < 0:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


class SectorRotationStrategy(BaseStrategy):

    def __init__(self, params: SectorRotationParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="sector_rotation",
            display_name="板块轮动",
            description="先选强势板块，再从板块内选个股",
            category="轮动",
        )

    @property
    def _params_cls(self) -> type:
        return SectorRotationParams

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "rsi", "volume_ratio", "price_returns"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        ret_col = f"return_{p.lookback_period}d"
        ret_val = latest.get(ret_col, 0)
        if pd.notna(ret_val):
            if ret_val > 0.1:
                score += 25
                reasons.append(f"强势板块({ret_val*100:.1f}%)")
            elif ret_val > 0.05:
                score += 15
                reasons.append(f"板块上涨({ret_val*100:.1f}%)")

        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio) and vol_ratio > p.volume_expansion:
            score += 20
            reasons.append(f"板块放量({vol_ratio:.1f})")

        # Up ratio proxy (use change_pct as indicator)
        change_pct = latest.get("change_pct", 0)
        if pd.notna(change_pct) and change_pct > 2:
            score += 20
            reasons.append("板块内多数上涨")
        elif pd.notna(change_pct) and change_pct > 0:
            score += 10

        # Volume expansion
        score += 15
        reasons.append("量能放大")

        ma5 = latest.get("ma5")
        ma10 = latest.get("ma10")
        ma20 = latest.get("ma20")
        if pd.notna(ma5) and pd.notna(ma20) and ma5 > ma20:
            score += 10
            reasons.append("板块MA多头")

        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val) and 50 < rsi_val < 80:
            score += 10
            reasons.append(f"板块RSI适中({rsi_val:.0f})")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params

        ret_col = f"return_{p.lookback_period}d"
        if ret_col not in df.columns:
            df[ret_col] = df["close"].pct_change(periods=p.lookback_period)

        buy_mask = df[ret_col] > 0.05
        sell_mask = df[ret_col] < 0

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
        return SectorRotationBT
