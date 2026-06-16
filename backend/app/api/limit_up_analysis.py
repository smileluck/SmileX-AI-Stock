import logging
from datetime import datetime

from fastapi import APIRouter, Query

from app.services.limit_up_analysis import (
    get_analysis_task_status,
    get_limit_up_analysis_by_date,
    get_limit_up_analysis_history,
    snapshot_limit_up_analysis_data,
    start_analysis_task,
)

router = APIRouter(tags=["limit_up_analysis"])

logger = logging.getLogger(__name__)


@router.get("/limit-up/analysis")
def query_limit_up_analysis(
    trade_date: str | None = None,
    board: str | None = None,
    stock_type: str | None = None,
    phase: str | None = None,
):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    return get_limit_up_analysis_by_date(trade_date, board=board, stock_type=stock_type, phase=phase)


@router.get("/limit-up/analysis/history")
def limit_up_analysis_history(limit: int = Query(default=20, le=100), offset: int = Query(default=0, ge=0)):
    items, total = get_limit_up_analysis_history(limit, offset)
    return {"items": items, "total": total}


@router.get("/limit-up/analysis/task-status")
def analysis_task_status(trade_date: str | None = None, phase: str = "close"):
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    return get_analysis_task_status(date, phase)


@router.post("/limit-up/analysis/snapshot")
def trigger_snapshot(phase: str = "close"):
    return snapshot_limit_up_analysis_data(trigger="manual", phase=phase)


@router.post("/limit-up/analysis/generate")
def trigger_generate(trade_date: str | None = None, phase: str = "close"):
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    try:
        result = start_analysis_task(date, phase=phase)
        if result.get("already_running"):
            return {"success": False, "already_running": True, "message": "已有分析任务在运行中", "data": result}
        if result.get("no_data"):
            return {"success": False, "no_data": True, "message": "当日无待分析数据，请先采集数据", "data": result}
        return {"success": True, "message": "涨停分析任务已启动", "data": result}
    except Exception as e:
        logger.error("启动涨停分析任务失败: %s", e, exc_info=True)
        return {"success": False, "message": str(e)}
