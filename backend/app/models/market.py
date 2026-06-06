from pydantic import BaseModel


class IndexItem(BaseModel):
    code: str
    name: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    amount: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    prev_close: float | None = None
    amplitude: float | None = None
    update_time: str | None = None


class MarketOverviewResponse(BaseModel):
    cn_main: list[IndexItem]
    international: list[IndexItem]
    fetch_time: str


class IndexDailyItem(BaseModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float


class IndexHistoryData(BaseModel):
    code: str
    name: str
    records: list[IndexDailyItem]


class MarketHistoryResponse(BaseModel):
    indices: list[IndexHistoryData]
    fetch_time: str


class PredictionIndex(BaseModel):
    predicted_change_pct: float | None = None
    support: float | None = None
    resistance: float | None = None


class PredictionSummary(BaseModel):
    overall_direction: str
    confidence: float
    indices: dict[str, PredictionIndex]
    key_factors: list[str]
    risk_level: str


class ScoredNewsItem(BaseModel):
    title: str
    source: str
    impact_score: int = 5
    impact_category: str = "其他"


class MarketAnalysisItem(BaseModel):
    id: int
    trade_date: str
    analysis_text: str
    prediction_text: str
    prediction_summary: dict
    actual_data: dict
    review_text: str
    scored_news: list[ScoredNewsItem] = []
    model_used: str
    status: str
    created_at: str
    updated_at: str


class MarketAnalysisResponse(BaseModel):
    items: list[MarketAnalysisItem]
    total: int


class SectorItem(BaseModel):
    code: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    change: float | None = None
    volume: float | None = None
    amount: float | None = None
    up_count: float | None = None
    down_count: float | None = None
    flat_count: float | None = None
    leading_stock: str | None = None
    leading_stock_code: str | None = None
    leading_stock_change_pct: float | None = None


class SectorCapitalFlowItem(BaseModel):
    code: str
    name: str
    change_pct: float | None = None
    main_net_inflow: float | None = None
    main_net_inflow_pct: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    medium_net: float | None = None
    small_net: float | None = None


class SectorOverviewResponse(BaseModel):
    industry: list[SectorItem]
    concept: list[SectorItem]
    fetch_time: str


class SectorCapitalFlowResponse(BaseModel):
    industry: list[SectorCapitalFlowItem]
    concept: list[SectorCapitalFlowItem]
    fetch_time: str


class SectorHistoryItem(BaseModel):
    code: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    change: float | None = None
    volume: float | None = None
    amount: float | None = None
    up_count: int | None = None
    down_count: int | None = None
    flat_count: int | None = None
    leading_stock: str | None = None
    leading_stock_code: str | None = None
    leading_stock_change_pct: float | None = None
    main_net_inflow: float | None = None
    main_net_inflow_pct: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    medium_net: float | None = None
    small_net: float | None = None


class SectorHistoryDateResponse(BaseModel):
    trade_date: str
    sector_type: str
    items: list[SectorHistoryItem]
    item_count: int


class SectorAggregatedItem(BaseModel):
    code: str
    name: str
    avg_change_pct: float | None = None
    total_main_net_inflow: float | None = None
    avg_main_net_inflow_pct: float | None = None
    best_change_pct: float | None = None
    worst_change_pct: float | None = None
    trading_days: int = 0


class SectorHistoryRangeResponse(BaseModel):
    start_date: str
    end_date: str
    sector_type: str
    sectors: list[SectorAggregatedItem]


class SectorTrendPoint(BaseModel):
    date: str
    change_pct: float | None = None
    main_net_inflow: float | None = None
    price: float | None = None
    volume: float | None = None


class SectorTrendResponse(BaseModel):
    code: str
    name: str
    sector_type: str
    data: list[SectorTrendPoint]


class SectorDatesResponse(BaseModel):
    dates: list[str]


class SectorSnapshotResponse(BaseModel):
    success: bool
    message: str
    trade_date: str | None = None
    industry_count: int = 0
    concept_count: int = 0


class GenerateAnalysisRequest(BaseModel):
    trade_date: str | None = None


class GenerateAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: MarketAnalysisItem | None = None


class AiDailyReportItem(BaseModel):
    id: int
    trade_date: str
    report_text: str
    market_summary: str
    sector_hot: str
    capital_flow: str
    news_sentiment: str
    outlook: str
    risk_warning: str
    model_used: str
    status: str
    created_at: str
    updated_at: str


class AiDailyReportResponse(BaseModel):
    items: list[AiDailyReportItem]
    total: int


class GenerateAiReportResponse(BaseModel):
    success: bool
    message: str
    data: AiDailyReportItem | None = None
