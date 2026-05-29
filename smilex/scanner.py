import pandas as pd
from datetime import datetime, timedelta
from smilex.fetcher import stock_list, daily_history
from smilex.indicators import all_indicators
from smilex.config import SCANNER_MIN_LISTED_DAYS, SCANNER_VOLUME_RATIO_MIN


def daily_scan() -> pd.DataFrame:
    """全市场扫描，返回推荐股票列表"""
    stocks = stock_list()
    results: list[dict] = []
    total = len(stocks)

    for i, row in stocks.iterrows():
        code = row["code"]
        name = row["name"]

        if _should_skip(row):
            continue

        try:
            start = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")
            df = daily_history(code, start_date=start)
        except Exception:
            continue

        if len(df) < SCANNER_MIN_LISTED_DAYS:
            continue

        df = all_indicators(df)
        score, reasons = _evaluate(df.iloc[-1])

        if score > 0:
            results.append({
                "code": code, "name": name,
                "price": round(df.iloc[-1]["close"], 2),
                "change_pct": round(df.iloc[-1].get("change_pct", 0), 2),
                "volume_ratio": round(df.iloc[-1].get("volume_ratio", 0), 2),
                "score": score,
                "reasons": "；".join(reasons),
            })

        if (i + 1) % 500 == 0:
            print(f"Scanned {i+1}/{total}...")

    if results:
        return pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)
    return pd.DataFrame(results)


def _should_skip(row) -> bool:
    name = str(row.get("name", ""))
    if "ST" in name or "退" in name:
        return True
    change_pct = row.get("change_pct", 0)
    if pd.isna(change_pct) or abs(float(change_pct)) >= 9.9:
        return True
    price = row.get("price", 0)
    if pd.isna(price) or float(price) <= 0:
        return True
    return False


def _evaluate(latest: pd.Series) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    ma5 = latest.get("ma5")
    ma10 = latest.get("ma10")
    ma20 = latest.get("ma20")
    ma60 = latest.get("ma60")

    if all(pd.notna([ma5, ma10, ma20, ma60])):
        if ma5 > ma10 > ma20 > ma60:
            score += 30
            reasons.append("均线多头排列")

    dif = latest.get("macd_dif")
    dea = latest.get("macd_dea")
    if all(pd.notna([dif, dea])):
        if dif > dea:
            score += 20
            reasons.append("MACD金叉")
        elif abs(dif - dea) / max(abs(dea), 0.01) < 0.05:
            score += 10
            reasons.append("MACD即将金叉")

    vol_ratio = latest.get("volume_ratio", 0)
    if pd.notna(vol_ratio) and vol_ratio > SCANNER_VOLUME_RATIO_MIN:
        score += 20
        reasons.append(f"放量(量比{vol_ratio:.1f})")

    close = latest.get("close", 0)
    boll_mid = latest.get("boll_mid")
    if pd.notna(boll_mid) and close > boll_mid:
        score += 15
        reasons.append("站上布林中轨")

    rsi_val = latest.get("rsi14")
    if pd.notna(rsi_val):
        if 40 < rsi_val < 70:
            score += 15
            reasons.append(f"RSI适中({rsi_val:.0f})")
        elif rsi_val < 40:
            score += 5
            reasons.append(f"RSI偏低({rsi_val:.0f})")

    return score, reasons
