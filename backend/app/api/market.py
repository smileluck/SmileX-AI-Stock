from fastapi import APIRouter, Query

from app.models.market import (
    MarketOverviewResponse,
    MarketHistoryResponse,
    SectorOverviewResponse,
    SectorCapitalFlowResponse,
)
from app.services.market import get_market_overview, get_market_history
from app.services.sector import get_sector_overview, get_sector_capital_flow

router = APIRouter(tags=["market"])


@router.get("/market/overview", response_model=MarketOverviewResponse)
def market_overview():
    return get_market_overview()


@router.get("/market/history", response_model=MarketHistoryResponse)
def market_history(days: int = Query(default=30, le=365)):
    return get_market_history(days)


@router.get("/market/sector/overview", response_model=SectorOverviewResponse)
def sector_overview():
    return get_sector_overview()


@router.get("/market/sector/capital-flow", response_model=SectorCapitalFlowResponse)
def sector_capital_flow():
    return get_sector_capital_flow()
