import pandas as pd
from datetime import datetime, timedelta
from smilex.fetcher import stock_list, daily_history
from smilex.indicators import all_indicators
from smilex.config import SCANNER_MIN_LISTED_DAYS


def daily_scan(strategy_name: str = "trend_following", **params) -> pd.DataFrame:
    """全市场扫描，返回推荐股票列表"""
    from smilex.strategies import get_strategy

    strategy = get_strategy(strategy_name, **params)
    indicator_names = strategy.required_indicators

    stocks = stock_list()
    results: list[dict] = []
    total = len(stocks)

    # For value_technical strategy, pre-load valuation cache
    valuation_cache: dict | None = None
    if strategy_name == "value_technical":
        try:
            from smilex.store import query_latest_valuation
            val_df = query_latest_valuation()
            if not val_df.empty:
                valuation_cache = {}
                for _, row in val_df.iterrows():
                    valuation_cache[row["code"]] = {
                        "pe": row.get("pe"), "pb": row.get("pb"),
                        "roe": row.get("roe"), "total_mv": row.get("total_mv"),
                    }
                from smilex.strategies.value_technical import ValueTechnicalStrategy
                if isinstance(strategy, ValueTechnicalStrategy):
                    strategy.set_valuation_cache(valuation_cache)
        except Exception:
            pass

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

        df = all_indicators(df, indicators=indicator_names)

        # Evaluate with strategy
        if strategy_name == "value_technical":
            score, reasons = strategy.evaluate(df.iloc[-1], code=code)
        else:
            score, reasons = strategy.evaluate(df.iloc[-1])

        if score > 0:
            results.append({
                "code": code, "name": name,
                "price": round(df.iloc[-1]["close"], 2),
                "change_pct": round(df.iloc[-1].get("change_pct", 0), 2),
                "volume_ratio": round(df.iloc[-1].get("volume_ratio", 0), 2),
                "score": score,
                "reasons": "；".join(reasons),
                "strategy": strategy.metadata.display_name,
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
