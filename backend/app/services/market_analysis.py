import json
import logging
import re
from datetime import datetime, timedelta

import pandas as pd

from app.database import get_connection, db_session
from app.services.market import CN_INDEX_NAMES, _fetch_index_daily_fallback
from app.services import llm
from app.services.constants import (
    NEWS_TIME_DECAY_PER_HOUR,
    NEWS_TIME_WEIGHT_FLOOR,
    NEWS_FILTER_TARGET_COUNT,
    NEWS_DAILY_FETCH_LIMIT,
)

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
    return llm.parse_json_response(text, expect="object")


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


def _compute_time_weight(publish_time: str | None, reference_date: datetime) -> float:
    """Compute a time-based weight for a news item.
    - More recent news gets higher weight (decay over days)
    - Base weight is 1.0 for today, decays ~0.15 per day
    Returns value in [0.3, 1.0]
    """
    if not publish_time:
        return 0.5
    try:
        pub_dt = datetime.strptime(publish_time[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        try:
            pub_dt = datetime.strptime(publish_time[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return 0.5

    hours_diff = (reference_date - pub_dt).total_seconds() / 3600
    if hours_diff < 0:
        # Future/upcoming event — boost
        return 1.0
    weight = max(NEWS_TIME_WEIGHT_FLOOR, 1.0 - hours_diff * NEWS_TIME_DECAY_PER_HOUR)
    return round(weight, 2)


def _filter_news_by_impact(
    news_list: list[dict],
    target_count: int = NEWS_FILTER_TARGET_COUNT,
    reference_date: datetime | None = None,
    is_weekend: bool = False,
) -> list[dict]:
    """Use LLM to score and rank news by A-share impact, with time-based weighting.
    Returns top N with combined score and category."""
    if not news_list:
        return []

    now = reference_date or datetime.now()

    # Pre-compute time weights
    time_weights = [_compute_time_weight(n.get("publish_time"), now) for n in news_list]

    numbered = "\n".join(
        f"{i+1}. [{n['source']}] {n['title']}"
        + (f" (发布: {n['publish_time'][:16]})" if n.get("publish_time") else "")
        for i, n in enumerate(news_list)
    )

    weekend_hint = (
        "\n特别注意：这是周末分析，请特别关注涉及下周即将发生的事件"
        "（如重要经济数据公布、政策会议、期权交割等），这类前瞻性资讯应适当提高评分。"
        if is_weekend else ""
    )

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
            "注意：发布时间越近的资讯越重要；涉及即将发生的事件（如下周会议、数据公布等前瞻性资讯）"
            "应适当提高评分，因为它们对近期开盘影响更大。"
            f"{weekend_hint}\n"
            f"请选出影响值最高的{target_count}条，按影响力从高到低排序，以JSON数组格式返回。格式如下：\n"
            "```json\n"
            '[{"index": 1, "score": 9, "category": "外围市场"}]\n'
            "```\n"
            "只返回JSON数组，不要其他内容。"
        )},
        {"role": "user", "content": numbered},
    ]
    resp = llm.score_news(prompt).strip()
    results = llm.parse_json_response(resp, expect="array")

    if not results or not isinstance(results, list):
        # Fallback: sort by time weight only
        ranked = [
            {**news_list[i], "impact_score": 5, "impact_category": "其他", "time_weight": time_weights[i], "combined_score": round(5 * time_weights[i], 2)}
            for i in range(min(len(news_list), target_count))
        ]
        ranked.sort(key=lambda x: x["combined_score"], reverse=True)
        return ranked

    scored = []
    for item in results:
        idx = item.get("index", 0) - 1
        if 0 <= idx < len(news_list):
            llm_score = item.get("score", 5)
            tw = time_weights[idx]
            combined = round(llm_score * tw, 2)
            scored.append({
                **news_list[idx],
                "impact_score": llm_score,
                "impact_category": item.get("category", "其他"),
                "time_weight": tw,
                "combined_score": combined,
            })
    scored.sort(key=lambda x: x["combined_score"], reverse=True)
    return scored[:target_count]


def get_today_market_context(date_str: str) -> dict:
    friday_str = _get_friday_before_weekend(date_str)
    is_weekend = friday_str is not None

    # Index data: use Friday's data on weekends. 同一份 df 同时用于当日/趋势，避免重复拉取。
    market_date = friday_str or date_str
    cn_data = []
    index_dfs: dict[str, pd.DataFrame] = {}
    for code, name in CN_INDEX_NAMES.items():
        df = _fetch_index_daily_fallback(code)
        if df is None:
            logger.warning("All index sources failed for %s", code)
            continue
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        index_dfs[code] = df
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

    # News: expand date range on weekends (full week: Monday through today)
    recent_news = []
    ref_dt = datetime.strptime(date_str, "%Y-%m-%d")
    conn = get_connection()
    try:
        if is_weekend:
            # Monday of the same week
            monday_str = (ref_dt - timedelta(days=ref_dt.weekday())).strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT title, source, url, publish_time FROM news WHERE date(publish_time) BETWEEN ? AND ? ORDER BY publish_time DESC",
                (monday_str, date_str),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT title, source, url, publish_time FROM news WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT ?",
                (date_str, NEWS_DAILY_FETCH_LIMIT),
            ).fetchall()
        recent_news = [{"title": r["title"], "source": r["source"], "url": r["url"], "publish_time": r["publish_time"]} for r in rows]
    finally:
        conn.close()

    if is_weekend and len(recent_news) > NEWS_FILTER_TARGET_COUNT:
        logger.info("周末模式：从 %d 条本周资讯中筛选影响值最高的 %d 条（含时间加权）",
                    len(recent_news), NEWS_FILTER_TARGET_COUNT)
        recent_news = _filter_news_by_impact(recent_news, NEWS_FILTER_TARGET_COUNT, reference_date=ref_dt, is_weekend=True)

    # Always score news when we have enough for meaningful ranking
    scored_news = []
    if len(recent_news) >= 5 and not (is_weekend and len(recent_news) > NEWS_FILTER_TARGET_COUNT):
        # Weekend bulk news already scored above with time weights
        scored_news = _filter_news_by_impact(recent_news, NEWS_FILTER_TARGET_COUNT, reference_date=ref_dt, is_weekend=is_weekend)
        for item in scored_news:
            item.setdefault("impact_score", 5)
            item.setdefault("impact_category", "其他")
            item.setdefault("time_weight", 1.0)
            item.setdefault("combined_score", item["impact_score"])
    elif is_weekend and len(recent_news) > NEWS_FILTER_TARGET_COUNT:
        # Already scored with time weights in the block above
        scored_news = recent_news
    else:
        scored_news = recent_news

    trend_data = {}
    for code, name in CN_INDEX_NAMES.items():
        df = index_dfs.get(code)
        if df is None:
            continue
        # df['date'] 已是字符串 YYYY-MM-DD，可直接字符串比较
        recent = df[df["date"] < market_date].sort_values("date").tail(5)
        if not recent.empty:
            trend_data[code] = {
                "name": name,
                "records": recent[["date", "close", "volume"]].to_dict("records"),
            }

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
        date_label = f"本周资讯({context.get('date','')}周末汇总)" if is_weekend else "当日相关新闻"
        lines.append(f"\n=== {date_label} 影响力排行({len(context['scored_news'])}条) ===")
        if is_weekend:
            lines.append("注：综合得分 = 影响力评分 × 时间权重，越近的资讯或涉及即将发生事件的资讯权重越高。")
        for n in context["scored_news"]:
            score = n.get("impact_score", "?")
            cat = n.get("impact_category", "")
            combined = n.get("combined_score")
            tw = n.get("time_weight")
            pub = n.get("publish_time", "")[:16]
            if combined is not None:
                lines.append(f"[综合:{combined} | 影响力:{score}/10 | 时间权重:{tw} | {cat}] [{n['source']}] {n['title']} ({pub})")
            else:
                lines.append(f"[影响力:{score}/10 | {cat}] [{n['source']}] {n['title']}")
    elif context["recent_news"]:
        date_label = f"本周资讯({context.get('date','')}周末汇总)" if is_weekend else "当日相关新闻"
        lines.append(f"\n=== {date_label}({len(context['recent_news'])}条) ===")
        for n in context["recent_news"][:30]:
            pub = n.get("publish_time", "")[:16]
            lines.append(f"[{n['source']}] {n['title']} ({pub})" if pub else f"[{n['source']}] {n['title']}")

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
        df = _fetch_index_daily_fallback(code)
        if df is None:
            continue
        try:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            day = df[df["date"] == today_date]
            if day.empty:
                continue
            row = day.iloc[0]
            prev_df = df[df["date"] < today_date].sort_values("date").tail(1)
            if prev_df.empty:
                continue
            prev_close = float(prev_df.iloc[0]["close"])
            change_pct = (float(row["close"]) - prev_close) / prev_close * 100 if prev_close else 0
            today_cn.append({
                "code": code, "name": name,
                "close": float(row["close"]),
                "open": float(row["open"]),
                "change_pct": round(change_pct, 2),
                "volume": float(row["volume"]),
            })
        except Exception:
            logger.exception("compare_prediction parse failed for %s", code)

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
                 scored_news_json, llm.get_model_for_function("analysis"), now_str, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO market_analysis
                    (trade_date, analysis_text, prediction_text, prediction_summary,
                     scored_news, model_used, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,'analyzed',?,?)""",
                (trade_date, analysis_part, prediction_part,
                 json.dumps(prediction_summary, ensure_ascii=False),
                 scored_news_json, llm.get_model_for_function("analysis"), now_str, now_str),
            )
        conn.commit()

        result = conn.execute("SELECT * FROM market_analysis WHERE trade_date=?", (trade_date,)).fetchone()
        return _row_to_dict(result)
    finally:
        conn.close()


def get_analysis(date: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM market_analysis WHERE trade_date=?", (date,)).fetchone()
        return _row_to_dict(row) if row else None


def get_latest_analysis() -> dict | None:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM market_analysis ORDER BY trade_date DESC LIMIT 1").fetchone()
        return _row_to_dict(row) if row else None


def get_analysis_history(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    with db_session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM market_analysis").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM market_analysis ORDER BY trade_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
