import json
import logging
import re
from datetime import datetime, timedelta

from app.database import get_connection
from app.services import llm
from app.services.sector import get_sector_history_by_date, get_sector_history_range
from app.services.strategy import get_strategy_prompt

logger = logging.getLogger(__name__)

_SECTOR_LABELS = {"industry": "行业板块", "concept": "概念板块"}

_SYSTEM_PROMPT_TEMPLATE = """\
你是一位资深A股{sector_label}分析师，专注于{sector_label}的深度研究。请根据以下{sector_label}数据、近期趋势和相关新闻，生成分析报告。

报告要求包含以下板块，每个板块用明确的标题分隔：

## 一、板块概览
总结当日{sector_label}整体表现，涨跌比例、市场广度。

## 二、热门板块
分析领涨板块及其驱动因素（政策、事件、基本面变化等），指出持续性如何。

## 三、冷门板块
分析领跌板块及原因，是否存在超跌反弹机会。

## 四、资金流向分析
分析主力资金偏好，哪些板块受到资金追捧，哪些遭到抛售。

## 五、板块轮动趋势
根据近期数据判断板块轮动方向，哪些板块可能接棒。

## 六、明日板块展望
预测下一个交易日可能活跃的板块及逻辑。

要求：
- 语言专业简洁，重点突出
- 数据引用准确，涨跌幅、资金流向要有具体数字
- 每个板块 100-200 字

最后输出一个 ```json``` 代码块，包含结构化预测数据：
```json
{{
  "predicted_active_sectors": [
    {{"name": "板块名", "direction": "up", "confidence": 0.8, "heat": 8, "key_drivers": ["驱动因素1", "驱动因素2"], "risk_level": "medium"}}
  ],
  "overall_rotation": "轮动方向描述",
  "confidence": 0.7,
  "key_factors": ["因素1", "因素2"],
  "risk_level": "medium"
}}
```
"""

