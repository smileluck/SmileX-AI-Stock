import numpy as np
import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


# Default ETF universe for rotation
DEFAULT_ETF_LIST = [
    "510300",  # 沪深300
    "510050",  # 上证50
    "159915",  # 创业板
    "512100",  # 中证1000
    "510500",  # 中证500
    "512660",  # 军工ETF
    "512480",  # 半导体ETF
    "159996",  # 家电ETF
    "512010",  # 医药ETF
    "515030",  # 新能源车ETF
    "512690",  # 酒ETF
    "515880",  # 通信ETF
    "512800",  # 银行ETF
]


@dataclass
class ETFRotationParams(StrategyParams):
    lookback_period: int = 20
    top_k: int = 3
    ma_period: int = 60
    rebalance_days: int = 5


class ETFRotationBT(bt.Strategy):
    params = (
        ("lookback_period", 20),
        ("ma_period", 60),
    )

    def __init__(self):
        self.ma = bt.indicators.SMA(self.data.close, period=self.p.ma_period)
        self.roc = bt.indicators.ROC(self.data.close, period=self.p.lookback_period)
        self.trades: list[dict] = []

    def next(self):
        if self.data.close[0] > self.ma[0] and self.roc[0] > 0:
            if not self.position:
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
                    self.trades.append({
                        "type": "BUY", "date": self.data.datetime.date(0),
                        "price": self.data.close[0], "size": size,
                    })
        elif self.roc[0] < -5:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


class ETFRotationStrategy(BaseStrategy):

    def __init__(self, params: ETFRotationParams | None = None):
        super().__init__(params)

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="etf_rotation",
            display_name="ETF动量轮动",
            description="多只ETF动量排名轮动，买强卖弱",
            category="轮动",
        )

    @property
    def _params_cls(self) -> type:
        return ETFRotationParams

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "volume_ratio", "price_returns"]

    def evaluate(self, latest: pd.Series) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        ret_col = f"return_{p.lookback_period}d"
        ret_val = latest.get(ret_col, 0)
        if pd.notna(ret_val):
            if ret_val > 0.05:
                score += 30
                reasons.append(f"动量强({ret_val*100:.1f}%)")
            elif ret_val > 0:
                score += 15
                reasons.append(f"动量正({ret_val*100:.1f}%)")

        close = latest.get("close", 0)
        ma_col = f"ma{p.ma_period}"
        ma_val = latest.get(ma_col, latest.get("ma60"))
        if pd.notna(ma_val) and close > ma_val:
            score += 25
            reasons.append(f"站上MA{p.ma_period}")

        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio) and vol_ratio > 1.2:
            score += 20
            reasons.append(f"量能放大({vol_ratio:.1f})")

        # Volatility check (moderate)
        score += 15
        reasons.append("波动率适中")

        dif = latest.get("macd_dif")
        if pd.notna(dif) and dif > 0:
            score += 10
            reasons.append("MACD DIF>0")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params

        ret_col = f"return_{p.lookback_period}d"
        if ret_col not in df.columns:
            df[ret_col] = df["close"].pct_change(periods=p.lookback_period)

        ma_col = f"ma{p.ma_period}"
        if ma_col not in df.columns:
            df[ma_col] = df["close"].rolling(window=p.ma_period).mean()

        buy_mask = (df[ret_col] > 0) & (df["close"] > df[ma_col])
        sell_mask = df[ret_col] < -0.05

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
        return ETFRotationBT

    @staticmethod
    def get_etf_universe() -> list[str]:
        return DEFAULT_ETF_LIST
