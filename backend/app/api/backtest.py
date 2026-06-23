"""量化策略回测 API。"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_connection
from app.services.backtest import data_loader, engine, metrics, strategies

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backtest"])


# ----- Request / Response Models -----

class BacktestRequest(BaseModel):
    strategy_type: str = Field(..., description="morning/midday/afternoon/custom_factor")
    universe: str = Field("main", description="all/main/sh_main/sz_main/gem/star/watchlist")
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    top_n: int = 5
    rebalance: str = "daily"
    stop_loss: float = -0.07
    take_profit: float = 0.15
    commission_bps: float = 2.5
    stamp_duty_bps: float = 1.0
    benchmark: str = "hs300"
    custom_factors: dict[str, float] = Field(default_factory=dict)
    name: str = ""


class BacktestRunMeta(BaseModel):
    id: int
    name: str
    strategy_type: str
    universe: str
    start_date: str
    end_date: str
    status: str
    metrics: dict
    created_at: str
    finished_at: str | None = None


class BacktestRunsResponse(BaseModel):
    items: list[BacktestRunMeta]
    total: int


class BacktestDetailResponse(BaseModel):
    id: int
    name: str
    strategy_type: str
    universe: str
    start_date: str
    end_date: str
    status: str
    params: dict
    metrics: dict
    equity_curve: list[dict]
    trades_summary: dict
    created_at: str
    finished_at: str | None = None


class BacktestTradesResponse(BaseModel):
    items: list[dict]
    total: int


class DataCoverageResponse(BaseModel):
    n_days: int
    n_codes: int
    min_date: str | None
    max_date: str | None
    universe: str
    sufficient: bool


class StrategiesResponse(BaseModel):
    items: list[dict]


class BackfillResponse(BaseModel):
    success: bool
    message: str
    task_id: str | None = None


# ----- In-memory backfill task tracking -----

_backfill_tasks: dict[str, dict] = {}


# ----- Endpoints -----

@router.get("/backtest/strategies", response_model=StrategiesResponse)
def list_strategies_endpoint():
    return StrategiesResponse(items=strategies.list_strategies())


@router.get("/backtest/data-coverage", response_model=DataCoverageResponse)
def data_coverage_endpoint(universe: str = Query("main")):
    cov = data_loader.check_coverage(universe=universe)
    return DataCoverageResponse(**cov)


@router.post("/backtest/runs", response_model=BacktestDetailResponse)
def create_run(req: BacktestRequest):
    """同步执行回测并返回完整结果。"""
    params = engine.BacktestParams(
        strategy_type=req.strategy_type,
        universe=req.universe,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        top_n=req.top_n,
        rebalance=req.rebalance,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        commission_bps=req.commission_bps,
        stamp_duty_bps=req.stamp_duty_bps,
        benchmark=req.benchmark,
        custom_factors=req.custom_factors,
        name=req.name or f"{req.strategy_type}-{req.start_date}~{req.end_date}",
    )

    try:
        raw = engine.run_backtest(params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("backtest failed")
        raise HTTPException(status_code=500, detail=f"backtest failed: {e}")

    m = metrics.compute(raw["equity_curve"], raw["trades"],
                        params.initial_capital, raw["n_days"])

    run_id = _persist_run(params, raw, m, status="done")
    return _build_detail_response(run_id)


@router.get("/backtest/runs", response_model=BacktestRunsResponse)
def list_runs(limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM backtest_run").fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM backtest_run ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        items = [_row_to_meta(r) for r in rows]
        return BacktestRunsResponse(items=items, total=total)
    finally:
        conn.close()


@router.get("/backtest/runs/{run_id}", response_model=BacktestDetailResponse)
def get_run(run_id: int):
    try:
        return _build_detail_response(run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.get("/backtest/runs/{run_id}/trades", response_model=BacktestTradesResponse)
def list_trades(run_id: int, limit: int = Query(100, le=500), offset: int = Query(0, ge=0)):
    conn = get_connection()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM backtest_trade WHERE run_id = ?", (run_id,)
        ).fetchone()["c"]
        rows = conn.execute(
            "SELECT trade_date, code, name, side, price, shares, amount, cost, reason "
            "FROM backtest_trade WHERE run_id = ? "
            "ORDER BY trade_date DESC, id DESC LIMIT ? OFFSET ?",
            (run_id, limit, offset),
        ).fetchall()
        items = [dict(r) for r in rows]
        # 数值转 float 便于前端展示
        for it in items:
            for k in ("price", "amount", "cost"):
                if it.get(k) is not None:
                    it[k] = float(it[k])
            it["shares"] = int(it.get("shares") or 0)
        return BacktestTradesResponse(items=items, total=total)
    finally:
        conn.close()


@router.delete("/backtest/runs/{run_id}")
def delete_run(run_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM backtest_equity WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM backtest_trade WHERE run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM backtest_run WHERE id = ?", (run_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"success": True}
    finally:
        conn.close()


@router.post("/backtest/backfill", response_model=BackfillResponse)
def trigger_backfill(days: int = Query(365, ge=30, le=1000)):
    """触发后台 backfill（全市场），返回 task_id 供前端轮询。"""
    task_id = str(uuid.uuid4())[:8]
    _backfill_tasks[task_id] = {"status": "running", "message": "backfill started", "progress": 0}

    def _bg():
        try:
            from app.services.backfill_daily import backfill_daily, _get_all_market_codes
            codes = _get_all_market_codes()
            _backfill_tasks[task_id]["message"] = f"fetched {len(codes)} codes"
            result = backfill_daily(codes=codes, days=days)
            _backfill_tasks[task_id].update({
                "status": "done",
                "message": f"done: {result.get('processed', 0)}/{result.get('total_codes', 0)}",
                "progress": 100,
                "result": result,
            })
        except Exception as e:
            logger.exception("backfill task failed")
            _backfill_tasks[task_id].update({"status": "failed", "message": str(e)})

    threading.Thread(target=_bg, daemon=True).start()
    return BackfillResponse(
        success=True,
        message=f"backfill started (task_id={task_id}, days={days})",
        task_id=task_id,
    )


@router.get("/backtest/backfill/{task_id}/status")
def backfill_status(task_id: str):
    """查询 backfill 任务进度。"""
    info = _backfill_tasks.get(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="task not found")
    return info


# ----- Persistence helpers -----

def _persist_run(params: engine.BacktestParams, raw: dict, m: dict, *, status: str,
                 error_msg: str = "") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO backtest_run "
            "(name, strategy_type, params_json, universe, start_date, end_date, "
            " status, metrics_json, error_msg, created_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                params.name,
                params.strategy_type,
                json.dumps(params.to_json_dict(), ensure_ascii=False),
                params.universe,
                params.start_date,
                params.end_date,
                status,
                json.dumps(m, ensure_ascii=False),
                error_msg,
                now,
                now if status == "done" else None,
            ),
        )
        run_id = cur.lastrowid

        if status == "done":
            conn.executemany(
                "INSERT INTO backtest_equity "
                "(run_id, trade_date, equity, cash, position_value, benchmark, drawdown) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        e["trade_date"],
                        float(e["equity"]),
                        float(e["cash"]),
                        float(e["position_value"]),
                        float(e["benchmark"]) if e.get("benchmark") is not None else None,
                        float(e["drawdown"]) if e.get("drawdown") is not None else None,
                    )
                    for e in raw["equity_curve"]
                ],
            )
            conn.executemany(
                "INSERT INTO backtest_trade "
                "(run_id, trade_date, code, name, side, price, shares, amount, cost, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id, t["trade_date"], t["code"], t["name"], t["side"],
                        float(t["price"]), int(t["shares"]), float(t["amount"]),
                        float(t["cost"]), t["reason"],
                    )
                    for t in raw["trades"]
                ],
            )
        conn.commit()
        return run_id
    finally:
        conn.close()


def _build_detail_response(run_id: int) -> BacktestDetailResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM backtest_run WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            raise LookupError(f"run {run_id} not found")

        equity = [
            {
                "trade_date": r["trade_date"],
                "equity": float(r["equity"]),
                "cash": float(r["cash"]),
                "position_value": float(r["position_value"]),
                "benchmark": float(r["benchmark"]) if r["benchmark"] is not None else None,
                "drawdown": float(r["drawdown"]) if r["drawdown"] is not None else None,
            }
            for r in conn.execute(
                "SELECT trade_date, equity, cash, position_value, benchmark, drawdown "
                "FROM backtest_equity WHERE run_id = ? ORDER BY trade_date ASC",
                (run_id,),
            ).fetchall()
        ]
        n_trades = conn.execute(
            "SELECT COUNT(*) AS c FROM backtest_trade WHERE run_id = ?", (run_id,)
        ).fetchone()["c"]
        n_buys = conn.execute(
            "SELECT COUNT(*) AS c FROM backtest_trade WHERE run_id = ? AND side='buy'",
            (run_id,),
        ).fetchone()["c"]
        n_sells = conn.execute(
            "SELECT COUNT(*) AS c FROM backtest_trade WHERE run_id = ? AND side='sell'",
            (run_id,),
        ).fetchone()["c"]
        total_cost = conn.execute(
            "SELECT COALESCE(SUM(cost), 0) AS s FROM backtest_trade WHERE run_id = ?",
            (run_id,),
        ).fetchone()["s"]

        return BacktestDetailResponse(
            id=row["id"],
            name=row["name"],
            strategy_type=row["strategy_type"],
            universe=row["universe"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=row["status"],
            params=json.loads(row["params_json"] or "{}"),
            metrics=json.loads(row["metrics_json"] or "{}"),
            equity_curve=equity,
            trades_summary={
                "n_trades": int(n_trades),
                "n_buys": int(n_buys),
                "n_sells": int(n_sells),
                "total_cost": float(total_cost),
            },
            created_at=row["created_at"],
            finished_at=row["finished_at"],
        )
    finally:
        conn.close()


def _row_to_meta(row) -> BacktestRunMeta:
    return BacktestRunMeta(
        id=row["id"],
        name=row["name"],
        strategy_type=row["strategy_type"],
        universe=row["universe"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        status=row["status"],
        metrics=json.loads(row["metrics_json"] or "{}"),
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )
