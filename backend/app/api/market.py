from fastapi import APIRouter, Query

from app.models.market import (
    MarketOverviewResponse,
    MarketHistoryResponse,
    SectorOverviewResponse,
    SectorCapitalFlowResponse,
    SectorHistoryDateResponse,
    SectorHistoryRangeResponse,
    SectorTrendResponse,
    SectorDatesResponse,
    SectorSnapshotResponse,
)
from app.services.market import get_market_overview, get_market_history, snapshot_market_data
from app.services.sector import (
    get_sector_overview,
    get_sector_capital_flow,
    snapshot_sector_data,
    get_sector_history_by_date,
    get_sector_history_range,
    get_sector_trend,
    get_sector_dates,
)

router = APIRouter(tags=["market"])


@router.get("/market/overview", response_model=MarketOverviewResponse)
def market_overview():
    return get_market_overview()


@router.get("/market/history", response_model=MarketHistoryResponse)
def market_history(days: int = Query(default=30, le=365)):
    return get_market_history(days)


@router.post("/market/snapshot")
def trigger_market_snapshot():
    return snapshot_market_data()


@router.get("/market/sector/overview", response_model=SectorOverviewResponse)
def sector_overview():
    return get_sector_overview()


@router.get("/market/sector/capital-flow", response_model=SectorCapitalFlowResponse)
def sector_capital_flow():
    return get_sector_capital_flow()


@router.get("/market/sector/history/date", response_model=SectorHistoryDateResponse)
def sector_history_by_date(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    sector_type: str = Query(default="industry", pattern="^(industry|concept)$"),
):
    return get_sector_history_by_date(trade_date, sector_type)


@router.get("/market/sector/history/range", response_model=SectorHistoryRangeResponse)
def sector_history_range(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    sector_type: str = Query(default="industry", pattern="^(industry|concept)$"),
):
    return get_sector_history_range(start_date, end_date, sector_type)


@router.get("/market/sector/history/trend", response_model=SectorTrendResponse)
def sector_trend(
    code: str = Query(..., description="Sector code"),
    sector_type: str = Query(default="industry", pattern="^(industry|concept)$"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
):
    return get_sector_trend(code, sector_type, start_date, end_date)


@router.get("/market/sector/history/dates", response_model=SectorDatesResponse)
def sector_available_dates(
    sector_type: str = Query(default="industry", pattern="^(industry|concept)$"),
    limit: int = Query(default=90, le=365),
):
    return {"dates": get_sector_dates(sector_type, limit)}


@router.post("/market/sector/snapshot", response_model=SectorSnapshotResponse)
def trigger_sector_snapshot():
    return snapshot_sector_data()
