import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compute_indicators(daily_rows: list[dict]) -> dict | None:
    """Compute technical indicators from historical daily OHLCV data.

    Args:
        daily_rows: List of dicts from stock_daily table, any order.

    Returns:
        Dict with indicator values (latest), or None if insufficient data.
    """
    if not daily_rows or len(daily_rows) < 26:
        return None

    try:
        df = pd.DataFrame(daily_rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values("trade_date").reset_index(drop=True)

        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

        close = df["close"]
        high = df["high"]
        low = df["low"]

        result = {}

        # --- MA ---
        for n in (5, 10, 20, 60):
            ma = close.rolling(n).mean()
            val = ma.iloc[-1]
            result[f"ma{n}"] = round(val, 2) if pd.notna(val) else None

        # --- MACD (12, 26, 9) ---
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_bar = (dif - dea) * 2

        for name, series in (("dif", dif), ("dea", dea), ("macd_bar", macd_bar)):
            val = series.iloc[-1]
            result[name] = round(val, 2) if pd.notna(val) else None

        # --- RSI (6, 12, 24) Wilder method ---
        delta = close.diff()
        for period in (6, 12, 24):
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, pd.NA)
            rsi = 100 - (100 / (1 + rs))
            val = rsi.iloc[-1]
            result[f"rsi{period}"] = round(val, 2) if pd.notna(val) else None

        # --- KDJ (9, 3, 3) ---
        low_9 = low.rolling(9).min()
        high_9 = high.rolling(9).max()
        rsv = (close - low_9) / (high_9 - low_9).replace(0, pd.NA) * 100
        k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
        d = k.ewm(alpha=1 / 3, adjust=False).mean()
        j = 3 * k - 2 * d

        for name, series in (("k", k), ("d", d), ("j", j)):
            val = series.iloc[-1]
            result[name] = round(val, 2) if pd.notna(val) else None

        # --- Bollinger Bands (20, 2) ---
        boll_mid = close.rolling(20).mean()
        boll_std = close.rolling(20).std()
        boll_upper = boll_mid + 2 * boll_std
        boll_lower = boll_mid - 2 * boll_std

        for name, series in (("boll_upper", boll_upper), ("boll_mid", boll_mid), ("boll_lower", boll_lower)):
            val = series.iloc[-1]
            result[name] = round(val, 2) if pd.notna(val) else None

        # Check that at least MA5 and MACD are valid
        if result.get("ma5") is None and result.get("dif") is None:
            return None

        return result

    except Exception:
        logger.warning("Failed to compute technical indicators", exc_info=True)
        return None
