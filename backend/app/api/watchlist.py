from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.watchlist import add_watchlist_stock, delete_watchlist_stock, list_watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistStockRequest(BaseModel):
    code: str
    name: str | None = None
    note: str | None = None


@router.get("/stocks")
def api_list_watchlist_stocks(trade_date: str | None = Query(default=None, description="YYYY-MM-DD")):
    items = list_watchlist(trade_date)
    return {"items": items, "total": len(items)}


@router.post("/stocks")
def api_add_watchlist_stock(req: WatchlistStockRequest):
    code = req.code.strip()
    if not code:
        raise HTTPException(400, "股票代码不能为空")
    return add_watchlist_stock(code, req.name, req.note)


@router.delete("/stocks/{code}")
def api_delete_watchlist_stock(code: str):
    ok = delete_watchlist_stock(code)
    if not ok:
        raise HTTPException(404, "自选股不存在")
    return {"success": True}
