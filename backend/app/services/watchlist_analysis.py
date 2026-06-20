"""自选股买入时机分析（早盘 / 收盘）。

参考 limit_up_analysis 的异步批处理范式：
- 取所有 watching 关注股
- 每只股拼紧凑 JSON context（近 10 日 K 线 + 近 5 日主力净流入 + add_price + 当日 spot）
- 分批 6 只/次调 llm.analysis_chat
- 解析 JSON 数组、INSERT OR REPLACE 到 watchlist_analysis
"""
import json
import logging
import threading
from datetime import datetime

from app.database import get_connection
from app.services import llm
from app.services.stock_daily import _fetch_one_stock_spot

logger = logging.getLogger(__name__)

BATCH_SIZE = 6

_tasks_lock = threading.Lock()
_running_tasks: dict[tuple[str, str], dict] = {}


_SYSTEM_PROMPT = """你是 A 股买点分析师，专注于判断自选股的买入时机。

基于「添加价 + 近期 K 线 + 资金流」给出每只股票的买入建议。

严格输出 JSON 数组，每个元素 schema：
{
  "code": "6位股票代码",
  "name": "股票名称",
  "action": "buy | wait | avoid",
  "buy_low": 建议买入区间下沿（数字）,
  "buy_high": 建议买入区间上沿（数字）,
  "support": 关键支撑位（数字）,
  "resistance": 关键阻力位（数字）,
  "confidence": 0.0-1.0,
  "reason": "30 字内的核心理由"
}

判断原则：
- buy：技术面回踩支撑、资金面持续流入、距添加价仍有空间
- wait：方向不明、量能不足、等待突破或回踩
- avoid：已大幅高于添加价且见顶信号明显、资金大幅流出、跌破支撑

不要输出 JSON 数组以外的任何内容、注释或 markdown 围栏。"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 数据准备
# ---------------------------------------------------------------------------

def _fetch_watching_stocks() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT code, name, add_price, add_date
               FROM watchlist_stock
               WHERE status = 'watching'
               ORDER BY sort_order, created_at"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _fetch_recent_kline(code: str, days: int = 10) -> list[dict]:
    """近 N 日 K 线：watchlist_stock_daily 优先，不足补 stock_daily。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT trade_date AS d, high AS h, low AS l, close AS c,
                      main_net_inflow AS m, turnover_rate AS t
               FROM watchlist_stock_daily
               WHERE code = ?
               ORDER BY trade_date DESC LIMIT ?""",
            (code, days),
        ).fetchall()
        wsd_dates = {r["d"] for r in rows}
        if len(rows) < days:
            need = days - len(rows)
            extra = conn.execute(
                """SELECT trade_date AS d, high AS h, low AS l, close AS c,
                          main_net_inflow AS m, turnover_rate AS t
                   FROM stock_daily
                   WHERE code = ? AND trade_date NOT IN (%s)
                   ORDER BY trade_date DESC LIMIT ?"""
                % (",".join("?" for _ in wsd_dates) if wsd_dates else "''",),
                (code, *wsd_dates, need) if wsd_dates else (code, need),
            ).fetchall()
            rows = list(rows) + list(extra)
    finally:
        conn.close()

    rows.sort(key=lambda r: r["d"])
    return [
        {"d": r["d"], "h": r["h"], "l": r["l"], "c": r["c"], "m": r["m"], "t": r["t"]}
        for r in rows
    ]


def _build_stock_context(stock: dict, today: str, phase: str) -> dict:
    """构造单只股的紧凑 context（dict，最终 json.dumps 注入 prompt）。"""
    code = stock["code"]
    kline = _fetch_recent_kline(code, days=10)
    inflow_5d = [k["m"] for k in kline[-5:] if k.get("m") is not None]

    today_spot = None
    try:
        today_spot = _fetch_one_stock_spot(code)
    except Exception:
        logger.warning("fetch spot failed during analysis: %s", code, exc_info=True)

    return {
        "code": code,
        "name": stock.get("name") or "",
        "add_price": stock.get("add_price"),
        "add_date": stock.get("add_date"),
        "phase": phase,
        "today": {
            "open": today_spot.get("open") if today_spot else None,
            "high": today_spot.get("high") if today_spot else None,
            "low": today_spot.get("low") if today_spot else None,
            "close": today_spot.get("close") if today_spot else None,
            "prev_close": today_spot.get("prev_close") if today_spot else None,
            "change_pct": today_spot.get("change_pct") if today_spot else None,
            "amount": today_spot.get("amount") if today_spot else None,
            "main_net_inflow": today_spot.get("main_net_inflow") if today_spot else None,
            "turnover_rate": today_spot.get("turnover_rate") if today_spot else None,
        } if today_spot else None,
        "kline_10d": kline,
        "inflow_5d": inflow_5d,
    }


def _build_batch_user_message(batch_ctx: list[dict], phase: str) -> str:
    """根据 phase 选择关注点，把整批 context 压成紧凑 JSON。"""
    if phase == "morning":
        focus = (
            "[早盘买点分析]\n"
            "重点关注：\n"
            "- 竞价/开盘强弱（开盘价 vs 昨收）\n"
            "- 是否回踩关键支撑位\n"
            "- 距添加价（add_price）涨跌幅是否合理\n"
            "- 近 10 日高低价区间内的相对位置\n"
        )
    else:
        focus = (
            "[收盘买点分析]\n"
            "重点关注：\n"
            "- 当日量价配合（成交额、换手率）\n"
            "- 是否有效突破阻力位或跌破支撑位\n"
            "- 主力净流入方向（inflow_5d 趋势）\n"
            "- 累计涨跌幅（今日 close vs add_price）\n"
            "- 是否出现见顶信号（高位放量、长上影等）\n"
        )
    return focus + "数据：\n" + json.dumps(batch_ctx, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 结果落库
# ---------------------------------------------------------------------------

def _save_results(trade_date: str, phase: str, analyses: list[dict], model_used: str) -> int:
    if not analyses:
        return 0
    now = _now()
    conn = get_connection()
    try:
        updated = 0
        for a in analyses:
            if not isinstance(a, dict):
                continue
            code = str(a.get("code") or "").strip()
            if not code:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO watchlist_analysis
                   (trade_date, phase, code, name, analysis_text, suggested_action,
                    buy_low, buy_high, support_price, resistance_price,
                    confidence, reason, model_used, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'done', ?, ?)""",
                (
                    trade_date, phase, code,
                    a.get("name", ""),
                    json.dumps(a, ensure_ascii=False),
                    (a.get("action") or "").strip().lower(),
                    a.get("buy_low"),
                    a.get("buy_high"),
                    a.get("support"),
                    a.get("resistance"),
                    float(a.get("confidence") or 0),
                    a.get("reason", ""),
                    model_used,
                    now, now,
                ),
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 异步任务
# ---------------------------------------------------------------------------

