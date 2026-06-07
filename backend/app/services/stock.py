import json
import logging
import re
from datetime import datetime

import akshare as ak

from app.config import MODEL_ANALYSIS
from app.database import get_connection
from app.services import llm

logger = logging.getLogger(__name__)


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _round2(val) -> float | None:
    if val is None:
        return None
    return round(val, 2)


# ---------------------------------------------------------------------------
# Limit Up (涨停)
# ---------------------------------------------------------------------------

def fetch_limit_up_stocks(date: str) -> list[dict]:
    """Fetch limit-up stock pool from akshare. date format: YYYY-MM-DD."""
    ak_date = date.replace("-", "")
    try:
        df = ak.stock_zt_pool_em(date=ak_date)
        if df is None or df.empty:
            return []
    except Exception:
        logger.warning("akshare stock_zt_pool_em failed for %s", date, exc_info=True)
        return []

    items = []
    for _, row in df.iterrows():
        items.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": _parse_float(row.get("最新价")),
            "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
            "limit_up_amount": _parse_float(row.get("封板资金")),
            "turnover_rate": _round2(_parse_float(row.get("换手率"))),
            "volume": _parse_float(row.get("成交额")),
            "amount": _parse_float(row.get("成交额")),
            "amplitude": None,
            "first_limit_up_time": str(row.get("首次封板时间", "")) or None,
            "last_limit_up_time": str(row.get("最后封板时间", "")) or None,
            "limit_up_times": int(_parse_float(row.get("连板数")) or 1),
            "reason": str(row.get("涨停统计", "")) if row.get("涨停统计") else "",
            "sector": str(row.get("所属行业", "")) if row.get("所属行业") else "",
        })
    return items


