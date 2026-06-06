import json
import logging
import re
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from app.database import get_connection
from app.services.market import CN_INDEX_NAMES
from app.services import llm
from app.config import MODEL_ANALYSIS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位资深A股市场分析师。你的任务是根据当日市场数据和新闻，提供专业的大盘分析，并对下一个交易日做出预测。

输出要求：
1. 先输出自由文本的当日大盘分析（包括各指数表现、成交量变化、市场情绪等）
2. 然后输出对下一个交易日的预测，也是自由文本
3. 最后输出一个 ```json 代码块，包含结构化预测数据

JSON 代码块格式如下：
```json
{
  "overall_direction": "up 或 down 或 flat",
  "confidence": 0.0到1.0之间的数字,
  "indices": {
    "sh000001": {"predicted_change_pct": 0.5, "support": 3300, "resistance": 3380},
    "sz399001": {"predicted_change_pct": -0.3, "support": 10500, "resistance": 10800},
    "sz399006": {"predicted_change_pct": 0.2, "support": 2100, "resistance": 2150}
  },
  "key_factors": ["因素1", "因素2", "因素3"],
  "risk_level": "low 或 medium 或 high"
}
```

注意：indices 中包含所有主要指数代码（sh000001, sz399001, sz399006, sh000688, sh000300, sh000016, sh000905, sh000852）。\
"""

_REVIEW_SYSTEM_PROMPT = """\
你是一位严谨的市场分析师，负责复盘预测准确性。请对比昨日的预测与今日的实际市场表现，给出客观评价。

输出要求：
1. 总体评价：预测方向是否正确？置信度是否合理？
2. 逐指数对比：预测涨跌幅 vs 实际涨跌幅，偏差有多大
3. 关键因素分析：哪些因素被正确预判，哪些被忽略
4. 改进建议：下次预测应该注意什么
"""


def _parse_prediction_json(text: str) -> dict:
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    candidate = m.group(1) if m else text
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return {}


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["prediction_summary"] = json.loads(d.get("prediction_summary") or "{}")
    d["actual_data"] = json.loads(d.get("actual_data") or "{}")
    d["scored_news"] = json.loads(d.get("scored_news") or "[]")
    return d


def _get_friday_before_weekend(date_str: str) -> str | None:
    """Return the Friday date if date_str is Saturday or Sunday, else None."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() == 5:  # Saturday
        return (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    if dt.weekday() == 6:  # Sunday
        return (dt - timedelta(days=2)).strftime("%Y-%m-%d")
    return None


def _filter_news_by_impact(news_list: list[dict], target_count: int = 30) -> list[dict]:
    """Use LLM to score and rank news by A-share impact. Returns top N with score and category."""
    if not news_list:
        return []

    numbered = "\n".join(f"{i+1}. [{n['source']}] {n['title']}" for i, n in enumerate(news_list))
    prompt = [
        {"role": "system", "content": (
            "你是一位资深A股市场分析师。以下是多条财经新闻标题，请评估每条新闻对A股市场的影响力。\n\n"
            "评分标准（0-10分）：\n"
            "- 9-10分：对A股有重大直接冲击（如央行政策、重大经济数据超预期、外围市场暴跌暴涨、重大地缘事件）\n"
            "- 7-8分：对A股有较大影响（如行业重磅政策、重要宏观数据、美股大幅波动、北向资金大幅变动）\n"
            "- 5-6分：有一定影响（如行业利好/利空、个股重大事件、区域经济政策）\n"
            "- 3-4分：影响较小（如一般行业动态、普通公司公告）\n"
            "- 1-2分：几乎无影响\n\n"
            "分类标签：政策变动 / 宏观经济 / 外围市场 / 行业动态 / 资金面 / 公司事件 / 其他\n\n"
            f"请选出影响值最高的{target_count}条，按影响力从高到低排序，以JSON数组格式返回。格式如下：\n"
            "```json\n"
            '[{"index": 1, "score": 9, "category": "外围市场"}]\n'
            "```\n"
            "只返回JSON数组，不要其他内容。"
        )},
        {"role": "user", "content": numbered},
    ]
    resp = llm.score_news(prompt).strip()
    results = _parse_prediction_json(resp) if resp.startswith("[") or resp.startswith("{") else None
    if not results:
        m = re.search(r"```json\s*(.*?)\s*```", resp, re.DOTALL)
        if m:
            try:
                results = json.loads(m.group(1))
            except (json.JSONDecodeError, TypeError):
                pass

    if not results or not isinstance(results, list):
        return news_list[:target_count]

    scored = []
    for item in results:
        idx = item.get("index", 0) - 1
        if 0 <= idx < len(news_list):
            scored.append({
                **news_list[idx],
                "impact_score": item.get("score", 5),
                "impact_category": item.get("category", "其他"),
            })
    scored.sort(key=lambda x: x.get("impact_score", 0), reverse=True)
    return scored[:target_count]


