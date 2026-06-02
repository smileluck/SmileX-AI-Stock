from fastapi import APIRouter, Query

from app.models.news import NewsResponse, SourceInfo, SyncResponse
from app.services.news_sync import sync_all, get_news, get_source_stats

router = APIRouter(tags=["news"])


@router.get("/news", response_model=NewsResponse)
def list_news(source: str = Query(default=""), limit: int = Query(default=100, le=500)):
    items = get_news(source=source, limit=limit)
    return NewsResponse(items=items, total=len(items))


@router.get("/news/sources", response_model=list[SourceInfo])
def list_sources():
    return get_source_stats()


@router.post("/news/sync", response_model=SyncResponse)
def trigger_sync():
    results = sync_all()
    total = sum(r["count"] for r in results)
    return SyncResponse(results=results, total=total)