def get_watchlist_analysis_task_status(trade_date: str, phase: str) -> dict:
    key = (trade_date, phase)
    with _tasks_lock:
        task = _running_tasks.get(key)
        if not task:
            return {
                "active": False, "status": "idle", "trade_date": trade_date, "phase": phase,
                "started_at": None, "finished_at": None, "total": 0, "done": 0, "error": None,
            }
        return {
            "active": task.get("active", False),
            "status": task.get("status", "idle"),
            "trade_date": trade_date, "phase": phase,
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "total": task.get("total", 0),
            "done": task.get("done", 0),
            "error": task.get("error"),
        }


def _worker(trade_date: str, phase: str, stocks: list[dict]) -> None:
    """后台线程：分批构造 context、调 LLM、落库、更新进度。"""
    key = (trade_date, phase)
    total = len(stocks)
    done = 0
    model_used = ""
    try:
        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["status"] = "running"

        for i in range(0, total, BATCH_SIZE):
            batch = stocks[i:i + BATCH_SIZE]
            batch_ctx = []
            for s in batch:
                try:
                    batch_ctx.append(_build_stock_context(s, trade_date, phase))
                except Exception:
                    logger.exception("build context failed: %s", s.get("code"))

            if not batch_ctx:
                done += len(batch)
                continue

            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_batch_user_message(batch_ctx, phase)},
            ]
            try:
                response = llm.analysis_chat(
                    messages, response_format={"type": "json_object"}
                )
                if not model_used:
                    model_used = llm.get_model_for_function("analysis")
                analyses = llm.parse_json_response(response, expect="array")
                _save_results(trade_date, phase, analyses, model_used)
                logger.info(
                    "watchlist %s batch %d/%d: %d stocks analyzed",
                    phase, i // BATCH_SIZE + 1, (total + BATCH_SIZE - 1) // BATCH_SIZE,
                    len(analyses) if isinstance(analyses, list) else 0,
                )
            except Exception:
                logger.exception(
                    "watchlist %s batch failed (trade_date=%s, offset=%d)", phase, trade_date, i
                )

            done += len(batch)
            with _tasks_lock:
                if key in _running_tasks:
                    _running_tasks[key]["done"] = done

        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["active"] = False
                _running_tasks[key]["status"] = "completed"
                _running_tasks[key]["finished_at"] = _now()
        logger.info("watchlist %s analysis done: %d stocks", phase, total)
    except Exception as e:
        logger.exception("watchlist %s analysis worker crashed", phase)
        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["active"] = False
                _running_tasks[key]["status"] = "failed"
                _running_tasks[key]["error"] = str(e)
                _running_tasks[key]["finished_at"] = _now()