def get_today_market_context(date_str: str) -> dict:
    friday_str = _get_friday_before_weekend(date_str)
    is_weekend = friday_str is not None

    # Index data: use Friday's data on weekends
    market_date = friday_str or date_str
    cn_data = []
    for code, name in CN_INDEX_NAMES.items():
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            day = df[df["date"] == market_date]
            if day.empty:
                last5 = df.sort_values("date").tail(5)
                cn_data.append({
                    "code": code, "name": name,
                    "note": f"{market_date} 无数据，最近5日: {last5[['date','close','volume']].to_string(index=False)}",
                })
            else:
                row = day.iloc[0]
                cn_data.append({
                    "code": code, "name": name,
                    "open": float(row["open"]), "close": float(row["close"]),
                    "high": float(row["high"]), "low": float(row["low"]),
                    "volume": float(row["volume"]),
                })
        except Exception:
            logger.warning("获取 %s 历史数据失败", code, exc_info=True)

    # News: expand date range on weekends (Friday through today)
    recent_news = []
    conn = get_connection()
    try:
        if is_weekend:
            rows = conn.execute(
                "SELECT title, source, url, publish_time FROM news WHERE date(publish_time) BETWEEN ? AND ? ORDER BY publish_time DESC",
                (friday_str, date_str),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT title, source, url, publish_time FROM news WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT 30",
                (date_str,),
            ).fetchall()
        recent_news = [{"title": r["title"], "source": r["source"], "url": r["url"], "publish_time": r["publish_time"]} for r in rows]
    finally:
        conn.close()

    if is_weekend and len(recent_news) > 30:
        logger.info("周末模式：从 %d 条新闻中筛选影响值最高的 30 条", len(recent_news))
        recent_news = _filter_news_by_impact(recent_news, 30)

    # Always score news when we have enough for meaningful ranking
    scored_news = []
    if len(recent_news) >= 5:
        scored_news = _filter_news_by_impact(recent_news, 30)
        # Ensure all items have score/category (in case scoring was skipped)
        for item in scored_news:
            item.setdefault("impact_score", 5)
            item.setdefault("impact_category", "其他")
    else:
        scored_news = recent_news

    trend_data = {}
    for code, name in CN_INDEX_NAMES.items():
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["date"] < market_date].sort_values("date").tail(5)
            if not df.empty:
                trend_data[code] = {
                    "name": name,
                    "records": df[["date", "close", "volume"]].to_dict("records"),
                }
        except Exception:
            pass

    return {"cn_data": cn_data, "recent_news": recent_news, "scored_news": scored_news, "trend_data": trend_data, "date": date_str, "is_weekend": is_weekend, "friday": friday_str}


def build_analysis_prompt(context: dict, previous_prediction: dict | None = None) -> list[dict]:
    is_weekend = context.get("is_weekend", False)
    friday = context.get("friday")

    if is_weekend:
        lines = [f"=== 当前日期: {context['date']}（周末休市） ==="]
        lines.append(f"以下为周五({friday})收盘数据，请结合周五以来的资讯预测下周一开盘走势。")
    else:
        lines = [f"=== {context['date']} A股市场数据 ==="]

    for item in context["cn_data"]:
        if "close" in item:
            change_pct = ((item["close"] - item["open"]) / item["open"] * 100) if item["open"] else 0
            lines.append(
                f"{item['name']}({item['code']}): 开{item['open']:.2f} 收{item['close']:.2f} "
                f"高{item['high']:.2f} 低{item['low']:.2f} 量{item['volume']:.0f} 涨跌幅{change_pct:+.2f}%"
            )
        else:
            lines.append(item.get("note", ""))

    if context["trend_data"]:
        lines.append("\n=== 近5日趋势 ===")
        for code, td in context["trend_data"].items():
            recs = td["records"]
            closes = " -> ".join(f"{r['close']:.2f}" for r in recs)
            lines.append(f"{td['name']}: {closes}")

    if context.get("scored_news"):
        date_label = f"{friday}~{context['date']}周末资讯" if is_weekend else "当日相关新闻"
        lines.append(f"\n=== {date_label}影响力排行({len(context['scored_news'])}条) ===")
        for n in context["scored_news"]:
            score = n.get("impact_score", "?")
            cat = n.get("impact_category", "")
            lines.append(f"[影响力:{score}/10 | {cat}] [{n['source']}] {n['title']}")
    elif context["recent_news"]:
        date_label = f"{friday}~{context['date']}周末资讯" if is_weekend else "当日相关新闻"
        lines.append(f"\n=== {date_label}({len(context['recent_news'])}条) ===")
        for n in context["recent_news"][:30]:
            lines.append(f"[{n['source']}] {n['title']}")

    if previous_prediction:
        lines.append("\n=== 上一个交易日预测（请先复盘） ===")
        lines.append(f"预测方向: {previous_prediction.get('prediction_summary', {}).get('overall_direction', 'N/A')}")
        lines.append(f"预测文本: {previous_prediction.get('prediction_text', '')[:500]}")
        lines.append(f"预测摘要: {json.dumps(previous_prediction.get('prediction_summary', {}), ensure_ascii=False)[:500]}")
        actual = previous_prediction.get("actual_data", {})
        if actual:
            lines.append(f"实际数据: {json.dumps(actual, ensure_ascii=False)[:500]}")

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def compare_prediction(today_date: str) -> dict | None:
    today_cn = []
    for code, name in CN_INDEX_NAMES.items():
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            day = df[df["date"] == today_date]
            if not day.empty:
                row = day.iloc[0]
                prev_close = float(day.iloc[0]["open"]) if len(day) > 0 else 0
                change_pct = 0
                try:
                    prev_df = df[df["date"] < today_date].sort_values("date").tail(1)
                    if not prev_df.empty:
                        prev_close = float(prev_df.iloc[0]["close"])
                        change_pct = (float(row["close"]) - prev_close) / prev_close * 100
                except Exception:
                    pass
                today_cn.append({
                    "code": code, "name": name,
                    "close": float(row["close"]),
                    "open": float(row["open"]),
                    "change_pct": round(change_pct, 2),
                    "volume": float(row["volume"]),
                })
        except Exception:
            pass

    if not today_cn:
        logger.warning("无法获取 %s 的实际数据，跳过对比", today_date)
        return None

    actual_data = {"indices": {}, "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    for item in today_cn:
        actual_data["indices"][item["code"]] = {
            "close": item["close"],
            "change_pct": item["change_pct"],
            "volume": item["volume"],
        }

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM market_analysis WHERE trade_date < ? AND status IN ('analyzed','reviewed') ORDER BY trade_date DESC LIMIT 1",
            (today_date,),
        ).fetchone()
        if not row:
            return None

        prev = _row_to_dict(row)
        review_prompt = [
            {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"=== 预测日期: {prev['trade_date']} ===\n"
                f"预测方向: {prev['prediction_summary'].get('overall_direction', 'N/A')}\n"
                f"预测置信度: {prev['prediction_summary'].get('confidence', 'N/A')}\n"
                f"预测详情: {json.dumps(prev['prediction_summary'], ensure_ascii=False)}\n"
                f"预测文本: {prev['prediction_text'][:800]}\n\n"
                f"=== 实际日期: {today_date} ===\n"
                f"实际数据: {json.dumps(actual_data, ensure_ascii=False)}\n\n"
                "请复盘预测准确性。"
            )},
        ]

        review_text = llm.analysis_chat(review_prompt)

        conn.execute(
            "UPDATE market_analysis SET actual_data=?, review_text=?, status='reviewed', updated_at=? WHERE id=?",
            (json.dumps(actual_data, ensure_ascii=False), review_text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), prev["id"]),
        )
        conn.commit()
        return _row_to_dict(conn.execute("SELECT * FROM market_analysis WHERE id=?", (prev["id"],)).fetchone())
    finally:
        conn.close()


