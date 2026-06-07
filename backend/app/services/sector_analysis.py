import logging
from datetime import datetime

from app.database import get_connection
from app.services import llm
from app.services.sector import get_sector_history_by_date
from app.services.strategy import get_strategy_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位资深A股板块分析师，专注于行业和概念板块的深度研究。请根据以下板块数据，生成一份全面的板块分析报告。

报告要求包含以下板块，每个板块用明确的标题分隔：

## 一、行业板块概览
总结当日行业板块整体表现，涨跌比例、市场广度。

## 二、热门行业板块
分析领涨行业板块及其驱动因素（政策、事件、基本面变化等），指出持续性如何。

## 三、冷门行业板块
分析领跌行业板块及原因，是否存在超跌反弹机会。

## 四、概念板块亮点
分析热门概念板块，指出市场炒作主线和题材轮动方向。

## 五、资金流向分析
分析主力资金偏好，哪些板块受到资金追捧，哪些遭到抛售。

## 六、板块轮动趋势
根据近期数据判断板块轮动方向，哪些板块可能接棒。

## 七、明日板块展望
预测下一个交易日可能活跃的板块及逻辑。

要求：
- 语言专业简洁，重点突出
- 数据引用准确，涨跌幅、资金流向要有具体数字
- 每个板块 100-200 字
"""


def _row_to_dict(row) -> dict:
    d = dict(row)
    return d


def _build_sector_context(trade_date: str) -> str:
    lines = [f"=== 交易日期: {trade_date} ===\n"]

    for sector_type, label in [("industry", "行业板块"), ("concept", "概念板块")]:
        data = get_sector_history_by_date(trade_date, sector_type)
        items = data.get("items", [])
        if not items:
            lines.append(f"无{label}数据\n")
            continue

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


def generate_sector_analysis(trade_date: str | None = None) -> dict:
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM sector_analysis WHERE trade_date=?", (trade_date,)
        ).fetchone()
        if existing and existing["status"] == "completed":
            return _row_to_dict(existing)

        context = _build_sector_context(trade_date)

        messages = [
            {"role": "system", "content": get_strategy_prompt("sector_analysis", _SYSTEM_PROMPT)},
            {"role": "user", "content": context},
        ]
        analysis_text = llm.analysis_chat(messages)

        if existing:
            conn.execute(
                "UPDATE sector_analysis SET analysis_text=?, model_used=?, status='completed', updated_at=? WHERE id=?",
                (analysis_text, llm.get_model_for_function("sector_analysis"), now_str, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO sector_analysis (trade_date, analysis_text, model_used, status, created_at, updated_at) "
                "VALUES (?,?,?,'completed',?,?)",
                (trade_date, analysis_text, llm.get_model_for_function("sector_analysis"), now_str, now_str),
            )
        conn.commit()

        result = conn.execute("SELECT * FROM sector_analysis WHERE trade_date=?", (trade_date,)).fetchone()
        return _row_to_dict(result)
    except Exception:
        conn.rollback()
        logger.exception("生成板块分析失败 trade_date=%s", trade_date)
        raise
    finally:
        conn.close()


def get_latest_sector_analysis() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM sector_analysis ORDER BY trade_date DESC LIMIT 1").fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_sector_analysis_history(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM sector_analysis").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM sector_analysis ORDER BY trade_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()
