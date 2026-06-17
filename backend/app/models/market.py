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


# --- Stock: Limit Up ---

class LimitUpItem(BaseModel):
    code: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    limit_up_amount: float | None = None
    turnover_rate: float | None = None
    volume: float | None = None
    amount: float | None = None
    amplitude: float | None = None
    first_limit_up_time: str | None = None
    last_limit_up_time: str | None = None
    limit_up_times: int = 1
    reason: str = ""
    sector: str = ""
    board: str = ""


class LimitUpResponse(BaseModel):
    trade_date: str
    items: list[LimitUpItem]
    item_count: int
    fetch_time: str


# --- Stock: Hot & Sentiment ---

class DrivingConcept(BaseModel):
    name: str
    change_pct: float


class StockHotItem(BaseModel):
    code: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    hot_rank: int | None = None
    turnover_rate: float | None = None
    amount: float | None = None
    volume: float | None = None
    net_inflow: float | None = None
    industry: str = ""
    driving_concepts: list[DrivingConcept] = []
    concepts: list[str] = []
    source: str = ""


class HotStockSource(BaseModel):
    source: str
    items: list[StockHotItem]


class HotConceptItem(BaseModel):
    name: str
    sector_type: str = ""
    change_pct: float | None = None
    main_net_inflow: float | None = None
    leading_stock: str = ""
    leading_stock_code: str = ""
    leading_stock_change_pct: float | None = None


class MarketSentimentResponse(BaseModel):
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    sentiment_score: float | None = None
    hot_stocks: list[HotStockSource] = []
    hot_concepts: list[HotConceptItem] = []
    fetch_time: str


class StockOverviewResponse(BaseModel):
    sentiment: MarketSentimentResponse
    limit_up: LimitUpResponse
    fetch_time: str


# --- Stock: Recommendation ---

class RecommendationItem(BaseModel):
    id: int
    trade_date: str
    code: str
    name: str
    reason: str
    strategy: str
    target_price: float | None = None
    stop_loss_price: float | None = None
    risk_level: str = "medium"
    current_price: float | None = None
    buy_low: float | None = None
    buy_high: float | None = None
    take_profit_price: float | None = None
    confidence: float = 0.5
    sector: str = ""
    score: float = 0
    model_used: str
    status: str
    actual_return_pct: float | None = None
    actual_exit_date: str | None = None
    phase: str = "afternoon"
    created_at: str
    updated_at: str


class RecommendationListResponse(BaseModel):
    items: list[RecommendationItem]
    total: int


class GenerateRecommendationResponse(BaseModel):
    success: bool
    message: str
    data: list[RecommendationItem] | None = None
    total: int = 0


class GenerateRecommendationRequest(BaseModel):
    trade_date: str | None = None
    phase: str = "afternoon"


class RecommendationTaskStatus(BaseModel):
    active: bool
    status: str
    trade_date: str
    phase: str
    started_at: str | None = None
    finished_at: str | None = None
    stage: str | None = None
    total: int = 0
    error: str | None = None


class RefreshRecommendationPriceRequest(BaseModel):
    trade_date: str | None = None
    phase: str = "morning"


# --- Stock AI Analysis ---

class StockAnalysisItem(BaseModel):
    id: int
    trade_date: str
    code: str
    name: str
    board: str = ""
    analysis_text: str = ""
    prediction_text: str = ""
    prediction_summary: dict = {}
    stock_data: dict = {}
    context_data: dict = {}
    recent_news: list[dict] = []
    model_used: str = ""
    status: str
    created_at: str
    updated_at: str


class StockAnalysisResponse(BaseModel):
    items: list[StockAnalysisItem]
    total: int


class GenerateStockAnalysisRequest(BaseModel):
    code: str
    trade_date: str | None = None


class GenerateStockAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: StockAnalysisItem | None = None


class StockAnalysisTaskStatus(BaseModel):
    active: bool
    status: str
    code: str
    trade_date: str
    started_at: str | None = None
    finished_at: str | None = None
    stage: str | None = None
    analysis_id: int | None = None
    error: str | None = None


# --- Sector AI Analysis ---

class SectorAnalysisItem(BaseModel):
    id: int
    trade_date: str
    sector_type: str
    analysis_text: str
    prediction_text: str = ""
    prediction_summary: dict = {}
    actual_data: dict = {}
    review_text: str = ""
    scored_news: list[dict] = []
    trend_data: dict = {}
    model_used: str
    status: str
    created_at: str
    updated_at: str


class SectorAnalysisResponse(BaseModel):
    items: list[SectorAnalysisItem]
    total: int


class GenerateSectorAnalysisRequest(BaseModel):
    trade_date: str | None = None
    sector_type: str | None = None


class GenerateSectorAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: dict | SectorAnalysisItem | None = None


# --- Tomorrow Strategy ---

class TomorrowStrategyEvent(BaseModel):
    title: str | None = None
    source: str | None = None
    impact: str | None = None


class TomorrowStrategySector(BaseModel):
    rank: int | None = None
    code: str | None = None
    name: str | None = None
    sector_type: str | None = None
    change_pct_today: float | None = None
    streak_up_days: int | None = None
    main_net_inflow_yi: float | None = None
    news_count: int | None = None
    news_avg_score: float | None = None
    top_events: list[TomorrowStrategyEvent] = []
    sustainability: str | None = None
    sustainability_reason: str | None = None
    tomorrow_outlook: str | None = None


class TomorrowStrategyStock(BaseModel):
    sector_code: str | None = None
    sector_name: str | None = None
    code: str | None = None
    name: str | None = None
    role: str | None = None
    entry_logic: str | None = None
    watch_price_low: float | None = None
    watch_price_high: float | None = None
    stop_loss_price: float | None = None
    target_price: float | None = None
    risk_tags: list[str] = []


class TomorrowStrategyAdvice(BaseModel):
    position_level: str | None = None
    style: str | None = None
    market_bias: str | None = None
    risk_warnings: list[str] = []
    actionable_summary: str | None = None


class TomorrowStrategyItem(BaseModel):
    id: int
    trade_date: str
    content_json: dict = {}
    raw_text: str = ""
    sectors_json: list[TomorrowStrategySector] = []
    stocks_json: list[TomorrowStrategyStock] = []
    strategy_json: TomorrowStrategyAdvice = {}
    model_used: str = ""
    status: str
    created_at: str
    updated_at: str


class TomorrowStrategyHistoryItem(BaseModel):
    id: int
    trade_date: str
    status: str
    model_used: str | None = None
    sector_count: int | None = None
    stock_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TomorrowStrategyResponse(BaseModel):
    items: list[TomorrowStrategyHistoryItem]
    total: int


class GenerateTomorrowStrategyResponse(BaseModel):
    success: bool
    message: str
    data: TomorrowStrategyItem | None = None


class TomorrowStrategyTaskStatus(BaseModel):
    active: bool
    status: str
    trade_date: str
    started_at: str | None = None
    finished_at: str | None = None
    stage: str | None = None
    error: str | None = None
