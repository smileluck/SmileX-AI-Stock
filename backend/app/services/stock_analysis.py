import json
import logging
import re
from datetime import datetime

from app.database import get_connection
from app.services import llm
from app.services.stock import _classify_board, _fetch_one_stock_concepts, _strip_code
from app.services.stock_daily import (
    get_stock_daily_detail,
    snapshot_stock_daily,
    _fetch_one_stock_spot,
    _insert_stock_daily,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位资深A股个股研究分析师。请基于给定的个股行情、资金流、近期走势、题材概念、相关新闻和历史AI记录，对单只股票进行研究分析。

输出要求：
1. 先输出自由文本分析，包含量价结构、资金流、题材/新闻驱动、风险因素和后续观察点
2. 再输出后续走势判断和操作建议
3. 最后输出一个 ```json 代码块，包含结构化结论

JSON 代码块格式如下：
```json
{
  "direction": "up 或 down 或 flat",
  "confidence": 0.0到1.0之间的数字,
  "suggested_action": "watch 或 buy 或 hold 或 avoid",
  "target_price": 0,
  "support_price": 0,
  "resistance_price": 0,
  "risk_level": "low 或 medium 或 high",
  "key_factors": ["因素1", "因素2", "因素3"]
}
```

请明确说明：以上分析仅供研究参考，不构成投资建议。\
"""


def _parse_prediction_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    candidate = m.group(1).strip() if m else text
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _split_analysis_text(text: str) -> tuple[str, str]:
    cleaned = re.sub(r"```(?:json)?\s*\n?.*?```", "", text, flags=re.DOTALL).strip()
    markers = ["走势判断", "后续走势", "操作建议", "后市展望"]
    for marker in markers:
        idx = cleaned.find(marker)
        if idx > 0:
            return cleaned[:idx].strip(), cleaned[idx:].strip()
    return cleaned, ""


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key, default in (("prediction_summary", "{}"), ("stock_data", "{}"), ("context_data", "{}"), ("recent_news", "[]")):
        try:
            d[key] = json.loads(d.get(key) or default)
        except (json.JSONDecodeError, TypeError):
            d[key] = json.loads(default)
    return d


def _recent_daily_rows(code: str, trade_date: str, limit: int = 10) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM stock_daily
               WHERE code = ? AND trade_date <= ?
               ORDER BY trade_date DESC LIMIT ?""",
            (code, trade_date, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _recent_recommendations(code: str, trade_date: str, limit: int = 5) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT trade_date, phase, reason, strategy, target_price, stop_loss_price,
                      risk_level, confidence, score, status, actual_return_pct
               FROM stock_recommendation
               WHERE code = ? AND trade_date <= ?
               ORDER BY trade_date DESC, id DESC LIMIT ?""",
            (code, trade_date, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _recent_limit_up_analysis(code: str, trade_date: str, limit: int = 5) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT trade_date, stock_type, phase, price, change_pct, sector, board,
                      ai_reason, ai_tomorrow_judge, ai_tomorrow_prob, ai_confidence, status
               FROM limit_up_analysis
               WHERE code = ? AND trade_date <= ?
               ORDER BY trade_date DESC, id DESC LIMIT ?""",
            (code, trade_date, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _recent_news(code: str, name: str, limit: int = 10) -> list[dict]:
    keyword = f"%{code}%"
    name_keyword = f"%{name}%" if name else keyword
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT title, source, url, publish_time
               FROM news
               WHERE title LIKE ? OR content LIKE ? OR title LIKE ? OR content LIKE ?
               ORDER BY publish_time DESC LIMIT ?""",
            (keyword, keyword, name_keyword, name_keyword, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _build_context(stock_data: dict) -> tuple[dict, list[dict]]:
    code = stock_data["code"]
    trade_date = stock_data["trade_date"]
    name = stock_data.get("name", "")
    concepts = _fetch_one_stock_concepts(code)
    recent_daily = _recent_daily_rows(code, trade_date)
    recommendations = _recent_recommendations(code, trade_date)
    limit_up_records = _recent_limit_up_analysis(code, trade_date)
    news = _recent_news(code, name)
    context = {
        "concepts": concepts,
        "recent_daily": recent_daily,
        "recent_recommendations": recommendations,
        "recent_limit_up_analysis": limit_up_records,
    }
    return context, news


def _create_pending_record(stock_data: dict, context_data: dict, recent_news: list[dict]) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO stock_analysis
               (trade_date, code, name, board, stock_data, context_data, recent_news, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                stock_data["trade_date"], stock_data["code"], stock_data.get("name", ""),
                stock_data.get("board") or _classify_board(stock_data["code"]),
                json.dumps(stock_data, ensure_ascii=False),
                json.dumps(context_data, ensure_ascii=False),
                json.dumps(recent_news, ensure_ascii=False),
                "pending", now, now,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _update_record(analysis_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [analysis_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE stock_analysis SET {columns} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def _create_waiting_record(code: str, trade_date: str) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    board = _classify_board(code)
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO stock_analysis
               (trade_date, code, name, board, stock_data, context_data, recent_news, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (trade_date, code, "", board, "{}", "{}", "[]", "waiting_data", now, now),
        )
        conn.commit()
        analysis_id = cur.lastrowid
    finally:
        conn.close()

    result = get_stock_analysis_detail(analysis_id)
    if not result:
        raise RuntimeError("创建 waiting_data 记录失败")
    return result


def _run_llm_analysis(stock_data: dict, context_data: dict, news: list[dict], analysis_id: int) -> None:
    """Run LLM analysis and update the record."""
    try:
        payload = {
            "stock_data": stock_data,
            "context_data": context_data,
            "recent_news": news,
        }
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "请分析以下个股数据：\n" + json.dumps(payload, ensure_ascii=False, indent=2)},
        ]
        response_text = llm.function_chat("stock_analysis", messages)
        prediction_summary = _parse_prediction_json(response_text)
        analysis_text, prediction_text = _split_analysis_text(response_text)
        _update_record(
            analysis_id,
            analysis_text=analysis_text,
            prediction_text=prediction_text,
            prediction_summary=json.dumps(prediction_summary, ensure_ascii=False),
            model_used=llm.get_model_for_function("analysis"),
            status="completed",
        )
    except Exception as e:
        logger.error("生成个股分析失败: %s", e, exc_info=True)
        _update_record(analysis_id, analysis_text=str(e), status="failed")
        raise


def generate_stock_analysis(code: str, trade_date: str | None = None) -> dict:
    normalized_code = _strip_code(code.strip().upper())
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    stock_data = get_stock_daily_detail(normalized_code, trade_date)
    if not stock_data:
        # 1. 尝试实时采集单只股票
        stock_data = _fetch_one_stock_spot(normalized_code)
        if stock_data:
            stock_data["trade_date"] = trade_date
            _insert_stock_daily(stock_data, trade_date)
            logger.info("实时采集单只股票数据成功: %s", normalized_code)
        else:
            # 2. 实时采集失败，挂起等待定时任务
            logger.info("实时采集失败，创建 waiting_data 记录: %s", normalized_code)
            waiting_record = _create_waiting_record(normalized_code, trade_date)
            try:
                snapshot_stock_daily(trade_date, trigger="manual")
            except Exception:
                logger.warning("触发全量采集失败", exc_info=True)
            return waiting_record

    context_data, news = _build_context(stock_data)
    analysis_id = _create_pending_record(stock_data, context_data, news)
    _run_llm_analysis(stock_data, context_data, news, analysis_id)

    result = get_stock_analysis_detail(analysis_id)
    if not result:
        raise RuntimeError("个股分析记录保存失败")
    return result


def get_latest_stock_analysis(code: str | None = None) -> dict | None:
    conn = get_connection()
    try:
        if code:
            row = conn.execute(
                """SELECT * FROM stock_analysis WHERE code = ?
                   ORDER BY created_at DESC, id DESC LIMIT 1""",
                (_strip_code(code.strip().upper()),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM stock_analysis ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def get_stock_analysis_history(code: str | None = None, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    params: list = []
    where = ""
    if code:
        where = "WHERE code = ?"
        params.append(_strip_code(code.strip().upper()))

    conn = get_connection()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM stock_analysis {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT * FROM stock_analysis {where}
                ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r) for r in rows], total


def get_stock_analysis_detail(analysis_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM stock_analysis WHERE id = ?", (analysis_id,)).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def process_waiting_stock_analysis(trade_date: str) -> dict:
    """Process all waiting_data stock_analysis records for a given trade_date."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, code, trade_date FROM stock_analysis
               WHERE trade_date = ? AND status = 'waiting_data'""",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    processed = 0
    failed = 0

    for row in rows:
        code = row["code"]
        trade_date = row["trade_date"]
        analysis_id = row["id"]

        stock_data = get_stock_daily_detail(code, trade_date)
        if not stock_data:
            logger.warning("定时任务仍无法获取股票数据: %s %s", code, trade_date)
            failed += 1
            continue

        try:
            context_data, news = _build_context(stock_data)
            _update_record(
                analysis_id,
                stock_data=json.dumps(stock_data, ensure_ascii=False),
                context_data=json.dumps(context_data, ensure_ascii=False),
                recent_news=json.dumps(news, ensure_ascii=False),
                name=stock_data.get("name", ""),
                board=stock_data.get("board") or _classify_board(code),
            )
            _run_llm_analysis(stock_data, context_data, news, analysis_id)
            processed += 1
        except Exception:
            logger.exception("处理 waiting_data 分析失败: %s %s", code, trade_date)
            failed += 1

    return {"processed": processed, "failed": failed, "total": len(rows)}
