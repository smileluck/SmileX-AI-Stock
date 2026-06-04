from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market import router as market_router
from app.api.news import router as news_router
from app.api.ai_config import router as ai_config_router
from app.database import init_db
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.services.news_sync import sync_all
from app.services.ai_config import seed_from_env

SYNC_INTERVAL_SECONDS = 300


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_from_env()
    start_scheduler()
    from app.services.scheduler import add_job
    add_job(lambda: sync_all(trigger="scheduled"), job_id="news_sync", seconds=SYNC_INTERVAL_SECONDS)
    yield
    shutdown_scheduler()


app = FastAPI(title="SmileX AI Stock", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")
app.include_router(ai_config_router, prefix="/api/v1")
