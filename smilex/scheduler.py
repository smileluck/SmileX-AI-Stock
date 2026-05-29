import os
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from smilex.config import HISTORY_DIR
from smilex.store import init_db, save_stock_list, update_daily
from smilex.fetcher import stock_list
from smilex.scanner import daily_scan
from smilex.notify import push, push_scan

CONFIG_FILE = os.path.join(HISTORY_DIR, "scheduler_config.json")


def run_daily_job():
    """执行每日收盘后任务"""
    print(f"[{datetime.now()}] 开始每日任务...")
    try:
        init_db()
        stocks = stock_list()
        save_stock_list(stocks)
        print(f"  股票列表已更新 ({len(stocks)} 只)")

        codes = stocks["code"].head(300).tolist()
        update_daily(codes)
        print("  日K数据已更新")

        results = daily_scan()
        print(f"  选股扫描完成，推荐 {len(results)} 只")

        if not results.empty:
            os.makedirs(HISTORY_DIR, exist_ok=True)
            filepath = os.path.join(HISTORY_DIR, f"scan_{datetime.now().strftime('%Y%m%d')}.csv")
            results.to_csv(filepath, index=False, encoding="utf-8-sig")

        push_scan(results)
        print(f"[{datetime.now()}] 每日任务完成")
    except Exception as e:
        push(f"每日任务执行失败：{e}", "SmileX 错误告警")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"enabled": False, "hour": 15, "minute": 30}


def save_config(cfg: dict):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def start_scheduler(st_state, hour: int, minute: int):
    scheduler = st_state.get("_scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_job, "cron", hour=hour, minute=minute,
                      id="daily_scan", replace_existing=True)
    scheduler.start()
    st_state["_scheduler"] = scheduler
    save_config({"enabled": True, "hour": hour, "minute": minute})


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
