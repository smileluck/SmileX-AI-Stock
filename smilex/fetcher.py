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
