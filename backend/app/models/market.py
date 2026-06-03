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
