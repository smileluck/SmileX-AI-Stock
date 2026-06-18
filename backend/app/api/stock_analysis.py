import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.market import (
    GenerateStockAnalysisRequest,
    GenerateStockAnalysisResponse,
    StockAnalysisItem,
    StockAnalysisResponse,
    StockAnalysisTaskStatus,
)
from app.services.stock_analysis import (
    get_latest_stock_analysis,
    get_stock_analysis_detail,
    get_stock_analysis_history,
    get_stock_analysis_task_status,
    start_stock_analysis_task,
    refresh_stock_data,
)

router = APIRouter(tags=["stock_analysis"])
logger = logging.getLogger(__name__)


@router.get("/stock/analysis/latest", response_model=StockAnalysisItem | None)
def latest_stock_analysis(code: str | None = Query(default=None)):
    return get_latest_stock_analysis(code)


@router.get("/stock/analysis/history", response_model=StockAnalysisResponse)
def stock_analysis_history(
    code: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items, total = get_stock_analysis_history(code, limit, offset)
    return StockAnalysisResponse(items=items, total=total)


@router.get("/stock/analysis/detail/{analysis_id}", response_model=StockAnalysisItem)
def stock_analysis_detail(analysis_id: int):
    result = get_stock_analysis_detail(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/stock/analysis/task-status", response_model=StockAnalysisTaskStatus)
def stock_analysis_task_status(
    code: str = Query(..., description="股票代码"),
    trade_date: str | None = Query(default=None),
):
    """查询单只股票分析任务进度，供前端轮询。

    必须放在 /stock/analysis/detail/{id} 路由之后没问题，但要避免被 /{xx} 形式的路径参数吞掉。
    当前路径 `/stock/analysis/task-status` 与 `/stock/analysis/detail/{analysis_id}` 不冲突。
    """
    return get_stock_analysis_task_status(code, trade_date)


@router.post("/stock/analysis/generate", response_model=GenerateStockAnalysisResponse)
def trigger_stock_analysis(request: GenerateStockAnalysisRequest):
    """立即启动后台分析任务，不等结果直接返回。

    前端用 GET /stock/analysis/task-status?code=xxx 轮询进度。
    """
    try:
        result = start_stock_analysis_task(request.code, request.trade_date)
        if result.get("already_running"):
            return GenerateStockAnalysisResponse(
                success=False,
                message=f"{request.code} 已有分析任务在运行，请稍后查询进度",
            )
        return GenerateStockAnalysisResponse(
            success=True,
            message=f"个股分析任务已启动（{result.get('code')}），可在进度条查看实时状态",
        )
    except Exception as e:
        logger.error("启动个股分析任务失败: %s", e, exc_info=True)
        return GenerateStockAnalysisResponse(success=False, message=str(e))


@router.post("/stock/analysis/refresh-data")
def refresh_stock_data_route(
    code: str = Query(..., description="股票代码"),
    trade_date: str | None = Query(default=None, description="交易日，默认当天"),
):
    """刷新单只股票的行情、基本面、资金明细数据。

    刷新后需重新生成个股分析才能看到最新数据。
    """
    return refresh_stock_data(code, trade_date)