def snapshot_limit_up_data(trade_date: str | None = None, trigger: str = "manual") -> dict:
    """Fetch limit-up stocks and persist to DB."""
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    items = fetch_limit_up_stocks(trade_date)
    if not items:
        return {"trade_date": trade_date, "item_count": 0, "success": True, "message": "当日无涨停股或非交易日"}

    conn = get_connection()
    try:
        conn.execute("DELETE FROM limit_up_snapshot WHERE trade_date = ?", (trade_date,))
        conn.executemany(
            """INSERT INTO limit_up_snapshot
               (trade_date, code, name, price, change_pct, limit_up_amount,
                turnover_rate, volume, amount, amplitude,
                first_limit_up_time, last_limit_up_time, limit_up_times, reason, sector, created_at)
               VALUES (?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?)""",
            [
                (trade_date, i["code"], i["name"], i["price"], i["change_pct"], i["limit_up_amount"],
                 i["turnover_rate"], i["volume"], i["amount"], i["amplitude"],
                 i["first_limit_up_time"], i["last_limit_up_time"], i["limit_up_times"],
                 i["reason"], i["sector"], now)
                for i in items
            ],
        )
        conn.execute(
            "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?,?,?,?,?,?,?)",
            ("limit_up_snapshot", trigger, "[]", len(items), "ok", 0, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to snapshot limit-up data")
        return {"trade_date": trade_date, "item_count": 0, "success": False, "message": "快照失败"}
    finally:
        conn.close()

    logger.info("Limit-up snapshot for %s: %d items", trade_date, len(items))
    return {"trade_date": trade_date, "item_count": len(items), "success": True, "message": "ok"}


def get_limit_up_by_date(trade_date: str) -> dict:
    """Get limit-up data from DB, fallback to live fetch."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM limit_up_snapshot WHERE trade_date = ? ORDER BY amount DESC NULLS LAST",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        items = [dict(r) for r in rows]
    else:
        items = fetch_limit_up_stocks(trade_date)

    return {
        "trade_date": trade_date,
        "items": items,
        "item_count": len(items),
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Hot Stocks & Market Sentiment
# ---------------------------------------------------------------------------

def _strip_code(raw_code: str) -> str:
    """Strip market prefix like SZ/SH from stock code."""
    if len(raw_code) > 2 and raw_code[:2] in ("SZ", "SH"):
        return raw_code[2:]
    return raw_code


def _fetch_hot_em(top_n: int) -> list[dict]:
    """东方财富个股人气榜"""
    try:
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return []
        items = []
        for idx, row in df.head(top_n).iterrows():
            items.append({
                "code": _strip_code(str(row.get("代码", ""))),
                "name": str(row.get("股票名称", "")),
                "price": _parse_float(row.get("最新价")),
                "change_pct": _round2(_parse_float(row.get("涨跌幅"))),
                "hot_rank": int(_parse_float(row.get("当前排名")) or (idx + 1)),
                "turnover_rate": None,
                "amount": None,
                "source": "东方财富",
            })
        return items
    except Exception:
        logger.debug("东方财富人气榜获取失败", exc_info=True)
        return []


def _fetch_hot_xq_follow(top_n: int) -> list[dict]:
    """雪球关注排行榜"""
    try:
        df = ak.stock_hot_follow_xq(symbol="最热门")
        if df is None or df.empty:
            return []
        items = []
        for idx, row in df.head(top_n).iterrows():
            items.append({
                "code": _strip_code(str(row.get("股票代码", ""))),
                "name": str(row.get("股票简称", "")),
                "price": _parse_float(row.get("最新价")),
                "change_pct": None,
                "hot_rank": idx + 1,
                "turnover_rate": None,
                "amount": None,
                "source": "雪球",
            })
        return items
    except Exception:
        logger.debug("雪球关注榜获取失败", exc_info=True)
        return []


def _fetch_hot_xq_tweet(top_n: int) -> list[dict]:
    """雪球讨论排行榜"""
    try:
        df = ak.stock_hot_tweet_xq(symbol="最热门")
        if df is None or df.empty:
            return []
        items = []
        for idx, row in df.head(top_n).iterrows():
            items.append({
                "code": _strip_code(str(row.get("股票代码", ""))),
                "name": str(row.get("股票简称", "")),
                "price": _parse_float(row.get("最新价")),
                "change_pct": None,
                "hot_rank": idx + 1,
                "turnover_rate": None,
                "amount": None,
                "source": "雪球",
            })
        return items
    except Exception:
        logger.debug("雪球讨论榜获取失败", exc_info=True)
        return []


def _fetch_hot_xq_deal(top_n: int) -> list[dict]:
    """雪球交易分享排行榜"""
    try:
        df = ak.stock_hot_deal_xq(symbol="最热门")
        if df is None or df.empty:
            return []
        items = []
        for idx, row in df.head(top_n).iterrows():
            items.append({
                "code": _strip_code(str(row.get("股票代码", ""))),
                "name": str(row.get("股票简称", "")),
                "price": _parse_float(row.get("最新价")),
                "change_pct": None,
                "hot_rank": idx + 1,
                "turnover_rate": None,
                "amount": None,
                "source": "雪球",
            })
        return items
    except Exception:
        logger.debug("雪球交易榜获取失败", exc_info=True)
        return []


def get_stock_hot_rank(top_n: int = 20) -> list[dict]:
    """Fetch stock popularity ranking from all sources, returns list of {source, items}."""
    sources = [
        ("东方财富人气", lambda: _fetch_hot_em(top_n)),
        ("雪球关注", lambda: _fetch_hot_xq_follow(top_n)),
        ("雪球讨论", lambda: _fetch_hot_xq_tweet(top_n)),
        ("雪球交易", lambda: _fetch_hot_xq_deal(top_n)),
    ]
    result = []
    for name, fn in sources:
        items = fn()
        if items:
            logger.info("热门个股 [%s]: %d 条", name, len(items))
            result.append({"source": name, "items": items})
    if not result:
        logger.warning("所有热门个股数据源均失败")
    return result


def get_market_sentiment() -> dict:
    """Get market sentiment data (up/down/flat counts, limit up/down)."""
    up_count = 0
    down_count = 0
    flat_count = 0
    limit_up_count = 0
    limit_down_count = 0
    sentiment_score = None

    try:
        df = ak.stock_market_activity_legu()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                item_name = str(row.get("item", ""))
                value = _parse_float(row.get("value"))
                if "上涨" in item_name:
                    up_count = int(value or 0)
                elif "下跌" in item_name:
                    down_count = int(value or 0)
                elif "平盘" in item_name:
                    flat_count = int(value or 0)
                elif "涨停" in item_name:
                    limit_up_count = int(value or 0)
                elif "跌停" in item_name:
                    limit_down_count = int(value or 0)
                elif "赚钱" in item_name or "情绪" in item_name:
                    sentiment_score = _round2(value)
    except Exception:
        logger.warning("akshare stock_market_activity_legu failed", exc_info=True)

    hot_stocks = get_stock_hot_rank()

    return {
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "sentiment_score": sentiment_score,
        "hot_stocks": hot_stocks,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_stock_overview() -> dict:
    """Aggregate overview: sentiment + limit-up data."""
    sentiment = get_market_sentiment()
    trade_date = datetime.now().strftime("%Y-%m-%d")
    limit_up = get_limit_up_by_date(trade_date)
    return {
        "sentiment": sentiment,
        "limit_up": limit_up,
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# AI Recommendations
# ---------------------------------------------------------------------------

_REC_SYSTEM_PROMPT = """\
你是一位资深A股投资顾问，负责根据当日市场数据为用户挑选具有投资价值的个股。

请根据以下市场数据，推荐 5-10 只有潜力的个股。要求：

1. 每只股票必须包含以下字段，以 JSON 数组格式输出：
   - code: 股票代码（如 "600519"）
   - name: 股票名称
   - reason: 推荐理由（50-100字，结合当日市场表现和基本面）
   - strategy: 操作策略（如 "短线追涨"、"低吸等待反弹"、"趋势持有"）
   - target_price: 目标价（如有）
   - stop_loss_price: 止损价（如有）
   - risk_level: 风险等级 "low"/"medium"/"high"
   - confidence: 信心度 0-1 之间的小数
   - sector: 所属行业/板块
   - score: 综合评分 1-10

2. 推荐原则：
   - 优先从涨停股中筛选强势品种
   - 关注主力资金大幅流入的个股
   - 结合热门板块和当日市场热点
   - 兼顾不同风险偏好的品种
   - 不推荐ST、*ST股票

3. 输出格式：严格用 ```json ``` 包裹的 JSON 数组，不要输出其他内容。
"""


def _get_rec_context(trade_date: str) -> str:
    """Collect context data for recommendation generation."""
    parts = []

    # Limit-up data
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code, name, change_pct, amount, limit_up_times, sector FROM limit_up_snapshot WHERE trade_date = ? ORDER BY amount DESC LIMIT 20",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        lines = [f"=== 今日涨停股 ({len(rows)}只) ==="]
        for r in rows:
            lines.append(f"  {r['name']}({r['code']}) 涨幅{r['change_pct']}% 连板{r['limit_up_times']} 行业:{r['sector']}")
        parts.append("\n".join(lines))

    # Hot sectors
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, change_pct, main_net_inflow, leading_stock FROM sector_snapshot_item WHERE trade_date = ? AND sector_type = 'industry' ORDER BY change_pct DESC LIMIT 10",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        lines = ["=== 热门行业 TOP10 ==="]
        for r in rows:
            inflow = (r["main_net_inflow"] or 0) / 1e8
            lines.append(f"  {r['name']}: 涨幅{r['change_pct']}% 主力净流入{inflow:.2f}亿 领涨:{r['leading_stock']}")
        parts.append("\n".join(lines))

    # Recent news
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT title, source FROM news WHERE date(publish_time) = ? ORDER BY publish_time DESC LIMIT 15",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        lines = [f"=== 最新新闻 ({len(rows)}条) ==="]
        for r in rows:
            lines.append(f"  [{r['source']}] {r['title']}")
        parts.append("\n".join(lines))

    return f"=== 交易日期: {trade_date} ===\n\n" + "\n\n".join(parts)


def _parse_recommendation_json(text: str) -> list[dict]:
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


def generate_recommendations(trade_date: str | None = None) -> dict:
    """Generate AI stock recommendations."""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context = _get_rec_context(trade_date)

    messages = [
        {"role": "system", "content": _REC_SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    response = llm.analysis_chat(messages)
    recs = _parse_recommendation_json(response)

    if not recs:
        logger.warning("No recommendations parsed from LLM response")
        return {"items": [], "total": 0}

    conn = get_connection()
    try:
        # Remove existing recommendations for this date
        conn.execute("DELETE FROM stock_recommendation WHERE trade_date = ?", (trade_date,))

        for rec in recs:
            conn.execute(
                """INSERT INTO stock_recommendation
                   (trade_date, code, name, reason, strategy, target_price, stop_loss_price,
                    risk_level, confidence, sector, score, model_used, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?)""",
                (
                    trade_date,
                    rec.get("code", ""),
                    rec.get("name", ""),
                    rec.get("reason", ""),
                    rec.get("strategy", ""),
                    _parse_float(rec.get("target_price")),
                    _parse_float(rec.get("stop_loss_price")),
                    rec.get("risk_level", "medium"),
                    _parse_float(rec.get("confidence")) or 0.5,
                    rec.get("sector", ""),
                    _parse_float(rec.get("score")) or 0,
                    MODEL_ANALYSIS,
                    "pending",
                    now,
                    now,
                ),
            )
        conn.commit()

        rows = conn.execute(
            "SELECT * FROM stock_recommendation WHERE trade_date = ? ORDER BY score DESC",
            (trade_date,),
        ).fetchall()
        items = [dict(r) for r in rows]
    except Exception:
        conn.rollback()
        logger.exception("Failed to save recommendations")
        raise
    finally:
        conn.close()

    logger.info("Generated %d recommendations for %s", len(items), trade_date)
    return {"items": items, "total": len(items)}


def get_recommendations_by_date(trade_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM stock_recommendation WHERE trade_date = ? ORDER BY score DESC",
            (trade_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recommendation_history(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM stock_recommendation").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM stock_recommendation ORDER BY trade_date DESC, score DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()
