import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.models.market import (
    AiDailyReportItem,
    AiDailyReportResponse,
    GenerateAiReportResponse,
)
from app.services.ai_daily_report import (
    generate_ai_daily_report,
    get_report,
    get_latest_report,
    get_report_history,
)

router = APIRouter(tags=["ai_daily_report"])


@router.get("/ai/report/latest", response_model=AiDailyReportItem | None)
def latest_report():
    return get_latest_report()


@router.get("/ai/report/history", response_model=AiDailyReportResponse)
def report_history(limit: int = Query(default=20, le=100), offset: int = Query(default=0, ge=0)):
    items, total = get_report_history(limit, offset)
    return AiDailyReportResponse(items=items, total=total)


@router.get("/ai/report/{date}", response_model=AiDailyReportItem)
def report_by_date(date: str):
    result = get_report(date)
    if not result:
        raise HTTPException(status_code=404, detail="Report not found")
    return result


@router.post("/ai/report/generate", response_model=GenerateAiReportResponse)
def trigger_report(date: str | None = None):
    trade_date = date or datetime.now().strftime("%Y-%m-%d")
    try:
        result = generate_ai_daily_report(trade_date)
        return GenerateAiReportResponse(success=True, message="报告生成成功", data=result)
    except Exception as e:
        logger.error("生成AI日报失败: %s", e, exc_info=True)
        return GenerateAiReportResponse(success=False, message=str(e))
