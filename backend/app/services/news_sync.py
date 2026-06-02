from datetime import datetime

import pandas as pd

from app.database import get_connection
from app.services.news_fetcher import SOURCE_REGISTRY, SOURCE_LABELS


def save_news(df: pd.DataFrame):
    if df.empty:
        return 0
    conn = get_connection()
    count = 0
    for _, row in df.iterrows():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO news (source, title, content, url, publish_time, fetch_time, extra) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row["source"], row["title"], row["content"], row["url"],
                    row["publish_time"], row["fetch_time"], row["extra"],
                ),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count


def sync_all() -> list[dict]:
    results = []
    for name, cls in SOURCE_REGISTRY.items():
        try:
            source = cls()
            df = source.fetch()
            count = save_news(df)
            results.append({"source": name, "label": SOURCE_LABELS.get(name, name), "count": count, "status": "ok"})
        except Exception as e:
            results.append({"source": name, "label": SOURCE_LABELS.get(name, name), "count": 0, "status": f"error: {e}"})
    cleanup_old_news(days=7)
    return results


def get_news(source: str = "", limit: int = 100) -> list[dict]:
    conn = get_connection()
    if source:
        rows = conn.execute(
            "SELECT * FROM news WHERE source = ? ORDER BY publish_time DESC LIMIT ?",
            (source, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM news ORDER BY publish_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    result = []
    for row in rows:
        import json
        result.append({
            "id": row["id"],
            "source": row["source"],
            "title": row["title"],
            "content": row["content"],
            "url": row["url"],
            "publish_time": row["publish_time"],
            "fetch_time": row["fetch_time"],
            "extra": json.loads(row["extra"]) if row["extra"] else {},
        })
    return result


def get_source_stats() -> list[dict]:
    conn = get_connection()
    stats = []
    for name, label in SOURCE_LABELS.items():
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MAX(fetch_time) as last_fetch FROM news WHERE source = ?",
            (name,),
        ).fetchone()
        stats.append({
            "name": name,
            "label": label,
            "count": row["cnt"] if row else 0,
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
