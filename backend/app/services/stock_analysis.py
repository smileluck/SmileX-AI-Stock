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
from app.services.technical_indicators import compute_indicators
from app.services.fundamental import get_latest_fundamental
from app.services.capital_detail import get_latest_capital_detail

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = """\
你是一位资深A股个股分析师，擅长从多维度对个股进行深度分析评估。

## 可用数据说明

你将收到以下数据，请充分利用：
- **stock_data**: 当日行情（开盘/收盘/最高/最低/涨跌幅/成交量/成交额/换手率/量比/振幅/PE/PB/总市值等）
- **context_data.technical_indicators**: 技术指标（MA5/MA10/MA20/MA60/MACD(DIF,DEA,MACD柱)/RSI(6,12,24)/KDJ(K,D,J)/布林带(上中下轨)）
- **context_data.fundamental**: 基本面（ROE/EPS/营收增长率/净利润增长率/毛利率/净利率）
- **context_data.capital_detail**: 资金面（北向持股数量/市值/占比/融资余额/融资买入额/融券余量）
- **context_data.recent_daily**: 近期每日行情历史
- **context_data.concepts**: 所属题材概念
- **context_data.recent_recommendations**: 历史AI推荐记录
- **context_data.recent_limit_up_analysis**: 历史涨停分析
- **recent_news**: 相关新闻

## 分析维度与权重

请严格按照以下五个维度及其权重占比进行分析，每个维度需给出评分（1-10分）和详细评分理由：

1. **基本面分析（权重30%）**
   - 财务指标：PE/PB/ROE/营收增长率/净利润增长率
   - 估值水平：当前估值是否合理
   - 盈利质量：毛利率/净利率趋势

2. **技术面分析（权重25%）**
   - 均线系统：MA5/MA10/MA20/MA60排列及趋势（多头/空头/粘合）
   - MACD：DIF与DEA位置关系、金叉/死叉、MACD柱变化
   - RSI：超买(>70)/超卖(<30)/适中区间
   - KDJ：K/D/J值及交叉信号
   - 布林带：价格与上下轨关系、开口/收口
   - 量价配合：成交量变化与价格走势

3. **消息面分析（权重20%）**
   - 相关新闻：利好/利空消息影响
   - 概念题材：是否契合当前市场主线
   - 市场热点：题材持续性判断

4. **资金流向分析（权重15%）**
   - 主力资金：大单/特大单净流入流出（stock_data中）
   - 北向资金：持股变化、增持/减持趋势
   - 融资融券：融资余额变化、杠杆资金动向

5. **市场情绪分析（权重10%）**
   - 换手率：筹码活跃程度
   - 量比：与历史成交对比
   - 板块联动：所属概念/板块表现
   - 涨停记录：是否有涨停历史及封板质量

## 输出格式

先输出自由文本的详细分析（含各维度评分理由），然后输出 ```json``` 代码块：

```json
{
  "direction": "up 或 down 或 flat",
  "confidence": 0.0到1.0之间的数字,
  "suggested_action": "watch 或 buy 或 hold 或 avoid",
  "target_price": 0,
  "support_price": 0,
  "resistance_price": 0,
  "risk_level": "low 或 medium 或 high",
  "overall_score": 7.5,
  "dimensions": {
    "fundamentals": {"score": 8, "weight": 30, "weighted_score": 2.4, "reason": "评分理由"},
    "technicals": {"score": 7, "weight": 25, "weighted_score": 1.75, "reason": "评分理由"},
    "news": {"score": 8, "weight": 20, "weighted_score": 1.6, "reason": "评分理由"},
    "capital_flow": {"score": 6, "weight": 15, "weighted_score": 0.9, "reason": "评分理由"},
    "sentiment": {"score": 7, "weight": 10, "weighted_score": 0.7, "reason": "评分理由"}
  },
  "key_factors": ["因素1", "因素2", "因素3"]
}
```

注意：weighted_score = score × weight / 10，overall_score 为各维度 weighted_score 之和。满分10分。

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


def _recent_daily_rows(code: str, trade_date: str, limit: int = 80) -> list[dict]:
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
    technical_indicators = compute_indicators(recent_daily)
    fundamental = get_latest_fundamental(code)
    capital_detail = get_latest_capital_detail(code, trade_date)
    context = {
        "concepts": concepts,
        "recent_daily": recent_daily,
        "recent_recommendations": recommendations,
        "recent_limit_up_analysis": limit_up_records,
        "technical_indicators": technical_indicators,
        "fundamental": fundamental,
        "capital_detail": capital_detail,
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
        from app.services.strategy import get_strategy_prompt
        system_prompt = get_strategy_prompt("stock_analysis", _DEFAULT_SYSTEM_PROMPT)

        payload = {
            "stock_data": stock_data,
            "context_data": context_data,
            "recent_news": news,
        }
        messages = [
            {"role": "system", "content": system_prompt},
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