def start_watchlist_analysis_task(trade_date: str, phase: str) -> dict:
    """立即启动后台分析任务。重复触发同 date+phase 时复用。"""
    if phase not in ("morning", "close"):
        raise ValueError(f"phase must be morning or close, got {phase}")
    key = (trade_date, phase)
    with _tasks_lock:
        existing = _running_tasks.get(key)
        if existing and existing.get("active"):
            return {
                "started": False, "already_running": True,
                "trade_date": trade_date, "phase": phase,
                "total": existing.get("total", 0),
                "done": existing.get("done", 0),
            }

    stocks = _fetch_watching_stocks()
    if not stocks:
        return {
            "started": False, "no_data": True,
            "trade_date": trade_date, "phase": phase,
            "total": 0, "done": 0,
        }

    with _tasks_lock:
        _running_tasks[key] = {
            "active": True, "status": "running",
            "started_at": _now(), "finished_at": None,
            "total": len(stocks), "done": 0, "error": None,
        }

    t = threading.Thread(target=_worker, args=(trade_date, phase, stocks), daemon=True)
    t.start()
    logger.info("Started watchlist analysis %s for %s: %d stocks", phase, trade_date, len(stocks))
    return {
        "started": True, "already_running": False,
        "trade_date": trade_date, "phase": phase,
        "total": len(stocks), "done": 0,
    }


def generate_watchlist_analysis(trade_date: str | None = None, phase: str = "close") -> dict:
    """scheduler 同步入口：触发并等待完成。"""
    if not trade_date:
        trade_date = _today()
    key = (trade_date, phase)

    with _tasks_lock:
        existing = _running_tasks.get(key)
        if not (existing and existing.get("active")):
            start_watchlist_analysis_task(trade_date, phase)

    import time
    while True:
        with _tasks_lock:
            task = _running_tasks.get(key)
            if not task or not task.get("active"):
                break
        time.sleep(2)

    return list_watchlist_analysis(trade_date, phase=phase)


def list_watchlist_analysis(
    trade_date: str | None = None,
    phase: str | None = None,
    code: str | None = None,
    limit: int = 200,
) -> dict:
    """查询分析结果。trade_date 缺省取最新。"""
    conn = get_connection()
    try:
        if trade_date is None:
            row = conn.execute(
                "SELECT MAX(trade_date) AS d FROM watchlist_analysis"
            ).fetchone()
            trade_date = row["d"] if row and row["d"] else None

        if not trade_date:
            return {"items": [], "total": 0, "trade_date": None}

        sql = ("SELECT * FROM watchlist_analysis WHERE trade_date = ?")
        params: list = [trade_date]
        if phase:
            sql += " AND phase = ?"
            params.append(phase)
        if code:
            sql += " AND code = ?"
            params.append(code)
        sql += " ORDER BY CASE suggested_action WHEN 'buy' THEN 0 WHEN 'wait' THEN 1 ELSE 2 END, confidence DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    items = [dict(r) for r in rows]
    return {"items": items, "total": len(items), "trade_date": trade_date}
