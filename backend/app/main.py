from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market import router as market_router
from app.api.market_analysis import router as analysis_router
from app.api.news import router as news_router
from app.api.proxy import router as proxy_router
from app.api.chat import router as chat_router
from app.api.ai_daily_report import router as ai_report_router
from app.api.stock import router as stock_router
from app.api.sector_analysis import router as sector_analysis_router
from app.api.model_config import router as model_config_router
from app.api.strategy import router as strategy_router
from app.api.limit_up_analysis import router as limit_up_analysis_router
from app.database import init_db
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.services.news_sync import sync_all
from app.services.sector import snapshot_sector_data
from app.services.ai_daily_report import generate_ai_daily_report
from app.services.sector_analysis import generate_sector_analysis
from app.services.stock import snapshot_limit_up_data, generate_recommendations, update_morning_performance, update_recommendation_performance
from app.services.limit_up_analysis import snapshot_limit_up_analysis_data, generate_limit_up_analysis

SYNC_INTERVAL_SECONDS = 300


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.services.strategy import seed_default_strategies
    seed_default_strategies()
    start_scheduler()
    from app.services.scheduler import add_job
    from app.services.market_analysis import generate_daily_analysis
    add_job(lambda: sync_all(trigger="scheduled"), job_id="news_sync", seconds=SYNC_INTERVAL_SECONDS)
    add_job(
        lambda: generate_daily_analysis(datetime.now().strftime("%Y-%m-%d")),
        job_id="daily_market_analysis",
        cron="15 15 * * 1-5",
    )
    add_job(
        lambda: snapshot_sector_data(trigger="scheduled"),
        job_id="sector_snapshot",
        cron="20 15 * * 1-5",
    )
    add_job(
        lambda: generate_ai_daily_report(datetime.now().strftime("%Y-%m-%d")),
        job_id="ai_daily_report",
        cron="25 15 * * 1-5",
    )
    add_job(
        lambda: generate_sector_analysis(datetime.now().strftime("%Y-%m-%d")),
        job_id="sector_ai_analysis",
        cron="0 16 * * 1-5",
    )
    add_job(
        lambda: generate_sector_analysis(datetime.now().strftime("%Y-%m-%d")),
        job_id="sector_ai_analysis_sunday",
        cron="0 21 * * 0",
    )
    add_job(
        lambda: snapshot_limit_up_data(trigger="scheduled"),
        job_id="limit_up_snapshot",
        cron="30 15 * * 1-5",
    )
    add_job(
        lambda: generate_recommendations(phase="morning"),
        job_id="stock_recommendation_morning",
        cron="26 9 * * 1-5",
    )
    add_job(
        lambda: generate_recommendations(phase="midday"),
        job_id="stock_recommendation_midday",
        cron="25 11 * * 1-5",
    )

    def _review_rec_job():
        trade_date = datetime.now().strftime("%Y-%m-%d")
        try:
            update_morning_performance(trade_date)
        except Exception:
            pass
        try:
            update_recommendation_performance(trade_date, phase="midday")
        except Exception:
            pass
        return generate_recommendations(trade_date, phase="review")

    add_job(
        _review_rec_job,
        job_id="stock_recommendation_review",
        cron="35 15 * * 1-5",
    )
    add_job(
        lambda: snapshot_limit_up_analysis_data(trigger="scheduled"),
        job_id="limit_up_analysis_snapshot",
        cron="36 15 * * 1-5",
    )
    add_job(
        lambda: generate_limit_up_analysis(datetime.now().strftime("%Y-%m-%d")),
        job_id="limit_up_ai_analysis",
        cron="45 15 * * 1-5",
    )
    yield
    shutdown_scheduler()


app = FastAPI(title="SmileX AI Stock", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(news_router, prefix="/api/v1")
app.include_router(proxy_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(ai_report_router, prefix="/api/v1")
app.include_router(stock_router, prefix="/api/v1")
app.include_router(sector_analysis_router, prefix="/api/v1")
app.include_router(model_config_router, prefix="/api/v1")
app.include_router(strategy_router, prefix="/api/v1")
app.include_router(limit_up_analysis_router, prefix="/api/v1")
