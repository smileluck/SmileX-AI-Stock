"""券商研报入库与查询服务。

独立于 news_sync（字段差异大）。复用 sync_log 记录抓取历史。
"""
import json
import logging
import time
from datetime import datetime

from app.database import db_session
from sources.research_eastmoney import ResearchEastMoneySource

logger = logging.getLogger(__name__)


def sync_research_reports(trigger: str = "manual", days: int = 3) -> dict:
    """抓取近 days 天研报并入库。返回统计信息。"""
    start = time.time()
    source = ResearchEastMoneySource()
    try:
        df = source.fetch(days=days, page_size=100, max_pages=5)
    except Exception:
        logger.exception("[research_sync] fetch failed")
        df = None

    if df is None or df.empty:
        _log_sync("research_sync", trigger, 0, 0, "failed", time.time() - start)
        return {"total": 0, "inserted": 0, "status": "failed", "duration": time.time() - start}

    inserted = 0
    with db_session() as conn:
        for _, row in df.iterrows():
            try:
                extra = json.loads(row["extra"]) if row.get("extra") else {}
                stock_codes_json = json.dumps(extra.get("stock_codes") or [], ensure_ascii=False)
                target_price = extra.get("target_price")
                current_price = extra.get("current_price")
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO research_report (
                        source, title, url, report_type, org, analyst, rating,
                        target_price, current_price, industry, stock_codes,
                        publish_date, fetch_time, summary, content, extra
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("source") or "research_eastmoney",
                        row["title"],
                        row["url"],
                        extra.get("report_type", "stock"),
                        extra.get("org", ""),
                        extra.get("analyst", ""),
                        extra.get("rating", ""),
                        target_price,
                        current_price,
                        extra.get("industry", ""),
                        stock_codes_json,
                        row.get("publish_time") or "",
                        row.get("fetch_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        row.get("content", ""),
                        "",
                        row.get("extra", "{}"),
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except Exception:
                logger.exception("[research_sync] insert failed: %s", row.get("url"))
        conn.commit()

    duration = time.time() - start
    _log_sync("research_sync", trigger, len(df), inserted, "ok", duration)
    logger.info("[research_sync] fetched=%d inserted=%d duration=%.1fs", len(df), inserted, duration)
    return {"total": len(df), "inserted": inserted, "status": "ok", "duration": duration}


def _log_sync(job_id: str, trigger: str, total: int, inserted: int, status: str, duration: float):
    """写一条 sync_log 记录。results 存 JSON 详情。"""
    try:
        with db_session() as conn:
            conn.execute(
                """
                INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    trigger,
                    json.dumps({"inserted": inserted}, ensure_ascii=False),
                    total,
                    status,
                    duration,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
    except Exception:
        logger.exception("[research_sync] log_sync failed")


def get_recent_reports(
    days: int = 7,
    report_type: str | None = None,
    rating: str | None = None,
    org: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """查询近 days 天研报，支持过滤。返回 (rows, total)。"""
    where = ["publish_date >= date('now', ?)"]
    params: list = [f"-{days} days"]
    if report_type:
        where.append("report_type = ?")
        params.append(report_type)
    if rating:
        where.append("rating = ?")
        params.append(rating)
    if org:
        where.append("(org LIKE ? OR org = ?)")
        params.append(f"%{org}%")
        params.append(org)

    where_sql = " AND ".join(where)
    with db_session() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM research_report WHERE {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, source, title, url, report_type, org, analyst, rating,
                   target_price, current_price, industry, stock_codes,
                   publish_date, fetch_time, summary, extra
            FROM research_report
            WHERE {where_sql}
            ORDER BY publish_date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

    result = []
    for r in rows:
        item = dict(r)
        try:
            item["stock_codes"] = json.loads(item.get("stock_codes") or "[]")
        except (json.JSONDecodeError, TypeError):
            item["stock_codes"] = []
        try:
            item["extra"] = json.loads(item.get("extra") or "{}")
        except (json.JSONDecodeError, TypeError):
            item["extra"] = {}
        result.append(item)
    return result, total


def get_org_list(limit: int = 50) -> list[str]:
    """获取出现过的机构列表（用于前端过滤下拉）。"""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT org, COUNT(*) AS cnt FROM research_report
            WHERE org != '' AND publish_date >= date('now', '-30 days')
            GROUP BY org ORDER BY cnt DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [r["org"] for r in rows if r["org"]]
