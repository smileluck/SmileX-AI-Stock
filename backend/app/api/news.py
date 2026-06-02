from fastapi import APIRouter, Query

from app.models.news import NewsResponse, SourceInfo, SyncResponse, SyncLogResponse
from app.services.news_sync import sync_all, get_news, get_source_stats, get_sync_logs
from app.services.scheduler import get_jobs

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
    results = sync_all(trigger="manual")
    total = sum(r["count"] for r in results)
    return SyncResponse(results=results, total=total)


@router.get("/news/schedule")
def list_schedule():
    return {"jobs": get_jobs()}


@router.get("/news/sync/logs", response_model=SyncLogResponse)
def list_sync_logs(limit: int = Query(default=50, le=200)):
    items = get_sync_logs(limit=limit)
    return SyncLogResponse(items=items, total=len(items))
