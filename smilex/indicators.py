import pandas as pd
import pandas_ta as ta
from smilex.config import MA_SHORT_PERIOD, MA_LONG_PERIOD, RSI_PERIOD, BOLLINGER_PERIOD, BOLLINGER_STD


def ma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    if periods is None:
        periods = [5, 10, 20, 60]
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(window=p).mean()
    return df


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    result = ta.macd(df["close"], fast=fast, slow=slow, length=signal)
    if result is not None:
        df["macd_dif"] = result.iloc[:, 0]
        df["macd_dea"] = result.iloc[:, 1]
        df["macd_hist"] = result.iloc[:, 2]
    return df


def rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    df[f"rsi{period}"] = ta.rsi(df["close"], length=period)
    return df


def bollinger(df: pd.DataFrame, period: int = BOLLINGER_PERIOD,
              std: float = BOLLINGER_STD) -> pd.DataFrame:
    bb = ta.bbands(df["close"], length=period, std=std)
    if bb is not None:
        df["boll_upper"] = bb.iloc[:, 0]
        df["boll_mid"] = bb.iloc[:, 1]
        df["boll_lower"] = bb.iloc[:, 2]
    return df


def kdj(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
    low_min = df["low"].rolling(window=period).min()
    high_max = df["high"].rolling(window=period).max()
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    df["kdj_d"] = df["kdj_k"].ewm(com=2, adjust=False).mean()
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    return df


def volume_ratio(df: pd.DataFrame) -> pd.DataFrame:
    avg_vol = df["volume"].rolling(window=5).mean().shift(1)
    df["volume_ratio"] = df["volume"] / avg_vol
    return df


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    result = ta.adx(df["high"], df["low"], df["close"], length=period)
    if result is not None:
        df["adx"] = result.iloc[:, 0]
    return df


def donchian(df: pd.DataFrame, entry_period: int = 20, exit_period: int = 10) -> pd.DataFrame:
    df["donchian_upper"] = df["high"].rolling(window=entry_period).max()
    df["donchian_lower"] = df["low"].rolling(window=exit_period).min()
    return df


def price_returns(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"return_{period}d"] = df["close"].pct_change(periods=period)
    return df


def volume_momentum(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.DataFrame:
    df["vol_mom_fast"] = df["volume"].rolling(window=fast).mean()
    df["vol_mom_slow"] = df["volume"].rolling(window=slow).mean()
    df["volume_momentum"] = df["vol_mom_fast"] / df["vol_mom_slow"]
    return df


_INDICATOR_MAP = {
    "ma": ma,
    "macd": macd,
    "rsi": rsi,
    "bollinger": bollinger,
    "kdj": kdj,
    "volume_ratio": volume_ratio,
    "adx": adx,
    "donchian": donchian,
    "price_returns": lambda d: price_returns(d),
    "volume_momentum": lambda d: volume_momentum(d),
}


def all_indicators(df: pd.DataFrame, indicators: list[str] | None = None) -> pd.DataFrame:
    target = indicators if indicators is not None else list(_INDICATOR_MAP.keys())
    for name in target:
        func = _INDICATOR_MAP.get(name)
        if func:
            df = func(df)
    return df
