import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.models.market import (
    MarketAnalysisItem,
    MarketAnalysisResponse,
    GenerateAnalysisRequest,
    GenerateAnalysisResponse,
)
from app.services.market_analysis import (
    generate_daily_analysis,
    get_analysis,
    get_latest_analysis,
    get_analysis_history,
)

router = APIRouter(tags=["market_analysis"])


@router.get("/market/analysis/latest", response_model=MarketAnalysisItem | None)
def latest_analysis():
    return get_latest_analysis()


@router.get("/market/analysis/history", response_model=MarketAnalysisResponse)
def analysis_history(limit: int = Query(default=20, le=100), offset: int = Query(default=0, ge=0)):
    items, total = get_analysis_history(limit, offset)
    return MarketAnalysisResponse(items=items, total=total)


@router.get("/market/analysis/{date}", response_model=MarketAnalysisItem)
def analysis_by_date(date: str):
    result = get_analysis(date)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.post("/market/analysis/generate", response_model=GenerateAnalysisResponse)
def trigger_analysis(request: GenerateAnalysisRequest | None = None):
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    try:
        result = generate_daily_analysis(trade_date)
        return GenerateAnalysisResponse(success=True, message="分析生成成功", data=result)
    except Exception as e:
        logger.error("生成分析失败: %s", e, exc_info=True)
        return GenerateAnalysisResponse(success=False, message=str(e))
