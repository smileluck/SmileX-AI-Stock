from fastapi import APIRouter, Query

from app.models.market import MarketOverviewResponse, MarketHistoryResponse
from app.services.market import get_market_overview, get_market_history

router = APIRouter(tags=["market"])


@router.get("/market/overview", response_model=MarketOverviewResponse)
def market_overview():
    return get_market_overview()


@router.get("/market/history", response_model=MarketHistoryResponse)
def market_history(days: int = Query(default=30, le=365)):
    return get_market_history(days)
