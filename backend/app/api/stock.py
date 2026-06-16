from datetime import datetime

from fastapi import APIRouter, Query

from app.models.market import (
    StockOverviewResponse,
    LimitUpResponse,
    RecommendationListResponse,
    GenerateRecommendationResponse,
    GenerateRecommendationRequest,
    RefreshRecommendationPriceRequest,
    RecommendationTaskStatus,
)
from app.services.stock import (
    get_stock_overview,
    get_limit_up_by_date,
    snapshot_limit_up_data,
    get_recommendations_by_date,
    get_recommendation_history,
    get_recommendation_task_status,
    start_recommendation_task,
    update_recommendation_performance,
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
def stock_recommendations(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    phase: str | None = Query(default=None, description="morning or afternoon"),
):
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    items = get_recommendations_by_date(trade_date, phase)
    return RecommendationListResponse(items=items, total=len(items))


@router.get("/stock/recommendation/history", response_model=RecommendationListResponse)
def recommendation_history(limit: int = Query(default=50, le=200), offset: int = Query(default=0, ge=0)):
    items, total = get_recommendation_history(limit, offset)
    return RecommendationListResponse(items=items, total=total)


@router.get("/stock/recommendation/task-status", response_model=RecommendationTaskStatus)
def recommendation_task_status(
    trade_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    phase: str = Query(default="review", description="morning/midday/review/afternoon"),
):
    """查询推荐生成任务进度，供前端轮询。"""
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    return get_recommendation_task_status(date, phase)


@router.post("/stock/recommendation/refresh-price", response_model=RecommendationListResponse)
def refresh_recommendation_prices(request: RefreshRecommendationPriceRequest | None = None):
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    phase = (request.phase if request else None) or "morning"
    update_recommendation_performance(trade_date, phase=phase)
    items = get_recommendations_by_date(trade_date, phase)
    return RecommendationListResponse(items=items, total=len(items))


@router.post("/stock/recommendation/generate", response_model=GenerateRecommendationResponse)
def trigger_recommendation_generation(request: GenerateRecommendationRequest | None = None):
    """立即启动后台推荐生成任务，不等结果直接返回。

    前端用 GET /stock/recommendation/task-status 轮询进度。
    """
    trade_date = (request.trade_date if request else None) or datetime.now().strftime("%Y-%m-%d")
    phase = (request.phase if request else None) or "afternoon"
    try:
        result = start_recommendation_task(trade_date, phase)
        phase_label = {"morning": "早盘", "midday": "午盘", "review": "收盘复盘", "afternoon": "午后"}.get(phase, phase)
        if result.get("already_running"):
            return GenerateRecommendationResponse(
                success=False,
                message=f"{trade_date} 已有{phase_label}推荐任务在运行，请稍后查询进度",
            )
        return GenerateRecommendationResponse(
            success=True,
            message=f"{phase_label}推荐任务已启动（{trade_date}），可在进度条查看实时状态",
        )
    except Exception as e:
        return GenerateRecommendationResponse(success=False, message=str(e))
