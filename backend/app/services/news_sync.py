import json
import re
import time
from datetime import datetime, timedelta

import pandas as pd

from app.database import get_connection
from app.services.news_fetcher import SOURCE_REGISTRY, SOURCE_LABELS

_STD_FMT = "%Y-%m-%d %H:%M:%S"


def _normalize_publish_time(publish_time: str, fetch_time: str) -> str:
    s = (publish_time or "").strip()
    if not s:
        return ""

    # Relative times: "刚刚", "X分钟前", "X小时前", "昨天 HH:MM"
    if s == "刚刚":
        return fetch_time
    m = re.match(r"(\d+)\s*分钟前", s)
    if m:
        dt = datetime.strptime(fetch_time, _STD_FMT) - timedelta(minutes=int(m.group(1)))
        return dt.strftime(_STD_FMT)
    m = re.match(r"(\d+)\s*小时前", s)
    if m:
        dt = datetime.strptime(fetch_time, _STD_FMT) - timedelta(hours=int(m.group(1)))
        return dt.strftime(_STD_FMT)
    m = re.match(r"昨天\s*(.*)", s)
    if m:
        fetch_dt = datetime.strptime(fetch_time, _STD_FMT)
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                t = datetime.strptime(m.group(1).strip(), fmt)
                return (fetch_dt.replace(hour=t.hour, minute=t.minute, second=0) - timedelta(days=1)).strftime(_STD_FMT)
            except ValueError:
                continue

    # "MM月DD日 HH:MM"
    m = re.match(r"(\d+)月(\d+)日\s*(\d+):(\d+)", s)
    if m:
        fetch_dt = datetime.strptime(fetch_time, _STD_FMT)
        try:
            dt = datetime(fetch_dt.year, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            return dt.strftime(_STD_FMT)
        except ValueError:
            pass

    # Standard datetime formats
    for fmt in (_STD_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime(_STD_FMT)
        except ValueError:
            continue

    # "MM-DD HH:MM" without year — use current year
    for fmt in ("%m-%d %H:%M", "%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            fetch_dt = datetime.strptime(fetch_time, _STD_FMT)
            return dt.replace(year=fetch_dt.year).strftime(_STD_FMT)
        except ValueError:
            continue

    return ""


def save_news(df: pd.DataFrame):
    if df.empty:
        return 0
    conn = get_connection()
    count = 0
    for _, row in df.iterrows():
        try:
            pub = _normalize_publish_time(str(row.get("publish_time", "")), str(row.get("fetch_time", "")))
            conn.execute(
                "INSERT OR IGNORE INTO news (source, title, content, url, publish_time, fetch_time, extra) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row["source"], row["title"], row["content"], row["url"],
                    pub, row["fetch_time"], row["extra"],
                ),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count


def sync_all(trigger: str = "manual") -> list[dict]:
    start = time.time()
    results = []
    has_error = False
    for name, cls in SOURCE_REGISTRY.items():
        try:
            source = cls()
            df = source.fetch()
            count = save_news(df)
            results.append({"source": name, "label": SOURCE_LABELS.get(name, name), "count": count, "status": "ok"})
        except Exception as e:
            has_error = True
            results.append({"source": name, "label": SOURCE_LABELS.get(name, name), "count": 0, "status": f"error: {e}"})
    cleanup_old_news(days=7)
    total = sum(r["count"] for r in results)
    duration = round(time.time() - start, 2)
    _save_log(job_id="news_sync", trigger=trigger, results=results, total=total, status="error" if has_error else "ok", duration=duration)
    return results


def _save_log(job_id: str, trigger: str, results: list[dict], total: int, status: str, duration: float):
    conn = get_connection()
    conn.execute(
        "INSERT INTO sync_log (job_id, trigger, results, total, status, duration, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (job_id, trigger, json.dumps(results, ensure_ascii=False), total, status, duration, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_sync_logs(limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sync_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "job_id": row["job_id"],
            "trigger": row["trigger"],
            "results": json.loads(row["results"]) if row["results"] else [],
            "total": row["total"],
            "status": row["status"],
            "duration": row["duration"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _sort_key(row: dict) -> str:
    pub = (row.get("publish_time") or "").strip()
    if pub:
        norm = _normalize_publish_time(pub, row["fetch_time"] or "")
        if norm:
            return norm
    return row["fetch_time"] or ""


def get_news(source: str = "", limit: int = 100) -> list[dict]:
    conn = get_connection()
    if source:
        rows = conn.execute(
            "SELECT * FROM news WHERE source = ?",
            (source,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM news").fetchall()
    conn.close()

    raw = []
    for row in rows:
        pub_raw = row["publish_time"] or ""
        norm = _normalize_publish_time(pub_raw, row["fetch_time"] or "")
        raw.append({**dict(row), "publish_time": norm or pub_raw})

    raw.sort(key=_sort_key, reverse=True)

    import json as _json
    return [
        {
            "id": r["id"],
            "source": r["source"],
            "title": r["title"],
            "content": r["content"],
            "url": r["url"],
            "publish_time": r["publish_time"],
            "fetch_time": r["fetch_time"],
            "extra": _json.loads(r["extra"]) if r["extra"] else {},
        }
        for r in raw[:limit]
    ]


def get_source_stats() -> list[dict]:
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    stats = []
    for name, label in SOURCE_LABELS.items():
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MAX(fetch_time) as last_fetch FROM news WHERE source = ?",
            (name,),
        ).fetchone()
        today_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM news WHERE source = ? AND fetch_time >= ?",
            (name, today),
        ).fetchone()
        stats.append({
            "name": name,
            "label": label,
            "count": row["cnt"] if row else 0,
            "today_count": today_row["cnt"] if today_row else 0,
            "last_fetch": row["last_fetch"] if row else None,
        })
    conn.close()
    return stats


def cleanup_old_news(days: int = 7):
    conn = get_connection()
    cutoff = datetime.now().strftime("%Y-%m-%d 00:00:00")
    conn.execute("DELETE FROM news WHERE fetch_time < datetime(?, '-' || ? || ' days')", (cutoff, days))
    conn.commit()
    conn.close()
