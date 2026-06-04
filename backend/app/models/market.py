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


class MarketAnalysisItem(BaseModel):
    id: int
    trade_date: str
    analysis_text: str
    prediction_text: str
    prediction_summary: dict
    actual_data: dict
    review_text: str
    model_used: str
    status: str
    created_at: str
    updated_at: str


class MarketAnalysisResponse(BaseModel):
    items: list[MarketAnalysisItem]
    total: int


class GenerateAnalysisRequest(BaseModel):
    trade_date: str | None = None


class GenerateAnalysisResponse(BaseModel):
    success: bool
    message: str
    data: MarketAnalysisItem | None = None
