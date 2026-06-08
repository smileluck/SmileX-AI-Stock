import logging
from datetime import datetime

from fastapi import APIRouter, Query

from app.services.limit_up_analysis import (
    generate_limit_up_analysis,
    get_limit_up_analysis_by_date,
    get_limit_up_analysis_history,
    snapshot_limit_up_analysis_data,
)

router = APIRouter(tags=["limit_up_analysis"])

logger = logging.getLogger(__name__)


@router.get("/limit-up/analysis")
def query_limit_up_analysis(
    trade_date: str | None = None,
    board: str | None = None,
    stock_type: str | None = None,
):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    return get_limit_up_analysis_by_date(trade_date, board=board, stock_type=stock_type)


@router.get("/limit-up/analysis/history")
def limit_up_analysis_history(limit: int = Query(default=20, le=100), offset: int = Query(default=0, ge=0)):
    items, total = get_limit_up_analysis_history(limit, offset)
    return {"items": items, "total": total}


@router.post("/limit-up/analysis/snapshot")
def trigger_snapshot():
    return snapshot_limit_up_analysis_data(trigger="manual")


@router.post("/limit-up/analysis/generate")
def trigger_generate(trade_date: str | None = None):
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    try:
        result = generate_limit_up_analysis(date)
        return {"success": True, "message": "涨停分析生成成功", "data": result}
    except Exception as e:
        logger.error("生成涨停分析失败: %s", e, exc_info=True)
        return {"success": False, "message": str(e)}
