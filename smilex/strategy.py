import pandas as pd
import numpy as np
from smilex.config import MA_SHORT_PERIOD, MA_LONG_PERIOD


def generate_signals(df: pd.DataFrame, short_period: int = MA_SHORT_PERIOD,
                     long_period: int = MA_LONG_PERIOD) -> pd.DataFrame:
    """双均线交叉策略信号：短线上穿长线=买入(1)，下穿=卖出(-1)"""
    df = df.copy()
    df[f"ma{short_period}"] = df["close"].rolling(window=short_period).mean()
    df[f"ma{long_period}"] = df["close"].rolling(window=long_period).mean()

    golden_cross = (
        (df[f"ma{short_period}"] > df[f"ma{long_period}"]) &
        (df[f"ma{short_period}"].shift(1) <= df[f"ma{long_period}"].shift(1))
    )
    death_cross = (
        (df[f"ma{short_period}"] < df[f"ma{long_period}"]) &
        (df[f"ma{short_period}"].shift(1) >= df[f"ma{long_period}"].shift(1))
    )

    df["signal"] = 0
    df.loc[golden_cross, "signal"] = 1
    df.loc[death_cross, "signal"] = -1
    df["position"] = np.where(df[f"ma{short_period}"] > df[f"ma{long_period}"], 1, 0)
    return df