def generate_daily_analysis(trade_date: str | None = None) -> dict:
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM market_analysis WHERE trade_date=?", (trade_date,)
        ).fetchone()
        if existing and existing["status"] in ("analyzed", "reviewed"):
            return _row_to_dict(existing)

        compare_prediction(trade_date)

        context = get_today_market_context(trade_date)
        if not context["cn_data"]:
            raise ValueError(f"无法获取 {trade_date} 的市场数据")

        prev_row = conn.execute(
            "SELECT * FROM market_analysis WHERE trade_date < ? AND status IN ('analyzed','reviewed') ORDER BY trade_date DESC LIMIT 1",
            (trade_date,),
        ).fetchone()
        previous_prediction = _row_to_dict(prev_row) if prev_row else None

        messages = build_analysis_prompt(context, previous_prediction)
        response_text = llm.analysis_chat(messages)
        prediction_summary = _parse_prediction_json(response_text)

        analysis_part = response_text
        prediction_part = ""
        json_match = re.search(r"```json\s*.*?\s*```", response_text, re.DOTALL)
        if json_match:
            boundary = json_match.start()
            analysis_part = response_text[:boundary].strip()
            prediction_part = response_text[boundary:].strip()

        scored_news_json = json.dumps(context.get("scored_news", []), ensure_ascii=False)

        if existing:
            conn.execute(
                """UPDATE market_analysis SET
                    analysis_text=?, prediction_text=?, prediction_summary=?,
                    scored_news=?, model_used=?, status='analyzed', updated_at=?
                WHERE id=?""",
                (analysis_part, prediction_part, json.dumps(prediction_summary, ensure_ascii=False),
                 scored_news_json, MODEL_ANALYSIS, now_str, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO market_analysis
                    (trade_date, analysis_text, prediction_text, prediction_summary,
                     scored_news, model_used, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,'analyzed',?,?)""",
                (trade_date, analysis_part, prediction_part,
                 json.dumps(prediction_summary, ensure_ascii=False),
                 scored_news_json, MODEL_ANALYSIS, now_str, now_str),
            )
        conn.commit()

        result = conn.execute("SELECT * FROM market_analysis WHERE trade_date=?", (trade_date,)).fetchone()
        return _row_to_dict(result)
    finally:
        conn.close()


def get_analysis(date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM market_analysis WHERE trade_date=?", (date,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_latest_analysis() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM market_analysis ORDER BY trade_date DESC LIMIT 1").fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_analysis_history(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM market_analysis").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM market_analysis ORDER BY trade_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()
