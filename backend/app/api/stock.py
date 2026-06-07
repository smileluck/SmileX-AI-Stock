from datetime import datetime

from fastapi import APIRouter, Query

from app.models.market import (
    StockOverviewResponse,
    LimitUpResponse,
    RecommendationListResponse,
    GenerateRecommendationResponse,
)
from app.services.stock import (
    get_stock_overview,
    get_limit_up_by_date,
    snapshot_limit_up_data,
    get_recommendations_by_date,
    get_recommendation_history,
    generate_recommendations,
)

router = APIRouter(tags=["stock"])


@router.get("/stock/overview", response_model=StockOverviewResponse)
def stock_overview():
    return get_stock_overview()


@router.get("/stock/limit-up", response_model=LimitUpResponse)
def stock_limit_up(trade_date: str | None = Query(default=None, description="YYYY-MM-DD")):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    return get_limit_up_by_date(trade_date)


@router.post("/stock/limit-up/snapshot")
def trigger_limit_up_snapshot():
    return snapshot_limit_up_data()


@router.get("/stock/recommendation", response_model=RecommendationListResponse)
def stock_recommendations(trade_date: str | None = Query(default=None, description="YYYY-MM-DD")):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    items = get_recommendations_by_date(trade_date)
    return RecommendationListResponse(items=items, total=len(items))


@router.get("/stock/recommendation/history", response_model=RecommendationListResponse)
def recommendation_history(limit: int = Query(default=50, le=200), offset: int = Query(default=0, ge=0)):
    items, total = get_recommendation_history(limit, offset)
    return RecommendationListResponse(items=items, total=total)


@router.post("/stock/recommendation/generate", response_model=GenerateRecommendationResponse)
def trigger_recommendation_generation():
    try:
        result = generate_recommendations()
        return GenerateRecommendationResponse(
            success=True,
            message="推荐生成成功",
            data=result.get("items"),
            total=result.get("total", 0),
        )
    except Exception as e:
        return GenerateRecommendationResponse(success=False, message=str(e))
