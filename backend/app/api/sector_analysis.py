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
    generate_sector_analysis,
    get_latest_sector_analysis,
    get_sector_analysis_history,
)

router = APIRouter(tags=["sector_analysis"])

logger = logging.getLogger(__name__)


@router.get("/sector/analysis/latest", response_model=SectorAnalysisItem | None)
def latest_sector_analysis():
    return get_latest_sector_analysis()


@router.get("/sector/analysis/history", response_model=SectorAnalysisResponse)
def sector_analysis_history(limit: int = Query(default=20, le=100), offset: int = Query(default=0, ge=0)):
    items, total = get_sector_analysis_history(limit, offset)
    return SectorAnalysisResponse(items=items, total=total)


@router.post("/sector/analysis/generate", response_model=GenerateSectorAnalysisResponse)
def trigger_sector_analysis(request: GenerateSectorAnalysisRequest | None = None):
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    try:
        result = generate_sector_analysis(trade_date)
        return GenerateSectorAnalysisResponse(success=True, message="板块分析生成成功", data=result)
    except Exception as e:
        logger.error("生成板块分析失败: %s", e, exc_info=True)
        return GenerateSectorAnalysisResponse(success=False, message=str(e))
