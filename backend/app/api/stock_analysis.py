import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.market import (
    GenerateStockAnalysisRequest,
    GenerateStockAnalysisResponse,
    StockAnalysisItem,
    StockAnalysisResponse,
)
from app.services.stock_analysis import (
    generate_stock_analysis,
    get_latest_stock_analysis,
    get_stock_analysis_detail,
    get_stock_analysis_history,
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


@router.post("/stock/analysis/generate", response_model=GenerateStockAnalysisResponse)
def trigger_stock_analysis(request: GenerateStockAnalysisRequest):
    try:
        result = generate_stock_analysis(request.code, request.trade_date)
        if result.get("status") == "waiting_data":
            return GenerateStockAnalysisResponse(
                success=True, message="数据采集中，请稍后刷新查看", data=result
            )
        return GenerateStockAnalysisResponse(success=True, message="个股分析生成成功", data=result)
    except Exception as e:
        logger.error("生成个股分析失败: %s", e, exc_info=True)
        return GenerateStockAnalysisResponse(success=False, message=str(e))
