import json
import logging
import re
from datetime import datetime

import akshare as ak

from app.database import get_connection
from app.services import llm
from app.services.stock import _classify_board, _parse_float, _round2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------

def fetch_broken_limit_stocks(date: str) -> list[dict]:
    """Fetch broken limit-up stocks (炸板股) via akshare."""
    ak_date = date.replace("-", "")
    try:
        df = ak.stock_zt_pool_zbgc_em(date=ak_date)
        if df is None or df.empty:
            return []
    except Exception:
        logger.warning("akshare stock_zt_pool_zbgc_em failed for %s", date, exc_info=True)
        return []

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


def snapshot_limit_up_analysis_data(trade_date: str | None = None, trigger: str = "manual") -> dict:
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
        conn.execute("DELETE FROM limit_up_analysis WHERE trade_date = ?", (trade_date,))
        conn.executemany(
            """INSERT INTO limit_up_analysis
               (trade_date, code, name, price, change_pct, turnover_rate, amount,
                limit_up_times, sector, board, stock_type,
                first_limit_up_time, last_limit_up_time, limit_up_amount,
                status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    trade_date, i["code"], i["name"], i["price"], i["change_pct"],
                    i["turnover_rate"], i["amount"], i.get("limit_up_times", 1),
                    i.get("sector", ""), i.get("board", ""), i["stock_type"],
                    i.get("first_limit_up_time"), i.get("last_limit_up_time"),
                    i.get("limit_up_amount"),
                    "pending", now, now,
                )
                for i in all_items
            ],
        )
        conn.execute(
            "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            ("limit_up_analysis_snapshot", trigger, json.dumps({"limit_up": len(limit_up_items), "broken": len(broken_items)}),
             len(all_items), "ok", 0, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to snapshot limit-up analysis data")
        return {"trade_date": trade_date, "item_count": 0, "success": False, "message": "快照失败"}
    finally:
        conn.close()

    logger.info("Limit-up analysis snapshot for %s: %d limit_up + %d broken", trade_date, len(limit_up_items), len(broken_items))
    return {
        "trade_date": trade_date,
        "item_count": len(all_items),
        "limit_up_count": len(limit_up_items),
        "broken_count": len(broken_items),
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


def _build_analysis_context(trade_date: str) -> str:
    """Build context text from limit_up_analysis data + sector data + news."""
    parts = [f"=== 交易日期: {trade_date} ===\n"]

    conn = get_connection()
    try:
        # Limit-up stocks
        rows = conn.execute(
            "SELECT code, name, price, change_pct, turnover_rate, amount, "
            "limit_up_times, sector, board, first_limit_up_time, last_limit_up_time, limit_up_amount "
            "FROM limit_up_analysis WHERE trade_date = ? AND stock_type = 'limit_up' "
            "ORDER BY amount DESC NULLS LAST LIMIT 50",
            (trade_date,),
        ).fetchall()

        if rows:
            lines = [f"=== 封板股 ({len(rows)}只) ==="]
            for r in rows:
                amt = (r["amount"] or 0) / 1e8
                lines.append(
                    f"  {r['name']}({r['code']}) 价格{r['price']} 涨幅{r['change_pct']}% "
                    f"连板{r['limit_up_times']} 换手{r['turnover_rate']}% "
                    f"成交额{amt:.2f}亿 封板资金{(r['limit_up_amount'] or 0)/1e8:.2f}亿 "
                    f"首封{r['first_limit_up_time'] or ''} 末封{r['last_limit_up_time'] or ''} "
                    f"行业:{r['sector']} 板块:{r['board']}"
                )
            parts.append("\n".join(lines))

        # Broken limit stocks
        rows = conn.execute(
            "SELECT code, name, price, change_pct, turnover_rate, amount, "
            "limit_up_times, sector, board, first_limit_up_time, last_limit_up_time, limit_up_amount "
            "FROM limit_up_analysis WHERE trade_date = ? AND stock_type = 'broken' "
            "ORDER BY amount DESC NULLS LAST",
            (trade_date,),
        ).fetchall()

        if rows:
            lines = [f"=== 炸板股 ({len(rows)}只) ==="]
            for r in rows:
                amt = (r["amount"] or 0) / 1e8
                lines.append(
                    f"  {r['name']}({r['code']}) 价格{r['price']} 涨幅{r['change_pct']}% "
                    f"连板{r['limit_up_times']} 换手{r['turnover_rate']}% "
                    f"成交额{amt:.2f}亿 封板资金{(r['limit_up_amount'] or 0)/1e8:.2f}亿 "
                    f"首封{r['first_limit_up_time'] or ''} 末封{r['last_limit_up_time'] or ''} "
                    f"行业:{r['sector']} 板块:{r['board']}"
                )
            parts.append("\n".join(lines))

        # Hot sectors
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

        # Recent news
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


def _parse_analysis_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def generate_limit_up_analysis(trade_date: str | None = None) -> dict:
    """Generate AI analysis for all limit-up stocks of the day."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM limit_up_analysis WHERE trade_date = ? AND status = 'completed'",
            (trade_date,),
        ).fetchone()
        if existing["cnt"] > 0:
            rows = conn.execute(
                "SELECT * FROM limit_up_analysis WHERE trade_date = ? ORDER BY stock_type, amount DESC NULLS LAST",
                (trade_date,),
            ).fetchall()
            return {"trade_date": trade_date, "items": [dict(r) for r in rows], "total": len(rows), "status": "cached"}
    finally:
        conn.close()

    context = _build_analysis_context(trade_date)
    if not context or "封板股" not in context and "炸板股" not in context:
        return {"trade_date": trade_date, "items": [], "total": 0, "status": "no_data"}

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]

    try:
        response = llm.analysis_chat(messages)
    except Exception:
        logger.exception("LLM call failed for limit-up analysis")
        return {"trade_date": trade_date, "items": [], "total": 0, "status": "llm_error"}

    analyses = _parse_analysis_json(response)
    if not analyses:
        logger.warning("No analysis parsed from LLM response")
        return {"trade_date": trade_date, "items": [], "total": 0, "status": "parse_error"}

    analysis_map = {}
    for a in analyses:
        code = a.get("code", "")
        if code:
            analysis_map[code] = a

    model_used = llm.get_model_for_function("analysis")
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, code FROM limit_up_analysis WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()

        updated = 0
        for row in rows:
            a = analysis_map.get(row["code"])
            if not a:
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

        for row in rows:
            if row["code"] not in analysis_map:
                conn.execute(
                    "UPDATE limit_up_analysis SET status = 'completed', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )

        conn.commit()

        result_rows = conn.execute(
            "SELECT * FROM limit_up_analysis WHERE trade_date = ? ORDER BY stock_type, amount DESC NULLS LAST",
            (trade_date,),
        ).fetchall()
        items = [dict(r) for r in result_rows]
    except Exception:
        conn.rollback()
        logger.exception("Failed to save limit-up analysis")
        raise
    finally:
        conn.close()

    logger.info("Limit-up AI analysis for %s: %d/%d stocks analyzed", trade_date, updated, len(rows or []))
    return {"trade_date": trade_date, "items": items, "total": len(items), "status": "ok"}


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

def get_limit_up_analysis_by_date(trade_date: str, board: str | None = None, stock_type: str | None = None) -> dict:
    """Get AI analysis results, optionally filtered by board and stock_type."""
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
