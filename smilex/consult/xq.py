import akshare as ak
import pandas as pd


def hot_stocks(rank_type: str = "deal") -> pd.DataFrame:
    """获取雪球热度排行榜（deal/follow/tweet）"""
    try:
        if rank_type == "follow":
            df = ak.stock_hot_follow_xq()
        elif rank_type == "tweet":
            df = ak.stock_hot_tweet_xq()
        else:
            df = ak.stock_hot_deal_xq()
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"hot_stocks({rank_type}) failed: {e}")
        return pd.DataFrame()


def stock_info(code: str) -> pd.DataFrame:
    """获取雪球个股基本信息"""
    try:
        return ak.stock_individual_basic_info_xq(symbol=code)
    except Exception as e:
        print(f"stock_info failed: {e}")
        return pd.DataFrame()