_REVIEW_SYSTEM_PROMPT = """\
你是一位严谨的板块分析师，负责复盘预测准确性。请对比昨日的板块预测与今日的实际板块表现，给出客观评价。

输出要求：
1. 总体评价：预测的活跃板块方向是否正确？置信度是否合理？
2. 逐板块对比：预测活跃板块 vs 实际涨幅排名，哪些命中、哪些偏离
3. 关键因素分析：哪些驱动因素被正确预判，哪些被忽略
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
    for field in ("prediction_summary", "actual_data", "trend_data"):
        d[field] = json.loads(d.get(field) or "{}")
    d["scored_news"] = json.loads(d.get("scored_news") or "[]")
    return d


def _build_sector_context(trade_date: str, sector_type: str) -> str:
    label = _SECTOR_LABELS.get(sector_type, sector_type)
    lines = [f"=== 交易日期: {trade_date} ===\n"]

    data = get_sector_history_by_date(trade_date, sector_type)
    items = data.get("items", [])
    if not items:
        lines.append(f"无{label}数据\n")
        return "\n".join(lines)

    sorted_items = sorted(items, key=lambda x: x.get("change_pct") or 0, reverse=True)

    lines.append(f"=== {label}（共{len(sorted_items)}个） ===")
    lines.append(f"\n--- 领涨{label} TOP10 ---")
    for s in sorted_items[:10]:
        inflow = s.get("main_net_inflow")
        inflow_str = f"{inflow / 1e8:.2f}亿" if inflow else "N/A"
        leading = s.get("leading_stock", "N/A")
        leading_pct = s.get("leading_stock_change_pct")
        leading_pct_str = f"{leading_pct:+.2f}%" if leading_pct is not None else "N/A"
        lines.append(
            f"{s['name']}: 涨跌幅{s.get('change_pct', 'N/A'):+.2f}% "
            f"主力净流入{inflow_str} 领涨股{leading}({leading_pct_str}) "
            f"上涨{s.get('up_count', 'N/A')}家 下跌{s.get('down_count', 'N/A')}家"
        )

    lines.append(f"\n--- 领跌{label} TOP10 ---")
    for s in sorted_items[-10:]:
        inflow = s.get("main_net_inflow")
        inflow_str = f"{inflow / 1e8:.2f}亿" if inflow else "N/A"
        lines.append(
            f"{s['name']}: 涨跌幅{s.get('change_pct', 'N/A'):+.2f}% "
            f"主力净流入{inflow_str}"
        )

    inflow_sorted = sorted(items, key=lambda x: x.get("main_net_inflow") or 0, reverse=True)
    lines.append(f"\n--- {label}主力净流入 TOP5 ---")
    for s in inflow_sorted[:5]:
        inflow = s.get("main_net_inflow")
        inflow_str = f"{inflow / 1e8:.2f}亿" if inflow else "N/A"
        lines.append(f"{s['name']}: 净流入{inflow_str} 涨跌幅{s.get('change_pct', 'N/A'):+.2f}%")

    lines.append(f"\n--- {label}主力净流出 TOP5 ---")
    for s in inflow_sorted[-5:]:
        inflow = s.get("main_net_inflow")
        inflow_str = f"{inflow / 1e8:.2f}亿" if inflow else "N/A"
        lines.append(f"{s['name']}: 净流出{inflow_str} 涨跌幅{s.get('change_pct', 'N/A'):+.2f}%")

    lines.append("")
    return "\n".join(lines)


def _build_trend_context(trade_date: str, sector_type: str, days: int = 5) -> tuple[str, dict]:
    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    end_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (dt - timedelta(days=days * 2)).strftime("%Y-%m-%d")

    range_data = get_sector_history_range(start_date, end_date, sector_type)
    sectors = range_data.get("sectors", [])
    if not sectors:
        return "", {}

    trend_summary = {
        "start_date": start_date,
        "end_date": end_date,
        "sector_type": sector_type,
        "top_gainers": [],
        "top_losers": [],
        "top_inflow": [],
        "top_outflow": [],
    }

    label = _SECTOR_LABELS.get(sector_type, sector_type)
    lines = [f"\n=== 近{days}日{label}趋势（{start_date} ~ {end_date}） ==="]

    by_change = sorted(sectors, key=lambda x: x.get("avg_change_pct") or 0, reverse=True)
    lines.append(f"\n--- 近{days}日{label}涨幅 TOP10 ---")
    for s in by_change[:10]:
        lines.append(
            f"{s['name']}: 均涨{s.get('avg_change_pct', 0):+.2f}% "
            f"最佳{s.get('best_change_pct', 0):+.2f}% "
            f"最差{s.get('worst_change_pct', 0):+.2f}% "
            f"交易{s.get('trading_days', 0)}天"
        )
        trend_summary["top_gainers"].append({"name": s["name"], "avg_change_pct": s.get("avg_change_pct")})

    lines.append(f"\n--- 近{days}日{label}跌幅 TOP10 ---")
    for s in by_change[-10:]:
        lines.append(
            f"{s['name']}: 均涨{s.get('avg_change_pct', 0):+.2f}% "
            f"交易{s.get('trading_days', 0)}天"
        )
        trend_summary["top_losers"].append({"name": s["name"], "avg_change_pct": s.get("avg_change_pct")})

    by_inflow = sorted(sectors, key=lambda x: x.get("total_main_net_inflow") or 0, reverse=True)
    lines.append(f"\n--- 近{days}日{label}主力净流入 TOP5 ---")
    for s in by_inflow[:5]:
        inflow = s.get("total_main_net_inflow", 0)
        inflow_str = f"{inflow / 1e8:.2f}亿" if inflow else "0"
        lines.append(f"{s['name']}: 总净流入{inflow_str} 均涨{s.get('avg_change_pct', 0):+.2f}%")
        trend_summary["top_inflow"].append({"name": s["name"], "total_main_net_inflow": inflow})

    lines.append(f"\n--- 近{days}日{label}主力净流出 TOP5 ---")
    for s in by_inflow[-5:]:
        inflow = s.get("total_main_net_inflow", 0)
        inflow_str = f"{inflow / 1e8:.2f}亿" if inflow else "0"
        lines.append(f"{s['name']}: 总净流出{inflow_str} 均涨{s.get('avg_change_pct', 0):+.2f}%")
        trend_summary["top_outflow"].append({"name": s["name"], "total_main_net_inflow": inflow})

    lines.append("")
    return "\n".join(lines), trend_summary


def _score_sector_news(news_list: list[dict], sector_type: str, sector_names: list[str]) -> list[dict]:
    if not news_list:
        return []

    numbered = "\n".join(
        f"{i+1}. [{n['source']}] {n['title']}"
        + (f" (发布: {n['publish_time'][:16]})" if n.get("publish_time") else "")
        for i, n in enumerate(news_list)
    )

    label = _SECTOR_LABELS.get(sector_type, sector_type)
    sample_names = "、".join(sector_names[:15])

    prompt = [
        {"role": "system", "content": (
            f"你是一位资深A股市场分析师。以下是多条财经新闻标题，请评估每条新闻对{label}（如：{sample_names}等）"
            "的影响力和相关性。\n\n"
            "评分标准（0-10分）：\n"
            "- 9-10分：对板块有重大直接冲击（如行业重磅政策、重大行业事件、龙头公司重大变化）\n"
            "- 7-8分：对板块有较大影响（如行业利好政策、重要数据公布、产业链重大变化）\n"
            "- 5-6分：有一定影响（如一般行业动态、区域性政策）\n"
            "- 3-4分：影响较小（如普通公司公告、边缘关联）\n"
            "- 1-2分：几乎无影响\n\n"
            "分类标签：政策变动 / 宏观经济 / 外围市场 / 行业动态 / 资金面 / 公司事件 / 其他\n\n"
            "请选出影响值最高的20条，按影响力从高到低排序，以JSON数组格式返回。格式如下：\n"
            "```json\n"
            '[{"index": 1, "score": 9, "category": "行业动态"}]\n'
            "```\n"
            "只返回JSON数组，不要其他内容。"
        )},
        {"role": "user", "content": numbered},
    ]

    try:
        resp = llm.score_news(prompt).strip()
    except Exception:
        logger.warning("板块新闻评分LLM调用失败，使用默认评分", exc_info=True)
        return [
            {**news_list[i], "impact_score": 5, "impact_category": "其他"}
            for i in range(min(len(news_list), 20))
        ]
    results = None
    if resp.startswith("[") or resp.startswith("{"):
        try:
            parsed = json.loads(resp)
            results = parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, TypeError):
            pass
    if not results:
        m = re.search(r"```json\s*(.*?)\s*```", resp, re.DOTALL)
        if m:
            try:
                results = json.loads(m.group(1))
            except (json.JSONDecodeError, TypeError):
                pass

    if not results or not isinstance(results, list):
        return [
            {**news_list[i], "impact_score": 5, "impact_category": "其他"}
            for i in range(min(len(news_list), 20))
        ]

    scored = []
    for item in results:
        idx = item.get("index", 0) - 1
        if 0 <= idx < len(news_list):
            scored.append({
                **news_list[idx],
                "impact_score": item.get("score", 5),
                "impact_category": item.get("category", "其他"),
            })
    scored.sort(key=lambda x: x["impact_score"], reverse=True)
    return scored[:20]


def _get_previous_prediction(trade_date: str, sector_type: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sector_analysis WHERE trade_date < ? AND sector_type = ? AND status IN ('analyzed','reviewed') ORDER BY trade_date DESC LIMIT 1",
            (trade_date, sector_type),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _fetch_today_news(trade_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT title, source, url, publish_time, content FROM news WHERE date(publish_time) <= ? ORDER BY publish_time DESC LIMIT 100",
            (trade_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _generate_single_analysis(trade_date: str, sector_type: str) -> dict:
    label = _SECTOR_LABELS.get(sector_type, sector_type)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM sector_analysis WHERE trade_date=? AND sector_type=?",
            (trade_date, sector_type),
        ).fetchone()
        if existing and existing["status"] in ("analyzed", "reviewed"):
            return _row_to_dict(existing)

        context = _build_sector_context(trade_date, sector_type)

        trend_text, trend_summary = _build_trend_context(trade_date, sector_type, 5)

        all_news = _fetch_today_news(trade_date)
        today_items = get_sector_history_by_date(trade_date, sector_type).get("items", [])
        sector_names = [s["name"] for s in today_items]
        scored_news = _score_sector_news(all_news, sector_type, sector_names) if all_news else []

        previous = _get_previous_prediction(trade_date, sector_type)

        lines = [context]
        if trend_text:
            lines.append(trend_text)

        if scored_news:
            lines.append(f"\n=== {label}相关新闻（{len(scored_news)}条） ===")
            for n in scored_news:
                score = n.get("impact_score", "?")
                cat = n.get("impact_category", "")
                pub = n.get("publish_time", "")[:16]
                lines.append(f"[影响力:{score}/10 | {cat}] [{n['source']}] {n['title']} ({pub})")

        if previous:
            lines.append("\n=== 上一个交易日预测（请先复盘） ===")
            lines.append(f"预测日期: {previous['trade_date']}")
            ps = previous.get("prediction_summary", {})
            lines.append(f"轮动方向: {ps.get('overall_rotation', 'N/A')}")
            predicted = ps.get("predicted_active_sectors", [])
            if predicted:
                lines.append(f"预测活跃板块: {', '.join(s.get('name', '?') for s in predicted[:5])}")
            lines.append(f"预测摘要: {json.dumps(ps, ensure_ascii=False)[:500]}")

        user_content = "\n".join(lines)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(sector_label=label)
        messages = [
            {"role": "system", "content": get_strategy_prompt("sector_analysis", system_prompt)},
            {"role": "user", "content": user_content},
        ]

        try:
            response_text = llm.analysis_chat(messages)
        except Exception as e:
            logger.error("板块分析LLM调用失败: %s", e, exc_info=True)
            raise RuntimeError(f"{label}分析生成失败：LLM调用异常（{type(e).__name__}: {e}）") from e
        prediction_summary = _parse_prediction_json(response_text)

        analysis_part = response_text
        prediction_part = ""
        json_match = re.search(r"```json\s*.*?\s*```", response_text, re.DOTALL)
        if json_match:
            boundary = json_match.start()
            analysis_part = response_text[:boundary].strip()
            prediction_part = response_text[boundary:].strip()

        scored_news_json = json.dumps(scored_news, ensure_ascii=False)
        trend_data_json = json.dumps(trend_summary, ensure_ascii=False)
        prediction_summary_json = json.dumps(prediction_summary, ensure_ascii=False)

        if existing:
            conn.execute(
                """UPDATE sector_analysis SET
                    analysis_text=?, prediction_text=?, prediction_summary=?,
                    scored_news=?, trend_data=?, model_used=?, status='analyzed', updated_at=?
                WHERE id=?""",
                (analysis_part, prediction_part, prediction_summary_json,
                 scored_news_json, trend_data_json,
                 llm.get_model_for_function("sector_analysis"), now_str, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO sector_analysis
                    (trade_date, sector_type, analysis_text, prediction_text, prediction_summary,
                     scored_news, trend_data, model_used, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'analyzed',?,?)""",
                (trade_date, sector_type, analysis_part, prediction_part,
                 prediction_summary_json, scored_news_json, trend_data_json,
                 llm.get_model_for_function("sector_analysis"), now_str, now_str),
            )
        conn.commit()

        result = conn.execute(
            "SELECT * FROM sector_analysis WHERE trade_date=? AND sector_type=?",
            (trade_date, sector_type),
        ).fetchone()
        return _row_to_dict(result)
    except Exception:
        conn.rollback()
        logger.exception("生成%s分析失败 trade_date=%s", label, trade_date)
        raise
    finally:
        conn.close()


