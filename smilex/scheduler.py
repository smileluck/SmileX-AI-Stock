import os
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from smilex.config import HISTORY_DIR
from smilex.store import init_db, save_stock_list, update_daily, save_market_stats, sync_index_data
from smilex.fetcher import stock_list, realtime_quote
from smilex.scanner import daily_scan
from smilex.notify import push, push_scan

CONFIG_FILE = os.path.join(HISTORY_DIR, "scheduler_config.json")


def run_daily_job(strategy_name: str = "trend_following"):
    """执行每日收盘后任务"""
    print(f"[{datetime.now()}] 开始每日任务 (策略: {strategy_name})...")
    try:
        init_db()
        stocks = stock_list()
        save_stock_list(stocks)
        print(f"  股票列表已更新 ({len(stocks)} 只)")

        codes = stocks["code"].head(300).tolist()
        update_daily(codes)
        print("  日K数据已更新")

        # Sync valuation data for value strategies
        if strategy_name in ("value_technical", "multi_factor"):
            try:
                from smilex.fetcher import sync_valuation_data
                from smilex.store import save_valuation
                print("  同步估值数据...")
                val_df = sync_valuation_data(codes=codes, months=6)
                if not val_df.empty:
                    save_valuation(val_df)
                    print(f"  估值数据已更新 ({len(val_df)} 条)")
            except Exception as e:
                print(f"  估值数据同步失败: {e}")

        results = daily_scan(strategy_name=strategy_name)
        print(f"  选股扫描完成，推荐 {len(results)} 只")

        if not results.empty:
            os.makedirs(HISTORY_DIR, exist_ok=True)
            filepath = os.path.join(HISTORY_DIR, f"scan_{datetime.now().strftime('%Y%m%d')}.csv")
            results.to_csv(filepath, index=False, encoding="utf-8-sig")

        push_scan(results)
        print(f"[{datetime.now()}] 每日任务完成")
    except Exception as e:
        push(f"每日任务执行失败：{e}", "SmileX 错误告警")


def sync_market_overview():
    """同步大盘概览数据：市场统计 + 指数K线"""
    print(f"[{datetime.now()}] 同步大盘概览数据...")
    try:
        quote = realtime_quote()
        if not quote.empty:
            col_name = "涨跌幅"
            if col_name not in quote.columns:
                candidates = [c for c in quote.columns if "涨跌" in c]
                if candidates:
                    col_name = candidates[0]

            total = len(quote)
            up_count = len(quote[quote[col_name] > 0])
            down_count = len(quote[quote[col_name] < 0])
            flat_count = total - up_count - down_count
            limit_up = len(quote[quote[col_name] >= 9.9])
            limit_down = len(quote[quote[col_name] <= -9.9])

            save_market_stats(total, up_count, down_count, flat_count, limit_up, limit_down)

        sync_index_data()
        print(f"[{datetime.now()}] 大盘概览数据同步完成")
    except Exception as e:
        print(f"大盘概览同步失败: {e}")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "enabled": False,
        "hour": 15,
        "minute": 30,
        "strategy_name": "trend_following",
        "news_sync_enabled": False,
        "news_sync_interval": 30,
        "market_sync_enabled": False,
        "market_sync_interval": 60,
    }


def save_config(cfg: dict):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def start_scheduler(st_state, hour: int, minute: int, strategy_name: str = "trend_following"):
    scheduler = st_state.get("_scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)

    cfg = load_config()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_job, "cron", hour=hour, minute=minute,
                      id="daily_scan", replace_existing=True,
                      kwargs={"strategy_name": strategy_name})

    if cfg.get("market_sync_enabled"):
        interval = cfg.get("market_sync_interval", 60)
        scheduler.add_job(sync_market_overview, "interval", seconds=interval,
                          id="market_sync", replace_existing=True)

    if cfg.get("news_sync_enabled"):
        from smilex.news_sync import sync_all_news
        interval = cfg.get("news_sync_interval", 30)
        scheduler.add_job(sync_all_news, "interval", seconds=interval,
                          id="news_sync", replace_existing=True)

    scheduler.start()
    st_state["_scheduler"] = scheduler
    cfg.update({"enabled": True, "hour": hour, "minute": minute, "strategy_name": strategy_name})
    save_config(cfg)


def stop_scheduler(st_state):
    scheduler = st_state.get("_scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    st_state["_scheduler"] = None
    cfg = load_config()
    cfg["enabled"] = False
    save_config(cfg)


def get_next_run_time(st_state) -> str:
    scheduler = st_state.get("_scheduler")
    if scheduler and scheduler.running:
        job = scheduler.get_job("daily_scan")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    return "-"


def get_scan_history() -> list[str]:
    if not os.path.exists(HISTORY_DIR):
        return []
    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith("scan_") and f.endswith(".csv")]
    files.sort(reverse=True)
    return files


def start_news_sync(st_state, interval_seconds: int = 30):
    """启动新闻同步后台任务"""
    from smilex.news_sync import sync_all_news

    scheduler = st_state.get("_scheduler")
    if scheduler is None:
        scheduler = BackgroundScheduler()
        st_state["_scheduler"] = scheduler

    existing = scheduler.get_job("news_sync")
    if existing:
        scheduler.remove_job("news_sync")

    if not scheduler.running:
        scheduler.start()

    scheduler.add_job(
        sync_all_news, "interval", seconds=interval_seconds,
        id="news_sync", replace_existing=True,
    )
    cfg = load_config()
    cfg["news_sync_enabled"] = True
    cfg["news_sync_interval"] = interval_seconds
    save_config(cfg)


def stop_news_sync(st_state):
    """停止新闻同步后台任务"""
    scheduler = st_state.get("_scheduler")
    if scheduler and scheduler.running:
        scheduler.remove_job("news_sync")
        daily_job = scheduler.get_job("daily_scan")
        if daily_job is None:
            scheduler.shutdown(wait=False)
            st_state["_scheduler"] = None
    cfg = load_config()
    cfg["news_sync_enabled"] = False
    save_config(cfg)


def start_market_sync(st_state, interval_seconds: int = 60):
    """启动大盘概览同步后台任务"""
    scheduler = st_state.get("_scheduler")
    if scheduler is None:
        scheduler = BackgroundScheduler()
        st_state["_scheduler"] = scheduler

    existing = scheduler.get_job("market_sync")
    if existing:
        scheduler.remove_job("market_sync")

    if not scheduler.running:
        scheduler.start()

    scheduler.add_job(
        sync_market_overview, "interval", seconds=interval_seconds,
        id="market_sync", replace_existing=True,
    )
    cfg = load_config()
    cfg["market_sync_enabled"] = True
    cfg["market_sync_interval"] = interval_seconds
    save_config(cfg)


def stop_market_sync(st_state):
    """停止大盘概览同步后台任务"""
    scheduler = st_state.get("_scheduler")
    if scheduler and scheduler.running:
        scheduler.remove_job("market_sync")
        if scheduler.get_job("daily_scan") is None and scheduler.get_job("news_sync") is None:
            scheduler.shutdown(wait=False)
            st_state["_scheduler"] = None
    cfg = load_config()
    cfg["market_sync_enabled"] = False
    save_config(cfg)
