import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.models.market import (
    SectorAnalysisItem,
    SectorAnalysisResponse,
    GenerateSectorAnalysisRequest,
    GenerateSectorAnalysisResponse,
)
from app.services.sector_analysis import (
    compare_sector_prediction,
    get_latest_sector_analysis,
    get_sector_analysis_by_date,
    get_sector_analysis_history,
    get_sector_analysis_task_status,
    start_sector_analysis_task,
)

router = APIRouter(tags=["sector_analysis"])

logger = logging.getLogger(__name__)


@router.get("/sector/analysis/latest", response_model=SectorAnalysisItem | None)
def latest_sector_analysis(sector_type: str | None = Query(default=None)):
    return get_latest_sector_analysis(sector_type)


@router.get("/sector/analysis/history", response_model=SectorAnalysisResponse)
def sector_analysis_history(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    sector_type: str | None = Query(default=None),
):
    items, total = get_sector_analysis_history(limit, offset, sector_type)
    return SectorAnalysisResponse(items=items, total=total)


@router.get("/sector/analysis/task-status")
def sector_analysis_task_status(trade_date: str | None = None, sector_type: str | None = None):
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    return get_sector_analysis_task_status(date, sector_type)


@router.post("/sector/analysis/generate", response_model=GenerateSectorAnalysisResponse)
def trigger_sector_analysis(request: GenerateSectorAnalysisRequest | None = None):
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    sector_type = request.sector_type if request else None
    try:
        result = start_sector_analysis_task(trade_date, sector_type)
        if result.get("already_running"):
            return GenerateSectorAnalysisResponse(success=True, message="板块分析任务已在运行中", data=result)
        return GenerateSectorAnalysisResponse(success=True, message="板块分析任务已启动", data=result)
    except Exception as e:
        logger.error("启动板块分析任务失败: %s", e, exc_info=True)
        return GenerateSectorAnalysisResponse(success=False, message=str(e))


@router.post("/sector/analysis/review", response_model=GenerateSectorAnalysisResponse)
def trigger_sector_review(request: GenerateSectorAnalysisRequest | None = None):
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    try:
        result = compare_sector_prediction(trade_date)
        return GenerateSectorAnalysisResponse(success=True, message="板块复盘生成成功", data=result)
    except Exception as e:
        logger.error("生成板块复盘失败: %s", e, exc_info=True)
        return GenerateSectorAnalysisResponse(success=False, message=str(e))


@router.get("/sector/analysis/{trade_date}", response_model=SectorAnalysisItem | None)
def sector_analysis_by_date(trade_date: str, sector_type: str = Query(default="industry")):
    result = get_sector_analysis_by_date(trade_date, sector_type)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result
