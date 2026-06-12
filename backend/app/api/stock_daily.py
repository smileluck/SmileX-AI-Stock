from datetime import datetime

from fastapi import APIRouter, Query

from app.services.stock_daily import (
    snapshot_stock_daily,
    get_stock_daily,
    get_stock_daily_detail,
    get_stock_daily_ranking,
    get_stock_daily_dates,
    get_stock_daily_summary,
)

router = APIRouter(tags=["stock_daily"])


@router.post("/stock-daily/snapshot")
def trigger_stock_daily_snapshot():
    return snapshot_stock_daily()


@router.get("/stock-daily/list")
def query_stock_daily(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    sort_by: str = Query(default="change_pct"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    board: str | None = Query(default=None, description="沪深主板/创业板/科创板/北交所"),
    keyword: str | None = Query(default=None, description="代码或名称搜索"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    watchlist_first: bool = Query(default=True, description="自选股置顶"),
):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    items, total = get_stock_daily(
        trade_date, sort_by=sort_by, sort_order=sort_order,
        board=board, keyword=keyword, limit=limit, offset=offset,
        watchlist_first=watchlist_first,
    )
    return {"trade_date": trade_date, "items": items, "total": total}


@router.get("/stock-daily/detail/{code}")
def stock_daily_detail(
    code: str,
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
):
    data = get_stock_daily_detail(code, trade_date)
    if not data:
        return {"success": False, "message": "未找到数据"}
    return data


@router.get("/stock-daily/ranking")
def stock_daily_ranking(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    metric: str = Query(default="change_pct"),
    board: str | None = Query(default=None, description="沪深主板/创业板/科创板/北交所"),
    top_n: int = Query(default=20, ge=5, le=200),
):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    items = get_stock_daily_ranking(trade_date, metric=metric, board=board, top_n=top_n)
    return {"trade_date": trade_date, "metric": metric, "items": items}


@router.get("/stock-daily/dates")
def stock_daily_dates(limit: int = Query(default=90, le=365)):
    return {"dates": get_stock_daily_dates(limit)}


@router.get("/stock-daily/summary")
def stock_daily_summary(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    return get_stock_daily_summary(trade_date)
