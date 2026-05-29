import json
from datetime import datetime

from smilex.store import init_db, save_news, cleanup_old_news, query_news
from smilex.consult.news_em_flash import fetch_em_flash
from smilex.consult.news_cls import fetch_cls_telegraph
from smilex.consult.news_cctv import fetch_cctv_news


def sync_all_news():
    """调度器调用的新闻同步入口"""
    print(f"[{datetime.now()}] 新闻同步开始...")
    try:
        init_db()

        df_em = fetch_em_flash()
        if not df_em.empty:
            save_news(df_em)
            print(f"  东方财富快讯: {len(df_em)} 条")

        df_cls = fetch_cls_telegraph()
        if not df_cls.empty:
            save_news(df_cls)
            print(f"  财联社快讯: {len(df_cls)} 条")

        if _should_fetch_cctv():
            df_cctv = fetch_cctv_news()
            if not df_cctv.empty:
                save_news(df_cctv)
                print(f"  新闻联播: {len(df_cctv)} 条")

        cleanup_old_news(days=7)
        print(f"[{datetime.now()}] 新闻同步完成")
    except Exception as e:
        print(f"[{datetime.now()}] 新闻同步失败: {e}")


def _should_fetch_cctv() -> bool:
    """央视新闻每6小时抓取一次即可"""
    existing = query_news(source="cctv_news", limit=1)
    if existing.empty:
        return True
    last_fetch = existing.iloc[0].get("fetch_time", "")
    if not last_fetch:
        return True
    try:
        last_dt = datetime.strptime(last_fetch, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - last_dt).total_seconds() > 6 * 3600
    except ValueError:
        return True


def get_latest_news(source: str = "", limit: int = 200) -> list[dict]:
    """dashboard 调用，从 SQLite 读取缓存的新闻"""
    df = query_news(source=source, limit=limit)
    if df.empty:
        return []
    records = df.to_dict("records")
    for r in records:
        try:
            r["extra"] = json.loads(r.get("extra", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["extra"] = {}
    return records
