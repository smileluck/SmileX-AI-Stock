import json
import os
from datetime import datetime
from smilex.config import HISTORY_DIR


def push(message: str, title: str = "SmileX 选股通知"):
    """统一推送入口"""
    _print(message, title)
    _save_log(message, title)


def push_scan(results_df):
    """推送选股扫描结果"""
    if results_df.empty:
        push("今日无符合条件的推荐股票", "SmileX 选股结果")
        return

    lines = [f"共筛选出 {len(results_df)} 只股票："]
    for _, row in results_df.head(10).iterrows():
        lines.append(
            f"  {row['code']} {row['name']}  "
            f"价格:{row['price']}  涨跌:{row['change_pct']}%  "
            f"得分:{row['score']}  {row['reasons']}"
        )
    if len(results_df) > 10:
        lines.append(f"  ... 共 {len(results_df)} 只，详见看板")

    push("\n".join(lines), f"SmileX 每日推荐 ({datetime.now().strftime('%m-%d')})")


def _print(message: str, title: str):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    print(message)
    print(f"{'='*50}\n")


def _save_log(message: str, title: str):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    log_file = os.path.join(HISTORY_DIR, "notifications.jsonl")
    entry = {
        "time": datetime.now().isoformat(),
        "title": title,
        "message": message,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
