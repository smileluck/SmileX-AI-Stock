from pydantic import BaseModel


class NewsItem(BaseModel):
    id: int
    source: str
    title: str
    content: str
    url: str
    publish_time: str | None
    fetch_time: str
    extra: dict


class SourceInfo(BaseModel):
    name: str
    label: str
    count: int
    last_fetch: str | None


class SyncResultItem(BaseModel):
    source: str
    label: str
    count: int
    status: str


class SyncResponse(BaseModel):
    results: list[SyncResultItem]
    total: int


class NewsResponse(BaseModel):
    items: list[NewsItem]
    total: int


class SyncLogItem(BaseModel):
    id: int
    job_id: str
    trigger: str
    results: list[dict]
    total: int
    status: str
    duration: float
    created_at: str


class SyncLogResponse(BaseModel):
    items: list[SyncLogItem]
    total: int
