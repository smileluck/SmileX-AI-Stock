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
