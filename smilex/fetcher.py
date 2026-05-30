import akshare as ak
import pandas as pd
from smilex.config import DEFAULT_START_DATE


def stock_list() -> pd.DataFrame:
    """获取沪深A股列表，过滤ST和退市股"""
    df = ak.stock_zh_a_spot_em()
    df = df[~df["名称"].str.contains("ST|退", na=False)]
    df = df.rename(columns={
        "序号": "seq", "代码": "code", "名称": "name",
        "最新价": "price", "涨跌幅": "change_pct",
        "涨跌额": "change_amt", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude",
        "最高": "high", "最低": "low", "今开": "open",
        "昨收": "pre_close",
    })
    df = df[["code", "name", "price", "change_pct", "change_amt",
             "volume", "amount", "amplitude", "high", "low", "open", "pre_close"]]
    return df.reset_index(drop=True)


def daily_history(code: str, start_date: str = DEFAULT_START_DATE,
                  end_date: str = "", adjust: str = "qfq") -> pd.DataFrame:
    """获取个股日K线数据（前复权）"""
    df = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start_date, end_date=end_date,
        adjust=adjust,
    )
    df = df.rename(columns={
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude",
        "涨跌幅": "change_pct", "涨跌额": "change_amt",
        "换手率": "turnover",
    })
    df["date"] = pd.to_datetime(df["date"])
    df["code"] = code
    return df.reset_index(drop=True)


def index_daily(symbol: str = "000001",
                start_date: str = DEFAULT_START_DATE) -> pd.DataFrame:
    """获取指数日K线数据"""
    # stock_zh_index_daily 需要市场前缀: sh(沪) / sz(深)
    if not symbol.startswith(("sh", "sz")):
        prefix = "sh" if symbol.startswith(("000", "5")) else "sz"
        full_symbol = f"{prefix}{symbol}"
    else:
        full_symbol = symbol

    df = ak.stock_zh_index_daily(symbol=full_symbol)
    df["date"] = pd.to_datetime(df["date"])
    start = pd.to_datetime(start_date)
    df = df[df["date"] >= start]
    df["code"] = symbol
    return df.reset_index(drop=True)


def sector_list() -> pd.DataFrame:
    """获取东方财富行业板块列表"""
    df = ak.stock_board_industry_name_em()
    return df.reset_index(drop=True)


def realtime_quote() -> pd.DataFrame:
    """获取A股实时行情快照"""
    df = ak.stock_zh_a_spot_em()
    return df.reset_index(drop=True)


def stock_info(code: str) -> pd.DataFrame:
    """获取个股基本信息"""
    df = ak.stock_individual_info_em(symbol=code)
    return df


def stock_valuation(code: str) -> dict:
    """获取个股最新估值数据 (PE, PB, ROE, 总市值)"""
    try:
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is None or df.empty:
            return {}
        latest = df.iloc[-1]
        return {
            "code": code,
            "date": str(latest.get("trade_date", "")),
            "pe": float(latest.get("pe", 0)) if pd.notna(latest.get("pe")) else None,
            "pb": float(latest.get("pb", 0)) if pd.notna(latest.get("pb")) else None,
            "roe": float(latest.get("roe", 0)) if pd.notna(latest.get("roe")) else None,
            "total_mv": float(latest.get("total_mv", 0)) if pd.notna(latest.get("total_mv")) else None,
        }
    except Exception:
        return {}


def sync_valuation_data(codes: list[str] | None = None, months: int = 6) -> pd.DataFrame:
    """批量获取估值数据，返回 DataFrame 供 store.save_valuation() 使用"""
    from datetime import datetime, timedelta
    from smilex.store import _conn

    if codes is None:
        conn = _conn()
        try:
            codes = pd.read_sql("SELECT code FROM stock_info", conn)["code"].tolist()
        finally:
            conn.close()

    start_date = (datetime.now() - timedelta(days=months * 30)).strftime("%Y%m%d")
    all_rows: list[dict] = []
    total = len(codes)

    for i, code in enumerate(codes):
        try:
            df = ak.stock_a_indicator_lg(symbol=code)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df = df[df["trade_date"] >= start_date]
                for _, row in df.iterrows():
                    all_rows.append({
                        "code": code,
                        "date": str(row["trade_date"].date()),
                        "pe": float(row["pe"]) if pd.notna(row.get("pe")) else None,
                        "pb": float(row["pb"]) if pd.notna(row.get("pb")) else None,
                        "roe": float(row["roe"]) if pd.notna(row.get("roe")) else None,
                        "total_mv": float(row["total_mv"]) if pd.notna(row.get("total_mv")) else None,
                    })
        except Exception:
            pass
        if (i + 1) % 100 == 0:
            print(f"[{i+1}/{total}] 估值数据同步中...")

    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