def generate_sector_analysis(trade_date: str | None = None, sector_type: str | None = None) -> dict:
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    if sector_type is None:
        results = {}
        for st in ("industry", "concept"):
            try:
                results[st] = _generate_single_analysis(trade_date, st)
            except Exception:
                logger.exception("生成 %s 分析失败", st)
                results[st] = None
        return results

    return _generate_single_analysis(trade_date, sector_type)


def compare_sector_prediction(today_date: str, sector_type: str | None = None) -> dict:
    types = [sector_type] if sector_type else ["industry", "concept"]
    results = {}
    for st in types:
        label = _SECTOR_LABELS.get(st, st)
        try:
            actual = get_sector_history_by_date(today_date, st)
            actual_items = actual.get("items", [])
            if not actual_items:
                logger.warning("无法获取 %s 的%s实际数据，跳过复盘", today_date, label)
                results[st] = None
                continue

            actual_data = {
                "trade_date": today_date,
                "sector_type": st,
                "top_gainers": [
                    {"name": s["name"], "change_pct": s.get("change_pct"), "main_net_inflow": s.get("main_net_inflow")}
                    for s in sorted(actual_items, key=lambda x: x.get("change_pct") or 0, reverse=True)[:10]
                ],
                "top_losers": [
                    {"name": s["name"], "change_pct": s.get("change_pct"), "main_net_inflow": s.get("main_net_inflow")}
                    for s in sorted(actual_items, key=lambda x: x.get("change_pct") or 0)[:10]
                ],
                "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM sector_analysis WHERE trade_date < ? AND sector_type = ? AND status IN ('analyzed','reviewed') ORDER BY trade_date DESC LIMIT 1",
                    (today_date, st),
                ).fetchone()
                if not row:
                    results[st] = None
                    continue

                prev = _row_to_dict(row)
                review_prompt = [
                    {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"=== 预测日期: {prev['trade_date']} | {label} ===\n"
                        f"预测摘要: {json.dumps(prev.get('prediction_summary', {}), ensure_ascii=False)}\n"
                        f"预测文本: {prev.get('prediction_text', '')[:800]}\n\n"
                        f"=== 实际日期: {today_date} ===\n"
                        f"实际数据: {json.dumps(actual_data, ensure_ascii=False)}\n\n"
                        f"请复盘{label}预测准确性。"
                    )},
                ]

                review_text = llm.analysis_chat(review_prompt)

                conn.execute(
                    "UPDATE sector_analysis SET actual_data=?, review_text=?, status='reviewed', updated_at=? WHERE id=?",
                    (json.dumps(actual_data, ensure_ascii=False), review_text,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), prev["id"]),
                )
                conn.commit()

                result = conn.execute(
                    "SELECT * FROM sector_analysis WHERE id=?", (prev["id"],)
                ).fetchone()
                results[st] = _row_to_dict(result)
            finally:
                conn.close()
        except Exception:
            logger.exception("复盘%s预测失败", label)
            results[st] = None

    return results


def get_latest_sector_analysis(sector_type: str | None = None) -> dict | None:
    conn = get_connection()
    try:
        if sector_type:
            row = conn.execute(
                "SELECT * FROM sector_analysis WHERE sector_type=? ORDER BY trade_date DESC LIMIT 1",
                (sector_type,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM sector_analysis ORDER BY trade_date DESC LIMIT 1"
            ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_sector_analysis_by_date(trade_date: str, sector_type: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sector_analysis WHERE trade_date=? AND sector_type=?",
            (trade_date, sector_type),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_sector_analysis_history(limit: int = 20, offset: int = 0, sector_type: str | None = None) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        if sector_type:
            total = conn.execute(
                "SELECT COUNT(*) FROM sector_analysis WHERE sector_type=?", (sector_type,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM sector_analysis WHERE sector_type=? ORDER BY trade_date DESC LIMIT ? OFFSET ?",
                (sector_type, limit, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM sector_analysis").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM sector_analysis ORDER BY trade_date DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()
