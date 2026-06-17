from contextlib import asynccontextmanager
from datetime import datetime
import logging

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
from app.api.stock_daily import router as stock_daily_router
from app.api.stock_analysis import router as stock_analysis_router
from app.api.watchlist import router as watchlist_router
from app.api.tomorrow_strategy import router as tomorrow_strategy_router
from app.database import init_db
from app.services.scheduler import start_scheduler, shutdown_scheduler
from app.services.news_sync import sync_all
from app.services.market import snapshot_market_data
from app.services.sector import snapshot_sector_data
from app.services.ai_daily_report import generate_ai_daily_report
from app.services.sector_analysis import generate_sector_analysis, compare_sector_prediction
from app.services.stock import snapshot_limit_up_data, generate_recommendations, update_morning_performance, update_recommendation_performance
from app.services.limit_up_analysis import snapshot_limit_up_analysis_data, generate_limit_up_analysis
from app.services.stock_daily import snapshot_stock_daily
from app.services.fundamental import snapshot_fundamental_batch
from app.services.capital_detail import snapshot_capital_detail
from app.services.market_analysis import generate_daily_analysis
from app.services.tomorrow_strategy import generate_tomorrow_strategy

SYNC_INTERVAL_SECONDS = 300

logger = logging.getLogger(__name__)


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception("safe_call %s failed", getattr(fn, "__name__", fn))
        return None


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _review_rec_job():
    trade_date = _today()
    _safe_call(update_morning_performance, trade_date)
    _safe_call(update_recommendation_performance, trade_date, phase="midday")
    return generate_recommendations(trade_date, phase="review")


# 任务表：(job_id, cron 或 None, 触发函数, 描述)
# cron=None 表示走 IntervalTrigger（默认 SYNC_INTERVAL_SECONDS）
JOBS: list[dict] = [
    {"id": "news_sync", "cron": None, "fn": lambda: sync_all(trigger="scheduled"), "desc": "新闻聚合抓取"},
    {"id": "daily_market_analysis", "cron": "15 15 * * 1-5", "fn": lambda: generate_daily_analysis(_today()), "desc": "大盘指数AI分析+次日预测"},
    {"id": "market_snapshot_midday", "cron": "0 12 * * 1-5", "fn": lambda: snapshot_market_data(trigger="scheduled"), "desc": "午间行情快照"},
    {"id": "stock_daily_snapshot_midday", "cron": "1 12 * * 1-5", "fn": lambda: snapshot_stock_daily(trigger="scheduled"), "desc": "午间个股日线快照"},
    {"id": "sector_snapshot_midday", "cron": "2 12 * * 1-5", "fn": lambda: snapshot_sector_data(trigger="scheduled"), "desc": "午间板块快照"},
    {"id": "market_snapshot_close", "cron": "10 15 * * 1-5", "fn": lambda: snapshot_market_data(trigger="scheduled"), "desc": "收盘行情快照"},
    {"id": "stock_daily_snapshot_close", "cron": "12 15 * * 1-5", "fn": lambda: snapshot_stock_daily(trigger="scheduled"), "desc": "收盘个股日线快照"},
    {"id": "sector_snapshot_close", "cron": "20 15 * * 1-5", "fn": lambda: snapshot_sector_data(trigger="scheduled"), "desc": "收盘板块快照"},
    {"id": "sector_prediction_review", "cron": "55 15 * * 1-5", "fn": lambda: compare_sector_prediction(_today()), "desc": "板块预测复盘"},
    {"id": "ai_daily_report", "cron": "25 15 * * 1-5", "fn": lambda: generate_ai_daily_report(_today()), "desc": "AI综合收盘报告"},
    {"id": "sector_ai_analysis", "cron": "0 16 * * 1-5", "fn": lambda: generate_sector_analysis(_today()), "desc": "板块AI分析"},
    {"id": "sector_ai_analysis_sunday", "cron": "0 21 * * 0", "fn": lambda: generate_sector_analysis(_today()), "desc": "周日板块AI分析"},
    {"id": "limit_up_snapshot", "cron": "30 15 * * 1-5", "fn": lambda: snapshot_limit_up_data(trigger="scheduled"), "desc": "涨停股快照"},
    {"id": "stock_recommendation_morning", "cron": "26 9 * * 1-5", "fn": lambda: generate_recommendations(phase="morning"), "desc": "早盘AI个股推荐"},
    {"id": "stock_recommendation_midday", "cron": "25 11 * * 1-5", "fn": lambda: generate_recommendations(phase="midday"), "desc": "午盘AI个股推荐"},
    {"id": "stock_recommendation_afternoon", "cron": "45 14 * * 1-5", "fn": lambda: generate_recommendations(phase="afternoon"), "desc": "尾盘AI个股推荐"},
    {"id": "stock_recommendation_review", "cron": "35 15 * * 1-5", "fn": _review_rec_job, "desc": "收盘复盘+推荐"},
    {"id": "limit_up_analysis_snapshot_midday", "cron": "3 12 * * 1-5", "fn": lambda: snapshot_limit_up_analysis_data(trigger="scheduled", phase="midday"), "desc": "午间涨停/炸板采集"},
    {"id": "limit_up_ai_analysis_midday", "cron": "5 12 * * 1-5", "fn": lambda: generate_limit_up_analysis(_today(), phase="midday"), "desc": "午间涨停AI分析"},
    {"id": "limit_up_analysis_snapshot_close", "cron": "0 15 * * 1-5", "fn": lambda: snapshot_limit_up_analysis_data(trigger="scheduled", phase="close"), "desc": "收盘涨停/炸板采集"},
    {"id": "limit_up_ai_analysis_close", "cron": "5 15 * * 1-5", "fn": lambda: generate_limit_up_analysis(_today(), phase="close"), "desc": "收盘涨停AI分析"},
    {"id": "stock_fundamental_snapshot", "cron": "30 16 * * 1-5", "fn": lambda: snapshot_fundamental_batch(trigger="scheduled"), "desc": "个股基本面快照"},
    {"id": "stock_capital_detail_snapshot", "cron": "40 16 * * 1-5", "fn": lambda: snapshot_capital_detail(trigger="scheduled"), "desc": "个股资金流明细快照"},
    {"id": "tomorrow_strategy_generation", "cron": "40 15 * * 1-5", "fn": lambda: generate_tomorrow_strategy(_today()), "desc": "明日策略生成"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.services.strategy import seed_default_strategies
    seed_default_strategies()
    start_scheduler()
    from app.services.scheduler import add_job

    for job in JOBS:
        if job["cron"]:
            add_job(job["fn"], job_id=job["id"], cron=job["cron"])
        else:
            add_job(job["fn"], job_id=job["id"], seconds=SYNC_INTERVAL_SECONDS)
    logger.info("registered %d scheduled jobs", len(JOBS))
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
app.include_router(stock_daily_router, prefix="/api/v1")
app.include_router(stock_analysis_router, prefix="/api/v1")
app.include_router(watchlist_router, prefix="/api/v1")
app.include_router(tomorrow_strategy_router, prefix="/api/v1")
