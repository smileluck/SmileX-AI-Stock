from smilex.consult import ths, em, xq


def query_stock(code: str) -> dict:
    """综合查询一只股票的资讯，返回三站聚合结果"""
    return {
        "ths": ths.stock_rating(code),
        "em": em.capital_flow(code),
        "xq": xq.stock_info(code),
    }
