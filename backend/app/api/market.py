from fastapi import APIRouter

from app.models.market import MarketOverviewResponse
from app.services.market import get_market_overview

router = APIRouter(tags=["market"])


@router.get("/market/overview", response_model=MarketOverviewResponse)
def market_overview():
    return get_market_overview()
