import akshare as ak
import pandas as pd


def concept_boards() -> pd.DataFrame:
    """获取同花顺概念板块列表及涨幅排名"""
    try:
        return ak.stock_board_concept_name_ths().reset_index(drop=True)
    except Exception as e:
        print(f"concept_boards failed: {e}")
        return pd.DataFrame()


def industry_boards() -> pd.DataFrame:
    """获取同花顺行业板块涨跌排行"""
    try:
        return ak.stock_board_industry_name_ths().reset_index(drop=True)
    except Exception as e:
        print(f"industry_boards failed: {e}")
        return pd.DataFrame()


def board_stocks(board_type: str = "concept", board_code: str = "") -> pd.DataFrame:
    """获取某板块下的成分股列表"""
    try:
        if board_type == "concept":
            return ak.stock_board_concept_cons_ths(symbol=board_code).reset_index(drop=True)
        return ak.stock_board_industry_cons_ths(symbol=board_code).reset_index(drop=True)
    except Exception as e:
        print(f"board_stocks failed: {e}")
        return pd.DataFrame()


def stock_rating(code: str) -> pd.DataFrame:
    """获取同花顺个股综合评级"""
    try:
        return ak.stock_individual_info_ths(symbol=code)
    except Exception as e:
        print(f"stock_rating failed: {e}")
        return pd.DataFrame()
