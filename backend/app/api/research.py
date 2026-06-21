"""券商研报调研选股 REST 路由。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.research_pick import (
    get_pick_task_status,
    get_pick_history,
    get_picks_by_date,
    get_latest_pick_date,
    start_pick_task,
)
from app.services.research_sync import (
    get_recent_reports,
    get_org_list,
    sync_research_reports,
)

router = APIRouter(tags=["research"])


class PickGenerateRequest(BaseModel):
    trade_date: Optional[str] = None
    phase: Optional[str] = "close"


@router.get("/research/reports")
def list_reports(
    days: int = Query(default=7, ge=1, le=90),
    report_type: Optional[str] = Query(default=None, description="stock/industry"),
    rating: Optional[str] = Query(default=None, description="买入/增持/中性/减持"),
    org: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    rows, total = get_recent_reports(
        days=days, report_type=report_type, rating=rating, org=org,
        limit=limit, offset=offset,
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/research/orgs")
def list_orgs(limit: int = Query(default=50, ge=1, le=200)):
    """机构过滤下拉选项。"""
    return {"items": get_org_list(limit=limit)}


@router.get("/research/picks")
def list_picks(trade_date: Optional[str] = Query(default=None, description="YYYY-MM-DD")):
    """查选股结果。无 trade_date 时取最近一次。"""
    date = trade_date or get_latest_pick_date()
    if not date:
        return {"items": [], "total": 0, "trade_date": None}
    items = get_picks_by_date(date)
    return {"items": items, "total": len(items), "trade_date": date}


@router.get("/research/picks/history")
def picks_history(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    items, total = get_pick_history(limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/research/picks/task-status")
def picks_task_status(
    trade_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    phase: str = Query(default="close"),
):
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    return get_pick_task_status(date, phase)


@router.post("/research/picks/generate")
def trigger_pick_generate(request: PickGenerateRequest | None = None):
    """立即启动后台选股任务，不等结果直接返回。前端轮询 task-status。"""
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    phase = (request.phase if request else None) or "close"
    try:
        result = start_pick_task(trade_date, phase)
        return result
    except Exception as e:
        return {"started": False, "already_running": False, "error": str(e),
                "trade_date": trade_date, "phase": phase}


@router.post("/research/sync")
def trigger_sync(days: int = Query(default=3, ge=1, le=30)):
    """手动触发研报抓取。"""
    return sync_research_reports(trigger="manual", days=days)
