import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


def capital_flow(code: str) -> pd.DataFrame:
    """获取个股资金流向"""
    try:
        market = "sh" if code.startswith("6") else "sz"
        return ak.stock_individual_fund_flow(stock=code, market=market).reset_index(drop=True)
    except Exception as e:
        print(f"capital_flow failed: {e}")
        return pd.DataFrame()


def market_fund_flow() -> pd.DataFrame:
    """获取大盘资金流向"""
    try:
        return ak.stock_market_fund_flow().reset_index(drop=True)
    except Exception as e:
        print(f"market_fund_flow failed: {e}")
        return pd.DataFrame()


def north_flow() -> pd.DataFrame:
    """获取北向资金每日净流入"""
    try:
        return ak.stock_hsgt_north_net_flow_in_em().reset_index(drop=True)
    except Exception as e:
        print(f"north_flow failed: {e}")
        return pd.DataFrame()


def north_holdings() -> pd.DataFrame:
    """获取北向资金重仓股排行"""
    try:
        return ak.stock_hsgt_hold_detail_em(market="北向").reset_index(drop=True)
    except Exception as e:
        print(f"north_holdings failed: {e}")
        return pd.DataFrame()


def dragon_tiger(date: str = "") -> pd.DataFrame:
    """获取龙虎榜每日详情"""
    try:
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        return ak.stock_lhb_detail_em(start_date=date, end_date=date).reset_index(drop=True)
    except Exception as e:
        print(f"dragon_tiger failed: {e}")
        return pd.DataFrame()


def margin_data() -> pd.DataFrame:
    """获取融资融券数据"""
    try:
        d = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")
        return ak.stock_margin_sse(start_date=d, end_date=d).reset_index(drop=True)
    except Exception as e:
        print(f"margin_data failed: {e}")
        return pd.DataFrame()


def analyst_reports(code: str) -> pd.DataFrame:
    """获取个股研报评级"""
    try:
        return ak.stock_analyst_detail_em(analyst_id=code).reset_index(drop=True)
    except Exception as e:
        print(f"analyst_reports failed: {e}")
        return pd.DataFrame()
