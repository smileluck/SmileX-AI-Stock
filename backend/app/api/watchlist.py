"""自选股 / 自选板块 API。

M1: 关注股 CRUD（扩展字段）+ 搜索 + 一键加入 + 每日行情 + 板块 CRUD
M2/M3 的快照与分析端点单独追加（见 watchlist_snapshot / watchlist_analysis 服务）
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.watchlist import (
    add_custom_sector,
    add_custom_sector_stock,
    add_market_sector,
    add_watchlist_stock,
    delete_custom_sector,
    delete_market_sector,
    delete_watchlist_stock,
    get_watchlist_stock,
    list_custom_sector_stocks,
    list_custom_sectors,
    list_market_sectors,
    list_watchlist,
    list_watchlist_daily,
    remove_custom_sector_stock,
    search_stock,
    update_custom_sector,
    update_watchlist_stock,
    upsert_from_recommendation,
)
from app.services.watchlist_snapshot import snapshot_watchlist_daily
from app.services.watchlist_analysis import (
    get_watchlist_analysis_task_status,
    list_watchlist_analysis,
    start_watchlist_analysis_task,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


# ---------------------------------------------------------------------------
# 关注股
# ---------------------------------------------------------------------------

class WatchlistStockRequest(BaseModel):
    code: str
    name: str | None = None
    note: str | None = None
    add_price: float | None = None
    target_buy_price: float | None = None
    stop_loss_price: float | None = None
    source: str = "manual"
    custom_sector_id: int | None = None


class WatchlistStockPatch(BaseModel):
    name: str | None = None
    note: str | None = None
    target_buy_price: float | None = None
    stop_loss_price: float | None = None
    status: str | None = None
    custom_sector_id: int | None = None
    sort_order: int | None = None


class FromRecommendationRequest(BaseModel):
    code: str
    name: str | None = None
    add_price: float | None = None


@router.get("/stocks")
def api_list_watchlist_stocks(trade_date: str | None = Query(default=None, description="YYYY-MM-DD")):
    items = list_watchlist(trade_date)
    return {"items": items, "total": len(items)}


@router.post("/stocks")
def api_add_watchlist_stock(req: WatchlistStockRequest):
    code = req.code.strip()
    if not code:
        raise HTTPException(400, "股票代码不能为空")
    try:
        return add_watchlist_stock(
            code=code,
            name=req.name,
            note=req.note,
            add_price=req.add_price,
            target_buy=req.target_buy_price,
            stop_loss=req.stop_loss_price,
            source=req.source,
            custom_sector_id=req.custom_sector_id,
        )
    except Exception as e:
        raise HTTPException(500, f"添加失败: {e}")


@router.patch("/stocks/{code}")
def api_patch_watchlist_stock(code: str, req: WatchlistStockPatch):
    if not get_watchlist_stock(code):
        raise HTTPException(404, "自选股不存在")
    return update_watchlist_stock(code, req.model_dump(exclude_none=True))


@router.delete("/stocks/{code}")
def api_delete_watchlist_stock(code: str):
    ok = delete_watchlist_stock(code)
    if not ok:
        raise HTTPException(404, "自选股不存在")
    return {"success": True}


@router.get("/stocks/search")
def api_search_stock(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50)):
    return {"items": search_stock(q, limit=limit)}


@router.post("/stocks/from-recommendation")
def api_add_from_recommendation(req: FromRecommendationRequest):
    code = req.code.strip()
    if not code:
        raise HTTPException(400, "股票代码不能为空")
    return upsert_from_recommendation(code, req.name, req.add_price)


@router.get("/stocks/{code}/daily")
def api_get_watchlist_daily(code: str, days: int = Query(30, ge=1, le=365)):
    return {"items": list_watchlist_daily(code, days=days), "code": code}


# ---------------------------------------------------------------------------
# 市场板块关注
# ---------------------------------------------------------------------------

class MarketSectorRequest(BaseModel):
    sector_name: str
    sector_type: str = "industry"
    note: str = ""


@router.get("/sectors")
def api_list_market_sectors():
    items = list_market_sectors()
    return {"items": items, "total": len(items)}


@router.post("/sectors")
def api_add_market_sector(req: MarketSectorRequest):
    try:
        return add_market_sector(req.sector_name, req.sector_type, req.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/sectors/{sector_id}")
def api_delete_market_sector(sector_id: int):
    ok = delete_market_sector(sector_id)
    if not ok:
        raise HTTPException(404, "板块不存在")
    return {"success": True}


# ---------------------------------------------------------------------------
# 自定义板块
# ---------------------------------------------------------------------------

class CustomSectorRequest(BaseModel):
    name: str
    note: str = ""
    sort_order: int | None = None


class CustomSectorStockRequest(BaseModel):
    code: str
    name: str | None = None


@router.get("/custom-sectors")
def api_list_custom_sectors():
    items = list_custom_sectors()
    return {"items": items, "total": len(items)}


@router.post("/custom-sectors")
def api_add_custom_sector(req: CustomSectorRequest):
    try:
        return add_custom_sector(req.name, req.note)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/custom-sectors/{sector_id}")
def api_update_custom_sector(sector_id: int, req: CustomSectorRequest):
    if not any(s["id"] == sector_id for s in list_custom_sectors()):
        raise HTTPException(404, "板块不存在")
    return update_custom_sector(sector_id, req.model_dump(exclude_none=True))


@router.delete("/custom-sectors/{sector_id}")
def api_delete_custom_sector(sector_id: int):
    ok = delete_custom_sector(sector_id)
    if not ok:
        raise HTTPException(404, "板块不存在")
    return {"success": True}


@router.get("/custom-sectors/{sector_id}/stocks")
def api_list_custom_sector_stocks(sector_id: int):
    items = list_custom_sector_stocks(sector_id)
    return {"items": items, "total": len(items)}


@router.post("/custom-sectors/{sector_id}/stocks")
def api_add_custom_sector_stock(sector_id: int, req: CustomSectorStockRequest):
    code = req.code.strip()
    if not code:
        raise HTTPException(400, "股票代码不能为空")
    return add_custom_sector_stock(sector_id, code, req.name)


@router.delete("/custom-sectors/{sector_id}/stocks/{code}")
def api_remove_custom_sector_stock(sector_id: int, code: str):
    return remove_custom_sector_stock(sector_id, code)


# ---------------------------------------------------------------------------
# 每日快照（M2）
# ---------------------------------------------------------------------------

@router.post("/snapshot")
def api_snapshot_watchlist(trade_date: str | None = Query(default=None, description="YYYY-MM-DD，默认今天")):
    """手动触发：拉取所有 watching 关注股的当日行情，写入 watchlist_stock_daily。"""
    try:
        return snapshot_watchlist_daily(trade_date=trade_date, trigger="manual")
    except Exception as e:
        raise HTTPException(500, f"快照失败: {e}")


# ---------------------------------------------------------------------------
# 买入时机分析（M3）
# ---------------------------------------------------------------------------

@router.post("/analysis/generate")
def api_generate_analysis(
    phase: str = Query(..., description="morning 或 close"),
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD，默认今天"),
):
    """触发早盘/收盘买点分析（异步任务）。"""
    from datetime import datetime
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    try:
        return start_watchlist_analysis_task(trade_date, phase)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"启动分析失败: {e}")


@router.get("/analysis/task-status")
def api_analysis_task_status(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    phase: str = Query(..., description="morning 或 close"),
):
    return get_watchlist_analysis_task_status(trade_date, phase)


@router.get("/analysis")
def api_list_analysis(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD，缺省取最新"),
    phase: str | None = Query(default=None, description="morning 或 close"),
    code: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=500),
):
    return list_watchlist_analysis(trade_date=trade_date, phase=phase, code=code, limit=limit)
