import pandas as pd
import numpy as np


def generate_signals(df: pd.DataFrame, short_period: int = 5,
                     long_period: int = 20) -> pd.DataFrame:
    """双均线交叉策略信号（向后兼容，委托给 TrendFollowingStrategy）"""
    from smilex.strategies.trend_following import TrendFollowingStrategy, TrendFollowingParams

    params = TrendFollowingParams(short_period=short_period, long_period=long_period)
    strategy = TrendFollowingStrategy(params=params)
    return strategy.generate_signals(df)
