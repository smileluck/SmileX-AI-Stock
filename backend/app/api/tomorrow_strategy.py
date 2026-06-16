import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.models.market import (
    GenerateTomorrowStrategyResponse,
    TomorrowStrategyHistoryItem,
    TomorrowStrategyItem,
    TomorrowStrategyResponse,
    TomorrowStrategyTaskStatus,
)
from app.services.tomorrow_strategy import (
    get_latest_strategy,
    get_strategy,
    get_strategy_history,
    get_strategy_task_status,
    start_strategy_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tomorrow_strategy"])


@router.get("/tomorrow-strategy/latest", response_model=TomorrowStrategyItem | None)
def latest_strategy():
    return get_latest_strategy()


@router.get("/tomorrow-strategy/history", response_model=TomorrowStrategyResponse)
def strategy_history(limit: int = Query(default=20, le=100), offset: int = Query(default=0, ge=0)):
    items, total = get_strategy_history(limit, offset)
    return TomorrowStrategyResponse(
        items=[TomorrowStrategyHistoryItem(**it) for it in items],
        total=total,
    )


@router.get("/tomorrow-strategy/task-status", response_model=TomorrowStrategyTaskStatus)
def strategy_task_status(date: str | None = None):
    """查询策略生成任务的实时进度，供前端轮询。

    必须放在 /{date} 路径参数路由之前注册，否则会被吞掉。
    """
    trade_date = date or datetime.now().strftime("%Y-%m-%d")
    return get_strategy_task_status(trade_date)


@router.get("/tomorrow-strategy/{date}", response_model=TomorrowStrategyItem)
def strategy_by_date(date: str):
    result = get_strategy(date)
    if not result:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return result


@router.post("/tomorrow-strategy/generate", response_model=GenerateTomorrowStrategyResponse)
def trigger_strategy(date: str | None = None):
    """立即启动后台策略生成任务，不等结果直接返回。

    前端用 GET /tomorrow-strategy/task-status 轮询进度。
    """
    trade_date = date or datetime.now().strftime("%Y-%m-%d")
    try:
        result = start_strategy_task(trade_date)
        if result.get("already_running"):
            return GenerateTomorrowStrategyResponse(
                success=False,
                message=f"{trade_date} 已有策略生成任务在运行，请稍后查询进度",
            )
        return GenerateTomorrowStrategyResponse(
            success=True,
            message=f"明日策略生成任务已启动（{trade_date}），可在进度条查看实时状态",
        )
    except Exception as e:
        logger.error("启动明日策略任务失败: %s", e, exc_info=True)
        return GenerateTomorrowStrategyResponse(success=False, message=str(e))
