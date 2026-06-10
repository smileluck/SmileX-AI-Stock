import json
import logging
from datetime import datetime

import pandas as pd

from app.database import get_connection
from app.services import llm
from app.services.market import CN_INDEX_NAMES, _fetch_index_daily_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位资深A股市场分析师，负责每日收盘后的综合分析。请根据以下数据，生成一份全面的收盘分析报告。

报告要求包含以下板块，每个板块用明确的标题分隔：

## 一、大盘综述
对当日各主要指数表现进行总结，包括涨跌幅、成交量变化、市场情绪等。

## 二、板块热点
分析当日热门板块和冷门板块，指出领涨/领跌板块及其驱动因素。

## 三、资金流向
分析主力资金、北向资金等的流入流出情况，指出资金偏好。

## 四、新闻与情绪
总结当日重要新闻对市场的影响，评估市场情绪。

## 五、明日展望
对下一个交易日的市场走势给出预判，包括可能的热点和风险点。

## 六、风险提示
列出需要关注的主要风险因素。

要求：
- 语言专业但不晦涩，重点突出
- 数据引用准确，有理有据
- 每个板块 100-200 字
"""


def _row_to_dict(row) -> dict:
    d = dict(row)
    return d


def _get_index_data(trade_date: str) -> str:
    """Get index data from market_analysis if available, else fetch from akshare."""
    import akshare as ak
    import pandas as pd
    from app.services.market import CN_INDEX_NAMES

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT analysis_text FROM market_analysis WHERE trade_date=?", (trade_date,)
        ).fetchone()
        if row and row["analysis_text"]:
            return f"=== 已有指数分析 ===\n{row['analysis_text']}"
    finally:
        conn.close()

    lines = []
    for code, name in CN_INDEX_NAMES.items():
        df = _fetch_index_daily_fallback(code)
        if df is None:
            logger.warning("All index sources failed for %s", code)
            continue
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        day = df[df["date"] == trade_date]
        if not day.empty:
            r = day.iloc[0]
            change_pct = ((float(r["close"]) - float(r["open"])) / float(r["open"]) * 100) if float(r["open"]) else 0
            lines.append(
                f"{name}({code}): 开{float(r['open']):.2f} 收{float(r['close']):.2f} "
                f"高{float(r['high']):.2f} 低{float(r['low']):.2f} 涨跌幅{change_pct:+.2f}%"
            )

    return "=== 指数数据 ===\n" + "\n".join(lines) if lines else "无指数数据"


def _get_sector_data(trade_date: str) -> str:
    """Get top/bottom sectors from sector_snapshot_item."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM sector_snapshot_item WHERE trade_date=? AND sector_type='industry' ORDER BY change_pct DESC",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "无板块数据"

    items = [dict(r) for r in rows]
    top5 = items[:5]
    bottom5 = items[-5:] if len(items) >= 5 else items

    lines = ["=== 领涨板块 TOP5 ==="]
    for s in top5:
        lines.append(f"{s['name']}: 涨跌幅{s.get('change_pct', 'N/A')}% 主力净流入{s.get('main_net_inflow', 'N/A')} 领涨股{s.get('leading_stock', 'N/A')}")

    lines.append("\n=== 领跌板块 TOP5 ===")
    for s in bottom5:
        lines.append(f"{s['name']}: 涨跌幅{s.get('change_pct', 'N/A')}% 主力净流入{s.get('main_net_inflow', 'N/A')}")

    return "\n".join(lines)


def _get_capital_flow_data(trade_date: str) -> str:
    """Get capital flow summary from sector data."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM sector_snapshot_item WHERE trade_date=? AND sector_type='industry' "
            "ORDER BY main_net_inflow DESC",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "无资金流向数据"

    items = [dict(r) for r in rows]
    total_main = sum(s.get("main_net_inflow", 0) or 0 for s in items)
    inflow_top = [s for s in items if (s.get("main_net_inflow") or 0) > 0][:5]
    outflow_top = [s for s in items if (s.get("main_net_inflow") or 0) < 0][-5:]

    lines = [f"=== 主力资金流向 (行业合计: {total_main/1e8:.2f}亿) ==="]
    if inflow_top:
        lines.append("主力净流入 TOP5:")
        for s in inflow_top:
            lines.append(f"  {s['name']}: {s.get('main_net_inflow', 0)/1e8:.2f}亿")
    if outflow_top:
        lines.append("主力净流出 TOP5:")
        for s in outflow_top:
            lines.append(f"  {s['name']}: {s.get('main_net_inflow', 0)/1e8:.2f}亿")

    return "\n".join(lines)


def _get_news_data(trade_date: str) -> str:
    """Get news for the trading day."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT title, source FROM news WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT 30",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "无当日新闻"

    lines = [f"=== 当日新闻 ({len(rows)}条) ==="]
    for r in rows[:20]:
        lines.append(f"[{r['source']}] {r['title']}")
    return "\n".join(lines)


def _get_prediction_data(trade_date: str) -> str:
    """Get prediction from previous analysis."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT prediction_summary, prediction_text FROM market_analysis "
            "WHERE trade_date=? AND status IN ('analyzed','reviewed')",
            (trade_date,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return ""

    summary = json.loads(row["prediction_summary"]) if row["prediction_summary"] else {}
    return (
        f"=== 今日预测 ===\n"
        f"方向: {summary.get('overall_direction', 'N/A')}\n"
        f"置信度: {summary.get('confidence', 'N/A')}\n"
        f"风险等级: {summary.get('risk_level', 'N/A')}\n"
        f"关键因素: {', '.join(summary.get('key_factors', []))}"
    )


def generate_ai_daily_report(trade_date: str | None = None) -> dict:
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM ai_daily_report WHERE trade_date=?", (trade_date,)
        ).fetchone()
        if existing and existing["status"] == "completed":
            return _row_to_dict(existing)

        parts = [
            _get_index_data(trade_date),
            _get_sector_data(trade_date),
            _get_capital_flow_data(trade_date),
            _get_news_data(trade_date),
            _get_prediction_data(trade_date),
        ]
        user_content = f"=== 交易日期: {trade_date} ===\n\n" + "\n\n".join(p for p in parts if p)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        report_text = llm.function_chat("daily_report", messages)

        if existing:
            conn.execute(
                "UPDATE ai_daily_report SET report_text=?, status='completed', updated_at=? WHERE id=?",
                (report_text, now_str, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO ai_daily_report (trade_date, report_text, model_used, status, created_at, updated_at) "
                "VALUES (?,?,?,'completed',?,?)",
                (trade_date, report_text, llm.get_model_for_function("daily_report"), now_str, now_str),
            )
        conn.commit()

        result = conn.execute("SELECT * FROM ai_daily_report WHERE trade_date=?", (trade_date,)).fetchone()
        return _row_to_dict(result)
    except Exception:
        conn.rollback()
        logger.exception("生成AI日报失败 trade_date=%s", trade_date)
        raise
    finally:
        conn.close()


def get_report(date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ai_daily_report WHERE trade_date=?", (date,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_latest_report() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ai_daily_report ORDER BY trade_date DESC LIMIT 1").fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_report_history(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM ai_daily_report").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM ai_daily_report ORDER BY trade_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()
