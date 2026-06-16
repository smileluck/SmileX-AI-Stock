import json
import logging
import re
from datetime import datetime

from app.database import get_connection
from app.services import llm

logger = logging.getLogger(__name__)


def _get_day_news(trade_date: str, top_n: int = 50) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, source, title, publish_time FROM news "
            "WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT ?",
            (trade_date, top_n),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_sector_name_index(trade_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code, name, sector_type FROM sector_snapshot_item "
            "WHERE trade_date=? ORDER BY sector_type, change_pct DESC",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    seen = set()
    items = []
    for r in rows:
        key = (r["code"], r["sector_type"])
        if key in seen:
            continue
        seen.add(key)
        items.append({"code": r["code"], "name": r["name"], "sector_type": r["sector_type"]})
    return items


def _build_score_prompt(news_list: list[dict], sectors: list[dict]) -> list[dict]:
    sector_lines = "\n".join(
        f"{i + 1}. [{s['sector_type']}] {s['code']} {s['name']}"
        for i, s in enumerate(sectors)
    )
    news_lines = "\n".join(
        f"{i + 1}. [{n['source']}] {n['title']}"
        for i, n in enumerate(news_list)
    )

    system = (
        "你是A股市场分析师。下面给你两份数据：第一份是板块清单（行业+概念），第二份是当日新闻清单。\n"
        "请评估每条新闻**主要影响**哪些板块，按相关性输出 JSON 数组。\n\n"
        "评分维度（0-10分）：\n"
        "- 9-10分：对该板块有重大直接冲击（行业重磅政策、龙头公司重大变化）\n"
        "- 7-8分：对该板块有较大影响（行业利好政策、产业链重大变化）\n"
        "- 5-6分：有一定影响（一般行业动态、区域性政策）\n"
        "- 3-4分：影响较小（普通公司公告、边缘关联）\n"
        "- 1-2分：几乎无影响\n\n"
        "相关性：high / medium / low\n"
        "类别：政策变动 / 宏观经济 / 外围市场 / 行业动态 / 资金面 / 公司事件 / 其他\n\n"
        "**只输出与板块相关度 medium 以上的关联，避免为每条新闻硬塞板块**。\n\n"
        "输出 JSON 数组，每项格式：\n"
        '{"news_index": 1, "sector_index": 5, "score": 8, "relevance": "high", "category": "行业动态"}\n\n'
        "只输出 JSON 数组，不要其他解释。"
    )
    user = (
        f"=== 板块清单（共{len(sectors)}个） ===\n{sector_lines}\n\n"
        f"=== 新闻清单（共{len(news_list)}条） ===\n{news_lines}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_score_response(resp: str) -> list[dict]:
    if not resp:
        return []
    candidates = []
    if resp.lstrip().startswith("["):
        candidates.append(resp)
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", resp, re.DOTALL)
    if m:
        candidates.append(m.group(1))
    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            continue
    start = resp.find("[")
    end = resp.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(resp[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def score_news_to_sectors(trade_date: str, top_n: int = 50) -> dict:
    """对当天 top_n 条新闻批量识别影响的板块，写入 news_sector_association。"""
    news_list = _get_day_news(trade_date, top_n)
    sectors = _get_sector_name_index(trade_date)

    if not news_list:
        logger.warning("score_news_to_sectors: 当日无新闻 trade_date=%s", trade_date)
        return {"trade_date": trade_date, "news_count": 0, "associations": 0}
    if not sectors:
        logger.warning("score_news_to_sectors: 当日无板块快照 trade_date=%s", trade_date)
        return {"trade_date": trade_date, "news_count": len(news_list), "associations": 0}

    messages = _build_score_prompt(news_list, sectors)
    try:
        resp = llm.function_chat("news_scorer", messages)
    except Exception:
        logger.exception("news_sector_assoc LLM 调用失败 trade_date=%s", trade_date)
        return {"trade_date": trade_date, "news_count": len(news_list), "associations": 0, "error": "llm_failed"}

    parsed = _parse_score_response(resp)
    if not parsed:
        logger.warning("news_sector_assoc: 无法解析 LLM 输出 trade_date=%s", trade_date)
        return {"trade_date": trade_date, "news_count": len(news_list), "associations": 0, "error": "parse_failed"}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_insert = []
    seen = set()
    for item in parsed:
        try:
            n_idx = int(item.get("news_index", 0)) - 1
            s_idx = int(item.get("sector_index", 0)) - 1
        except (ValueError, TypeError):
            continue
        if not (0 <= n_idx < len(news_list)) or not (0 <= s_idx < len(sectors)):
            continue
        news = news_list[n_idx]
        sector = sectors[s_idx]
        key = (news["id"], sector["code"])
        if key in seen:
            continue
        seen.add(key)
        try:
            score = float(item.get("score", 5))
        except (ValueError, TypeError):
            score = 5.0
        score = max(0.0, min(10.0, score))
        rows_to_insert.append(
            (
                news["id"],
                sector["code"],
                sector["name"],
                sector["sector_type"],
                score,
                item.get("category", "其他"),
                item.get("relevance", "medium"),
                trade_date,
                now_str,
            )
        )

    if not rows_to_insert:
        return {"trade_date": trade_date, "news_count": len(news_list), "associations": 0}

    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM news_sector_association WHERE trade_date=?", (trade_date,)
        )
        conn.executemany(
            "INSERT INTO news_sector_association "
            "(news_id, sector_code, sector_name, sector_type, impact_score, impact_category, relevance, trade_date, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows_to_insert,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("news_sector_assoc 写库失败 trade_date=%s", trade_date)
        raise
    finally:
        conn.close()

    return {
        "trade_date": trade_date,
        "news_count": len(news_list),
        "associations": len(rows_to_insert),
    }


def get_sector_news_heat(trade_date: str, top_k: int = 30) -> list[dict]:
    """按板块聚合当日新闻热度，返回 top_k。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT sector_code, sector_name, sector_type, "
            "COUNT(*) AS news_count, AVG(impact_score) AS avg_score, "
            "MAX(impact_score) AS max_score "
            "FROM news_sector_association WHERE trade_date=? "
            "GROUP BY sector_code, sector_name, sector_type "
            "ORDER BY (AVG(impact_score) * COUNT(*)) DESC "
            "LIMIT ?",
            (trade_date, top_k),
        ).fetchall()
        return [
            {
                "sector_code": r["sector_code"],
                "sector_name": r["sector_name"],
                "sector_type": r["sector_type"],
                "news_count": r["news_count"],
                "avg_score": round(r["avg_score"], 2) if r["avg_score"] is not None else 0,
                "max_score": round(r["max_score"], 2) if r["max_score"] is not None else 0,
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_top_news_for_sector(trade_date: str, sector_code: str, limit: int = 5) -> list[dict]:
    """取某板块关联度最高的新闻（含标题+来源）。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT nsa.impact_score, nsa.impact_category, nsa.relevance, "
            "news.title, news.source, news.publish_time, news.url "
            "FROM news_sector_association nsa "
            "JOIN news ON news.id = nsa.news_id "
            "WHERE nsa.trade_date=? AND nsa.sector_code=? "
            "ORDER BY nsa.impact_score DESC, news.publish_time DESC LIMIT ?",
            (trade_date, sector_code, limit),
        ).fetchall()
        return [
            {
                "title": r["title"],
                "source": r["source"],
                "publish_time": r["publish_time"],
                "url": r["url"],
                "impact_score": r["impact_score"],
                "impact_category": r["impact_category"],
                "relevance": r["relevance"],
            }
            for r in rows
        ]
    finally:
        conn.close()
