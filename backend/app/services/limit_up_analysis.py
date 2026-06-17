import json
import logging
import threading
from datetime import datetime

import akshare as ak

from app.database import get_connection
from app.services import llm
from app.services.stock import _classify_board, _parse_float, _round2

logger = logging.getLogger(__name__)

BATCH_SIZE = 10


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------

def _fetch_broken_limit_from_db(date: str) -> list[dict]:
    """Fallback: infer broken limit-up stocks from stock_daily."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT code, name, close, high, prev_close, change_pct, amount, turnover_rate, volume
            FROM stock_daily
            WHERE trade_date = ?
              AND change_pct < 9.9
              AND prev_close > 0
              AND high >= prev_close * 1.095
            ORDER BY change_pct DESC
            LIMIT 50
            """,
            (date,),
        ).fetchall()
        return [
            {
                "code": r["code"],
                "name": r["name"],
                "price": r["close"],
                "change_pct": r["change_pct"],
                "limit_up_amount": None,
                "turnover_rate": r["turnover_rate"],
                "amount": r["amount"],
                "first_limit_up_time": None,
                "last_limit_up_time": None,
                "limit_up_times": 1,
                "sector": "",
                "board": _classify_board(r["code"]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def _has_analysis_snapshot(trade_date: str, phase: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM limit_up_analysis WHERE trade_date = ? AND phase = ? LIMIT 1",
            (trade_date, phase),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def fetch_broken_limit_stocks(date: str) -> list[dict]:
    """Fetch broken limit-up stocks (炸板股) via akshare, fallback to DB inference."""
    ak_date = date.replace("-", "")
    try:
        df = ak.stock_zt_pool_zbgc_em(date=ak_date)
        if df is not None and not df.empty:
            items = []
            for _, row in df.iterrows():
                code = str(row.get("代码", ""))
                items.append({
                    "code": code,
                    "name": str(row.get("名称", "")),
                    "price": _parse_float(row.get("最新价")),
                    "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
                    "limit_up_amount": _parse_float(row.get("封板资金")),
                    "turnover_rate": _round2(_parse_float(row.get("换手率"))),
                    "amount": _parse_float(row.get("成交额")),
                    "first_limit_up_time": str(row.get("首次封板时间", "")) or None,
                    "last_limit_up_time": str(row.get("最后封板时间", "")) or None,
                    "limit_up_times": int(_parse_float(row.get("连板数")) or 1),
                    "sector": str(row.get("所属行业", "")) if row.get("所属行业") else "",
                    "board": _classify_board(code),
                })
            return items
    except Exception:
        logger.warning("akshare stock_zt_pool_zbgc_em failed for %s, trying DB fallback", date, exc_info=True)

    return _fetch_broken_limit_from_db(date)


def snapshot_limit_up_analysis_data(trade_date: str | None = None, trigger: str = "manual", phase: str = "close") -> dict:
    """Fetch limit-up + broken-limit stocks and persist to limit_up_analysis table."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    from app.services.stock import fetch_limit_up_stocks
    limit_up_items = fetch_limit_up_stocks(trade_date)
    for item in limit_up_items:
        item["stock_type"] = "limit_up"

    broken_items = fetch_broken_limit_stocks(trade_date)
    for item in broken_items:
        item["stock_type"] = "broken"

    all_items = limit_up_items + broken_items
    if not all_items:
        return {"trade_date": trade_date, "item_count": 0, "success": True, "message": "当日无涨停/炸板股或非交易日"}

    conn = get_connection()
    try:
        conn.execute("DELETE FROM limit_up_analysis WHERE trade_date = ? AND phase = ?", (trade_date, phase))
        conn.executemany(
            """INSERT INTO limit_up_analysis
               (trade_date, code, name, price, change_pct, turnover_rate, amount,
                limit_up_times, sector, board, stock_type,
                first_limit_up_time, last_limit_up_time, limit_up_amount,
                status, phase, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    trade_date, i["code"], i["name"], i["price"], i["change_pct"],
                    i["turnover_rate"], i["amount"], i.get("limit_up_times", 1),
                    i.get("sector", ""), i.get("board", ""), i["stock_type"],
                    i.get("first_limit_up_time"), i.get("last_limit_up_time"),
                    i.get("limit_up_amount"),
                    "pending", phase, now, now,
                )
                for i in all_items
            ],
        )
        conn.execute(
            "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            (f"limit_up_analysis_snapshot_{phase}", trigger, json.dumps({"limit_up": len(limit_up_items), "broken": len(broken_items)}),
             len(all_items), "ok", 0, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to snapshot limit-up analysis data")
        return {"trade_date": trade_date, "item_count": 0, "success": False, "message": "快照失败"}
    finally:
        conn.close()

    logger.info("Limit-up analysis snapshot (%s) for %s: %d limit_up + %d broken", phase, trade_date, len(limit_up_items), len(broken_items))
    return {
        "trade_date": trade_date,
        "item_count": len(all_items),
        "limit_up_count": len(limit_up_items),
        "broken_count": len(broken_items),
        "phase": phase,
        "success": True,
        "message": "ok",
    }


# ---------------------------------------------------------------------------
# AI Analysis
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一位资深A股短线交易分析师，专注于涨停板战法研究。请根据以下涨停和炸板股票数据，逐只分析每只股票的涨停原因和明日走势预判。

对每只股票输出以下字段，以 JSON 数组格式：

- code: 股票代码
- name: 股票名称
- ai_reason: 涨停/炸板原因分析（50-100字，分析涨停逻辑、题材驱动因素、资金意图）
- ai_tomorrow_judge: 明日走势预判（50-100字，具体说明可能的走势形态和关键价位）
- ai_tomorrow_prob: 明日继续涨停概率 "high"/"medium"/"low"
- ai_confidence: 判断置信度 0-1
- ai_key_factors: 关键因素列表（2-5个简短标签，如 ["政策利好","连板龙头","板块联动"]）

分析原则：
1. 封板股分析重点：
   - 封板时间：越早封板说明资金越坚决，次日溢价概率越高
   - 连板数：连板股具有龙头辨识度，但也要注意接力风险
   - 封板资金量：封单越大说明多头力量越强
   - 所属板块是否当日热点：主线题材龙头持续性更好
   - 换手率：适度换手(5-15%)最佳，过高说明分歧大，过低可能加速见顶
2. 炸板股分析重点：
   - 炸板时间：尾盘炸板比早盘炸板风险更大
   - 炸板后跌幅：回撤越大说明抛压越重
   - 是否为主线题材：主线题材的炸板股次日可能有反包机会
   - 换手率和成交量：异常放量炸板需警惕
3. 明日预判原则：
   - 首板+早盘封板+主线热点+适度换手 → 次日高开概率大（high）
   - 多连板+主线龙头+缩量 → 可能继续涨停（high）
   - 尾盘封板或多次炸板回封 → 次日震荡概率大（medium）
   - 炸板股+非主线+放量 → 次日低开概率大（low）
   - 炸板股+主线热点+缩量炸板 → 可能反包（medium）

输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


def _fetch_pending_items(trade_date: str, phase: str) -> list[dict]:
    """Read all pending items for the day, ordered by stock_type then amount desc."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, code, name, price, change_pct, turnover_rate, amount, "
            "limit_up_times, sector, board, stock_type, "
            "first_limit_up_time, last_limit_up_time, limit_up_amount "
            "FROM limit_up_analysis WHERE trade_date = ? AND phase = ? AND status = 'pending' "
            "ORDER BY stock_type, amount DESC NULLS LAST",
            (trade_date, phase),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _build_shared_context(trade_date: str, phase_label: str) -> str:
    """Sectors + news shared across all batches (read once, cheap to inline)."""
    parts: list[str] = []
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, change_pct, main_net_inflow, leading_stock "
            "FROM sector_snapshot_item WHERE trade_date = ? AND sector_type = 'industry' "
            "ORDER BY change_pct DESC LIMIT 10",
            (trade_date,),
        ).fetchall()
        if rows:
            lines = ["=== 热门行业 TOP10 ==="]
            for r in rows:
                inflow = (r["main_net_inflow"] or 0) / 1e8
                lines.append(f"  {r['name']}: 涨幅{r['change_pct']}% 主力净流入{inflow:.2f}亿 领涨:{r['leading_stock']}")
            parts.append("\n".join(lines))

        rows = conn.execute(
            "SELECT title, source FROM news WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT 15",
            (trade_date,),
        ).fetchall()
        if rows:
            lines = [f"=== 最新新闻 ({len(rows)}条) ==="]
            for r in rows:
                lines.append(f"  [{r['source']}] {r['title']}")
            parts.append("\n".join(lines))
    finally:
        conn.close()
    return "\n\n".join(parts)


def _format_stock_line(r: dict) -> str:
    amt = (r["amount"] or 0) / 1e8
    return (
        f"  {r['name']}({r['code']}) 价格{r['price']} 涨幅{r['change_pct']}% "
        f"连板{r['limit_up_times']} 换手{r['turnover_rate']}% "
        f"成交额{amt:.2f}亿 封板资金{(r['limit_up_amount'] or 0)/1e8:.2f}亿 "
        f"首封{r.get('first_limit_up_time') or ''} 末封{r.get('last_limit_up_time') or ''} "
        f"行业:{r['sector']} 板块:{r['board']}"
    )


def _build_batch_context(batch: list[dict], trade_date: str, phase_label: str, shared: str) -> str:
    """Build context for one batch of stocks."""
    parts = [f"=== 交易日期: {trade_date} ({phase_label}数据) ===\n"]
    limit_up = [r for r in batch if r["stock_type"] == "limit_up"]
    broken = [r for r in batch if r["stock_type"] == "broken"]
    if limit_up:
        parts.append("=== 封板股 ({n}只) ===\n{body}".format(
            n=len(limit_up), body="\n".join(_format_stock_line(r) for r in limit_up)))
    if broken:
        parts.append("=== 炸板股 ({n}只) ===\n{body}".format(
            n=len(broken), body="\n".join(_format_stock_line(r) for r in broken)))
    if shared:
        parts.append(shared)
    return "\n\n".join(parts)


def _parse_analysis_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    return llm.parse_json_response(text, expect="array")


# ---------------------------------------------------------------------------
# Background task tracking
# ---------------------------------------------------------------------------

_tasks_lock = threading.Lock()
_running_tasks: dict[tuple[str, str], dict] = {}


def get_analysis_task_status(trade_date: str, phase: str) -> dict:
    """Return current progress for an analysis task."""
    key = (trade_date, phase)
    with _tasks_lock:
        task = _running_tasks.get(key)
        if not task:
            return {"active": False, "total": 0, "done": 0, "percent": 0, "phase": phase}
        total = task["total"]
        done = task["done"]
        percent = round(done / total * 100) if total else 0
        return {
            "active": task["active"],
            "total": total,
            "done": done,
            "percent": percent,
            "phase": phase,
            "started_at": task.get("started_at"),
            "error": task.get("error"),
        }


def _save_batch_results(trade_date: str, phase: str, analyses: list[dict], ids_in_batch: list[int]) -> int:
    """Persist batch analysis results. Returns count of rows actually updated with AI fields."""
    if not analyses or not ids_in_batch:
        # Mark these as completed (no AI data) so they don't get re-analyzed
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        try:
            placeholders = ",".join("?" * len(ids_in_batch))
            conn.execute(
                f"UPDATE limit_up_analysis SET status = 'completed', updated_at = ? "
                f"WHERE id IN ({placeholders})",
                [now, *ids_in_batch],
            )
            conn.commit()
        finally:
            conn.close()
        return 0

    analysis_map = {a.get("code", ""): a for a in analyses if a.get("code")}
    model_used = llm.get_model_for_function("analysis")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT id, code FROM limit_up_analysis WHERE id IN ({','.join('?' * len(ids_in_batch))})",
            ids_in_batch,
        ).fetchall()
        updated = 0
        for row in rows:
            a = analysis_map.get(row["code"])
            if not a:
                conn.execute(
                    "UPDATE limit_up_analysis SET status = 'completed', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                continue
            key_factors = a.get("ai_key_factors", [])
            if isinstance(key_factors, list):
                key_factors = json.dumps(key_factors, ensure_ascii=False)
            conn.execute(
                """UPDATE limit_up_analysis SET
                   ai_reason = ?, ai_tomorrow_judge = ?, ai_tomorrow_prob = ?,
                   ai_confidence = ?, ai_key_factors = ?, model_used = ?,
                   status = 'completed', updated_at = ?
                   WHERE id = ?""",
                (
                    a.get("ai_reason", ""),
                    a.get("ai_tomorrow_judge", ""),
                    a.get("ai_tomorrow_prob", ""),
                    _parse_float(a.get("ai_confidence")) or 0,
                    key_factors,
                    model_used,
                    now,
                    row["id"],
                ),
            )
            updated += 1
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _worker(trade_date: str, phase: str, items: list[dict], shared: str):
    """Background worker: split items into batches, call LLM per batch, persist results."""
    key = (trade_date, phase)
    phase_label = "午间" if phase == "midday" else "收盘"
    total = len(items)
    done = 0
    with _tasks_lock:
        _running_tasks[key]["active"] = True

    for i in range(0, total, BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        ids_in_batch = [r["id"] for r in batch]
        context = _build_batch_context(batch, trade_date, phase_label, shared)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]
        try:
            response = llm.function_chat("limit_up_analysis", messages)
            analyses = _parse_analysis_json(response)
            updated = _save_batch_results(trade_date, phase, analyses, ids_in_batch)
            logger.info("Limit-up batch (%s/%s) %s: %d/%d stocks analyzed",
                        phase, trade_date, f"{i//BATCH_SIZE+1}", updated, len(batch))
        except Exception:
            logger.exception("Limit-up batch failed (%s, %s, batch starting at %d)", trade_date, phase, i)
            # mark this batch as completed (no AI data) so it doesn't block progress
            try:
                _save_batch_results(trade_date, phase, [], ids_in_batch)
            except Exception:
                logger.exception("Failed to mark batch as completed after error")

        done += len(batch)
        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["done"] = done

    with _tasks_lock:
        if key in _running_tasks:
            _running_tasks[key]["active"] = False
    logger.info("Limit-up AI analysis done (%s) for %s: %d stocks", phase, trade_date, total)


def start_analysis_task(trade_date: str, phase: str) -> dict:
    """Trigger async batched analysis. Returns immediately with task status."""
    key = (trade_date, phase)
    with _tasks_lock:
        existing = _running_tasks.get(key)
        if existing and existing.get("active"):
            return {
                "started": False,
                "already_running": True,
                "trade_date": trade_date,
                "phase": phase,
                **{k: existing.get(k) for k in ("total", "done")},
            }

    items = _fetch_pending_items(trade_date, phase)
    if not items:
        return {
            "started": False,
            "already_running": False,
            "no_data": True,
            "trade_date": trade_date,
            "phase": phase,
            "total": 0,
            "done": 0,
        }

    shared = _build_shared_context(trade_date, "午间" if phase == "midday" else "收盘")
    with _tasks_lock:
        _running_tasks[key] = {
            "active": True,
            "total": len(items),
            "done": 0,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    t = threading.Thread(target=_worker, args=(trade_date, phase, items, shared), daemon=True)
    t.start()
    logger.info("Started limit-up AI analysis task (%s) for %s: %d pending items", phase, trade_date, len(items))

    return {
        "started": True,
        "already_running": False,
        "trade_date": trade_date,
        "phase": phase,
        "total": len(items),
        "done": 0,
    }


def generate_limit_up_analysis(trade_date: str | None = None, phase: str = "close", refresh_snapshot: bool = False) -> dict:
    """Backward-compat entry point for scheduled jobs. Triggers async task and returns immediately."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    key = (trade_date, phase)
    with _tasks_lock:
        existing = _running_tasks.get(key)
        if existing and existing.get("active"):
            return {
                "started": False,
                "already_running": True,
                "trade_date": trade_date,
                "phase": phase,
                **{k: existing.get(k) for k in ("total", "done")},
            }
    if refresh_snapshot or not _has_analysis_snapshot(trade_date, phase):
        snapshot_result = snapshot_limit_up_analysis_data(trade_date=trade_date, trigger="auto", phase=phase)
        if not snapshot_result.get("success"):
            return {"started": False, "snapshot_failed": True, "trade_date": trade_date, "phase": phase, "message": snapshot_result.get("message")}
    return start_analysis_task(trade_date, phase)


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

def get_limit_up_analysis_by_date(trade_date: str, board: str | None = None, stock_type: str | None = None, phase: str | None = None) -> dict:
    """Get AI analysis results, optionally filtered by board, stock_type and phase."""
    conn = get_connection()
    try:
        conditions = ["trade_date = ?"]
        params: list = [trade_date]
        if board:
            conditions.append("board = ?")
            params.append(board)
        if stock_type:
            conditions.append("stock_type = ?")
            params.append(stock_type)
        if phase:
            conditions.append("phase = ?")
            params.append(phase)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM limit_up_analysis WHERE {where} ORDER BY stock_type, amount DESC NULLS LAST",
            params,
        ).fetchall()
    finally:
        conn.close()

    return {"trade_date": trade_date, "items": [dict(r) for r in rows], "total": len(rows)}


def get_limit_up_analysis_history(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    """Get analysis history across dates (summary per date)."""
    conn = get_connection()
    try:
        total_row = conn.execute(
            "SELECT COUNT(DISTINCT trade_date) as cnt FROM limit_up_analysis"
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        rows = conn.execute(
            """SELECT trade_date,
                      COUNT(*) as total_count,
                      SUM(CASE WHEN stock_type = 'limit_up' THEN 1 ELSE 0 END) as limit_up_count,
                      SUM(CASE WHEN stock_type = 'broken' THEN 1 ELSE 0 END) as broken_count,
                      SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as analyzed_count,
                      MAX(updated_at) as last_updated
               FROM limit_up_analysis
               GROUP BY trade_date
               ORDER BY trade_date DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows], total
