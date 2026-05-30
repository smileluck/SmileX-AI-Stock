import pandas as pd
import backtrader as bt
from dataclasses import dataclass

from smilex.strategies.base import BaseStrategy, StrategyMetadata, StrategyParams


@dataclass
class ValueTechnicalParams(StrategyParams):
    pe_lower: float = 8.0
    pe_upper: float = 25.0
    pb_upper: float = 3.0
    ma_period: int = 60
    rsi_lower: float = 40.0
    rsi_upper: float = 60.0
    volume_ratio_min: float = 1.0


class ValueTechnicalBT(bt.Strategy):
    params = (
        ("ma_period", 60),
    )

    def __init__(self):
        self.ma = bt.indicators.SMA(self.data.close, period=self.p.ma_period)
        self.macd = bt.indicators.MACD(self.data.close)
        self.trades: list[dict] = []

    def next(self):
        if self.macd.lines.macd[0] > self.macd.lines.signal[0]:
            if self.macd.lines.macd[-1] <= self.macd.lines.signal[-1]:
                if self.data.close[0] > self.ma[0]:
                    if not self.position:
                        size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                        if size > 0:
                            self.buy(size=size)
                            self.trades.append({
                                "type": "BUY", "date": self.data.datetime.date(0),
                                "price": self.data.close[0], "size": size,
                            })
        elif self.macd.lines.macd[0] < self.macd.lines.signal[0]:
            if self.position:
                self.close()
                self.trades.append({
                    "type": "SELL", "date": self.data.datetime.date(0),
                    "price": self.data.close[0], "size": self.position.size,
                })


class ValueTechnicalStrategy(BaseStrategy):

    def __init__(self, params: ValueTechnicalParams | None = None):
        super().__init__(params)
        self._valuation_cache: dict | None = None

    @property
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="value_technical",
            display_name="价值技术混合",
            description="PE/PB估值筛选 + MACD技术信号，基本面与技术面结合",
            category="价值",
        )

    @property
    def _params_cls(self) -> type:
        return ValueTechnicalParams

    @property
    def required_indicators(self) -> list[str]:
        return ["ma", "macd", "rsi", "volume_ratio"]

    def set_valuation_cache(self, cache: dict):
        """Set PE/PB cache: {code: {pe: float, pb: float, ...}}"""
        self._valuation_cache = cache

    def _get_valuation(self, code: str) -> dict:
        if self._valuation_cache and code in self._valuation_cache:
            return self._valuation_cache[code]
        try:
            from smilex.store import query_latest_valuation
            df = query_latest_valuation([code])
            if not df.empty:
                row = df.iloc[0]
                return {"pe": row.get("pe"), "pb": row.get("pb")}
        except Exception:
            pass
        return {}

    def evaluate(self, latest: pd.Series, code: str = "") -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        p = self.params

        val = self._get_valuation(code) if code else {}
        pe = val.get("pe")
        pb = val.get("pb")

        if pe is not None:
            if p.pe_lower <= pe <= p.pe_upper:
                score += 20
                reasons.append(f"PE合理({pe:.1f})")
            elif pe < p.pe_lower:
                score += 10
                reasons.append(f"PE偏低({pe:.1f})")

        if pb is not None:
            if pb < p.pb_upper:
                score += 15
                reasons.append(f"PB适中({pb:.1f})")

        dif = latest.get("macd_dif")
        dea = latest.get("macd_dea")
        if pd.notna(dif) and pd.notna(dea) and dif > dea:
            score += 15
            reasons.append("MACD金叉")

        close = latest.get("close", 0)
        ma_col = f"ma{p.ma_period}"
        ma_val = latest.get(ma_col, latest.get("ma60"))
        if pd.notna(ma_val) and close > ma_val:
            score += 20
            reasons.append(f"站上MA{p.ma_period}")

        vol_ratio = latest.get("volume_ratio", 0)
        if pd.notna(vol_ratio) and vol_ratio > p.volume_ratio_min:
            score += 15
            reasons.append(f"量比正常({vol_ratio:.1f})")

        rsi_val = latest.get("rsi14")
        if pd.notna(rsi_val) and p.rsi_lower < rsi_val < p.rsi_upper:
            score += 15
            reasons.append(f"RSI适中({rsi_val:.0f})")

        return score, reasons

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        p = self.params

        ma_col = f"ma{p.ma_period}"
        if ma_col not in df.columns:
            df[ma_col] = df["close"].rolling(window=p.ma_period).mean()

        dif = df.get("macd_dif")
        dea = df.get("macd_dea")
        if dif is not None and dea is not None:
            golden = (dif > dea) & (dif.shift(1) <= dea.shift(1))
            death = (dif < dea) & (dif.shift(1) >= dea.shift(1))
        else:
            golden = pd.Series(False, index=df.index)
            death = pd.Series(False, index=df.index)

        buy_mask = golden & (df["close"] > df[ma_col])
        sell_mask = death

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
        return ValueTechnicalBT
