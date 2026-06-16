import json
import logging
import re
import threading
from datetime import datetime

from app.database import get_connection
from app.services import llm
from app.services.news_sector_assoc import (
    get_sector_news_heat,
    get_top_news_for_sector,
    score_news_to_sectors,
)
from app.services.sector_strength import calc_sector_streak, get_sector_snapshot_top
from app.services.sector import snapshot_sector_data
from app.services.stock import snapshot_limit_up_data

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是A股资深短线策略分析师。任务：基于今日收盘数据，输出「明日板块策略」。

输入数据包含：今日板块涨幅排行、连续强势板块统计、板块新闻热度、候选个股池、大盘指数参考。

请严格按照以下 JSON 结构输出（外层 ```json 代码块包裹）：

```json
{
  "sectors": [
    {
      "rank": 1,
      "code": "BK0428",
      "name": "电力行业",
      "sector_type": "industry",
      "change_pct_today": 3.2,
      "streak_up_days": 4,
      "main_net_inflow_yi": 12.5,
      "news_count": 8,
      "news_avg_score": 7.5,
      "top_events": [{"title": "...", "source": "...", "impact": "..."}],
      "sustainability": "high",
      "sustainability_reason": "...",
      "tomorrow_outlook": "大概率继续走强 / 分化 / 退潮"
    }
  ],
  "stocks": [
    {
      "sector_code": "BK0428",
      "sector_name": "电力行业",
      "code": "600886",
      "name": "国投电力",
      "role": "领涨龙头",
      "entry_logic": "...",
      "watch_price_low": 12.5,
      "watch_price_high": 13.0,
      "stop_loss_price": 11.8,
      "target_price": 14.5,
      "risk_tags": ["高位放量"]
    }
  ],
  "strategy_advice": {
    "position_level": "5-7成",
    "style": "追涨主线",
    "market_bias": "偏多",
    "risk_warnings": ["..."],
    "actionable_summary": "明日整体策略 Markdown 段落，重点提醒仓位与节奏"
  }
}
```

输出要求：
1. sectors 数组选 TOP 5（行业或概念板块混合，按明日赚钱效应排序）
2. sustainability 必须明确给出 high/medium/low 三档之一，并说明判断依据
3. 每个推荐板块至少配 2-3 个代表个股，优先用候选池里出现过的代码；可以从 leading_stock / limit_up 板块字段补充
4. 个股 role 字段限：领涨龙头 / 补涨标的 / 情绪先锋 / 趋势中军
5. watch_price_low/high 必须基于当前价格给出合理区间，止损位用百分比换算（一般 -5% 至 -8%）
6. risk_warnings 至少 3 条
7. 整体输出必须为合法 JSON，不要在 JSON 外加多余文字
"""


def _row_to_dict(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    for field in ("content_json", "strategy_json"):
        d[field] = json.loads(d.get(field) or "{}")
    for field in ("sectors_json", "stocks_json"):
        d[field] = json.loads(d.get(field) or "[]")
    return d


def _collect_market_context(trade_date: str) -> str:
    """从 ai_daily_report 取已生成的收盘报告作为大盘参考。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT report_text FROM ai_daily_report WHERE trade_date=? AND status='completed'",
            (trade_date,),
        ).fetchone()
    finally:
        conn.close()
    if row and row["report_text"]:
        snippet = row["report_text"][:1500]
        return f"=== 今日收盘报告摘要 ===\n{snippet}"
    return "=== 今日收盘报告 ===\n暂无"


def _collect_sector_strength(trade_date: str) -> tuple[str, list[dict]]:
    streak = calc_sector_streak(trade_date, lookback_days=8, top_k=20)
    today_top = get_sector_snapshot_top(trade_date, top_k=20)

    if not streak and not today_top:
        return "=== 板块强势度数据 ===\n无板块快照", []

    # 合并去重，code + sector_type 为 key
    merged: dict[tuple[str, str], dict] = {}
    for s in streak:
        merged[(s["code"], s["sector_type"])] = s
    for s in today_top:
        key = (s["code"], s["sector_type"])
        if key not in merged:
            merged[key] = {
                "code": s["code"],
                "name": s["name"],
                "sector_type": s["sector_type"],
                "change_pct_today": s.get("change_pct"),
                "streak_up_days": 0,
                "avg_change_pct": s.get("change_pct") or 0,
                "cumulative_main_net_inflow": s.get("main_net_inflow") or 0,
                "best_single_day_pct": s.get("change_pct") or 0,
                "trading_days": 1,
                "leading_stock": s.get("leading_stock"),
                "leading_stock_code": s.get("leading_stock_code"),
                "leading_stock_change_pct": s.get("leading_stock_change_pct"),
                "up_count": s.get("up_count"),
                "down_count": s.get("down_count"),
                "main_net_inflow_today": s.get("main_net_inflow"),
            }

    candidates = sorted(
        merged.values(),
        key=lambda x: (
            x.get("streak_up_days", 0),
            x.get("change_pct_today") or 0,
            x.get("main_net_inflow_today") or 0,
        ),
        reverse=True,
    )[:25]

    lines = ["=== 板块强势度（综合排行 TOP25） ==="]
    for i, s in enumerate(candidates, 1):
        inflow = s.get("main_net_inflow_today") or 0
        inflow_yi = inflow / 1e8 if inflow else 0
        lines.append(
            f"{i}. [{s['sector_type']}] {s['code']} {s['name']} "
            f"今日{s.get('change_pct_today', 0):+.2f}% "
            f"连续{s.get('streak_up_days', 0)}日上涨 "
            f"主力净流入{inflow_yi:.2f}亿 "
            f"领涨股{s.get('leading_stock', 'N/A')}({s.get('leading_stock_code', '')})"
        )
    return "\n".join(lines), candidates


def _collect_news_heat(trade_date: str, candidates: list[dict]) -> tuple[str, dict[str, dict]]:
    heat = get_sector_news_heat(trade_date, top_k=30)
    if not heat:
        return "=== 板块新闻热度 ===\n暂无（评分未跑或无新闻）", {}

    heat_map: dict[str, dict] = {}
    for h in heat:
        key = f"{h['sector_code']}|{h['sector_type']}"
        heat_map[key] = h

    # 候选板块对应的热度
    matched = []
    for c in candidates:
        key = f"{c['code']}|{c['sector_type']}"
        if key in heat_map:
            h = heat_map[key]
            c["news_count"] = h["news_count"]
            c["news_avg_score"] = h["avg_score"]
            matched.append(
                f"{c['name']}: 新闻{h['news_count']}条 均分{h['avg_score']} 最高{h['max_score']}"
            )

    lines = ["=== 板块新闻热度（候选板块匹配） ==="]
    if matched:
        lines.extend(matched[:20])
    else:
        lines.append("候选板块暂无强相关新闻")
        # 兜底：展示热度 TOP10
        for h in heat[:10]:
            lines.append(f"{h['sector_name']}({h['sector_type']}): {h['news_count']}条 均分{h['avg_score']}")
    return "\n".join(lines), heat_map


def _collect_stock_pool(trade_date: str, candidates: list[dict]) -> tuple[str, list[dict]]:
    """候选股池：limit_up_snapshot 板块字段 + sector_snapshot_item.leading_stock。"""
    conn = get_connection()
    try:
        limit_up_rows = conn.execute(
            "SELECT code, name, sector, reason, change_pct, limit_up_times, amount "
            "FROM limit_up_snapshot WHERE trade_date=? ORDER BY amount DESC LIMIT 80",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    pool: list[dict] = []
    seen_codes = set()
    for r in limit_up_rows:
        code = r["code"]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        pool.append(
            {
                "code": code,
                "name": r["name"],
                "sector_hint": r["sector"] or "",
                "reason": r["reason"] or "",
                "limit_up_times": r["limit_up_times"] or 1,
                "amount_yi": (r["amount"] or 0) / 1e8,
                "source": "limit_up",
            }
        )

    # 板块领涨股补充
    for c in candidates[:10]:
        code = c.get("leading_stock_code")
        if code and code not in seen_codes:
            seen_codes.add(code)
            pool.append(
                {
                    "code": code,
                    "name": c.get("leading_stock") or "",
                    "sector_hint": c["name"],
                    "reason": f"领涨{c['name']}",
                    "limit_up_times": 0,
                    "amount_yi": 0,
                    "source": "leading_stock",
                }
            )

    if not pool:
        return "=== 候选个股池 ===\n暂无（无涨停股/无领涨股）", []

    lines = [f"=== 候选个股池（共{len(pool)}只） ==="]
    for i, s in enumerate(pool[:40], 1):
        tag = "涨停" if s["source"] == "limit_up" else "领涨"
        lines.append(
            f"{i}. [{tag}] {s['code']} {s['name']} "
            f"板块:{s['sector_hint'] or 'N/A'} "
            f"理由:{s['reason'][:30] if s['reason'] else 'N/A'}"
        )
    return "\n".join(lines), pool


def _build_prompt(
    trade_date: str,
    sector_text: str,
    news_text: str,
    stock_text: str,
    market_text: str,
) -> list[dict]:
    user_content = (
        f"=== 交易日期: {trade_date} ===\n\n"
        f"{market_text}\n\n"
        f"{sector_text}\n\n"
        f"{news_text}\n\n"
        f"{stock_text}\n\n"
        "请基于以上数据，输出明日板块策略 JSON。"
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_json_block(raw: str) -> dict:
    """从 LLM 文本中抽取 JSON 对象，兼容 ```json 代码块和裸 JSON。"""
    if not raw:
        return {}

    # 优先匹配 ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # 直接尝试整段
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # 兜底：找第一个 { 到最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _enrich_sectors_with_news(sectors: list[dict], trade_date: str) -> list[dict]:
    """为每个推荐板块补 top_events（从 news_sector_association 查）。"""
    for s in sectors:
        code = s.get("code")
        if not code:
            continue
        try:
            top_news = get_top_news_for_sector(trade_date, code, limit=3)
        except Exception:
            top_news = []
        if top_news and not s.get("top_events"):
            s["top_events"] = [
                {
                    "title": n["title"],
                    "source": n["source"],
                    "impact": f"{n.get('impact_score', 0)}分/{n.get('impact_category', '其他')}",
                }
                for n in top_news
            ]
    return sectors


def _ensure_data_ready(trade_date: str) -> None:
    """检查 sector_snapshot_item 和 limit_up_snapshot 当日是否有数据，缺失则自动补采。

    采集失败只记 warning 不抛异常，让主流程继续跑（即使部分数据为空也能输出策略）。
    """
    conn = get_connection()
    try:
        sector_count = conn.execute(
            "SELECT COUNT(*) AS c FROM sector_snapshot_item WHERE trade_date=?",
            (trade_date,),
        ).fetchone()
        limit_up_count = conn.execute(
            "SELECT COUNT(*) AS c FROM limit_up_snapshot WHERE trade_date=?",
            (trade_date,),
        ).fetchone()
    finally:
        conn.close()

    sector_missing = not sector_count or sector_count["c"] == 0
    limit_up_missing = not limit_up_count or limit_up_count["c"] == 0

    if not sector_missing and not limit_up_missing:
        return

    logger.warning(
        "数据缺失，触发自动补采 trade_date=%s sector=%s limit_up=%s",
        trade_date,
        "缺" if sector_missing else "有",
        "缺" if limit_up_missing else "有",
    )

    if sector_missing:
        try:
            result = snapshot_sector_data(trade_date=trade_date, trigger="auto_for_strategy")
            logger.info("板块快照补采完成 trade_date=%s result=%s", trade_date, result)
        except Exception:
            logger.exception("板块快照补采失败 trade_date=%s", trade_date)

    if limit_up_missing:
        try:
            result = snapshot_limit_up_data(trade_date=trade_date, trigger="auto_for_strategy")
            logger.info("涨停快照补采完成 trade_date=%s result=%s", trade_date, result)
        except Exception:
            logger.exception("涨停快照补采失败 trade_date=%s", trade_date)


def _persist(trade_date: str, parsed: dict, raw: str, model_used: str) -> dict:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sectors = parsed.get("sectors", []) if isinstance(parsed, dict) else []
    stocks = parsed.get("stocks", []) if isinstance(parsed, dict) else []
    strategy = parsed.get("strategy_advice", {}) if isinstance(parsed, dict) else {}

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM tomorrow_strategy WHERE trade_date=?", (trade_date,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE tomorrow_strategy SET content_json=?, raw_text=?, sectors_json=?, "
                "stocks_json=?, strategy_json=?, model_used=?, status='completed', updated_at=? "
                "WHERE id=?",
                (
                    json.dumps(parsed, ensure_ascii=False),
                    raw,
                    json.dumps(sectors, ensure_ascii=False),
                    json.dumps(stocks, ensure_ascii=False),
                    json.dumps(strategy, ensure_ascii=False),
                    model_used,
                    now_str,
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                "INSERT INTO tomorrow_strategy "
                "(trade_date, content_json, raw_text, sectors_json, stocks_json, strategy_json, "
                "model_used, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,'completed',?,?)",
                (
                    trade_date,
                    json.dumps(parsed, ensure_ascii=False),
                    raw,
                    json.dumps(sectors, ensure_ascii=False),
                    json.dumps(stocks, ensure_ascii=False),
                    json.dumps(strategy, ensure_ascii=False),
                    model_used,
                    now_str,
                    now_str,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM tomorrow_strategy WHERE trade_date=?", (trade_date,)
        ).fetchone()
        return _row_to_dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run_strategy_sync(trade_date: str) -> dict:
    """同步执行完整策略生成流程（采集 → 新闻评分 → 上下文 → LLM → 解析 → 落库）。

    调用方应自行决定同步还是异步：定时任务可同步调用，HTTP 触发建议用 start_strategy_task。
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    # Step 0: 确保板块/涨停快照已采集，缺失则自动补采
    _ensure_data_ready(trade_date)

    # Step 1: 先跑新闻-板块评分（若已有数据则跳过）
    try:
        conn = get_connection()
        try:
            existing_assoc = conn.execute(
                "SELECT COUNT(*) AS c FROM news_sector_association WHERE trade_date=?",
                (trade_date,),
            ).fetchone()
        finally:
            conn.close()
        if existing_assoc and existing_assoc["c"] > 0:
            logger.info("news_sector_assoc 已存在 trade_date=%s count=%d", trade_date, existing_assoc["c"])
        else:
            score_result = score_news_to_sectors(trade_date, top_n=50)
            logger.info("news_sector_assoc 完成 %s", score_result)
    except Exception:
        logger.exception("新闻-板块评分失败，继续后续流程 trade_date=%s", trade_date)

    # Step 2: 收集上下文
    market_text = _collect_market_context(trade_date)
    sector_text, candidates = _collect_sector_strength(trade_date)
    news_text, heat_map = _collect_news_heat(trade_date, candidates)
    stock_text, pool = _collect_stock_pool(trade_date, candidates)

    if not candidates and not pool:
        raise RuntimeError(
            f"无可用的板块/个股数据 trade_date={trade_date}，"
            "已尝试自动补采但仍失败，可能是非交易日或上游数据源异常"
        )

    # Step 3: 构造 prompt + 调 LLM
    messages = _build_prompt(trade_date, sector_text, news_text, stock_text, market_text)
    logger.info("tomorrow_strategy prompt 构造完成 trade_date=%s", trade_date)

    try:
        raw = llm.function_chat("tomorrow_strategy", messages)
    except Exception:
        logger.exception("tomorrow_strategy LLM 调用失败 trade_date=%s", trade_date)
        raise

    model_used = llm.get_model_for_function("tomorrow_strategy")

    # Step 4: 解析
    parsed = _extract_json_block(raw)
    if not parsed:
        logger.warning("无法解析 LLM JSON 输出，落库 raw_text trade_date=%s", trade_date)
        parsed = {"sectors": [], "stocks": [], "strategy_advice": {}}

    # Step 5: 后处理（补 top_events）
    if isinstance(parsed.get("sectors"), list):
        parsed["sectors"] = _enrich_sectors_with_news(parsed["sectors"], trade_date)

    # Step 6: 落库
    return _persist(trade_date, parsed, raw, model_used)


# ---------------------------------------------------------------------------
# 异步任务管理（参考 limit_up_analysis 的后台线程 + 任务状态轮询范式）
# ---------------------------------------------------------------------------

_tasks_lock = threading.Lock()
_running_tasks: dict[str, dict] = {}


def get_strategy_task_status(trade_date: str) -> dict:
    """返回当前策略生成任务进度。"""
    with _tasks_lock:
        task = _running_tasks.get(trade_date)
        if not task:
            return {
                "active": False,
                "status": "idle",
                "trade_date": trade_date,
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
        return {
            "active": task["active"],
            "status": task.get("status", "idle"),
            "trade_date": trade_date,
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "stage": task.get("stage"),
            "error": task.get("error"),
        }


def _strategy_worker(trade_date: str) -> None:
    """后台线程：跑完整流程，更新任务状态。"""
    key = trade_date
    try:
        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["stage"] = "数据准备"

        def _set_stage(stage: str) -> None:
            with _tasks_lock:
                if key in _running_tasks:
                    _running_tasks[key]["stage"] = stage

        _set_stage("板块/涨停快照")
        _ensure_data_ready(trade_date)

        _set_stage("新闻-板块评分")
        try:
            conn = get_connection()
            try:
                existing_assoc = conn.execute(
                    "SELECT COUNT(*) AS c FROM news_sector_association WHERE trade_date=?",
                    (trade_date,),
                ).fetchone()
            finally:
                conn.close()
            if existing_assoc and existing_assoc["c"] > 0:
                logger.info("news_sector_assoc 已存在 trade_date=%s count=%d", trade_date, existing_assoc["c"])
            else:
                score_result = score_news_to_sectors(trade_date, top_n=50)
                logger.info("news_sector_assoc 完成 %s", score_result)
        except Exception:
            logger.exception("新闻-板块评分失败，继续后续流程 trade_date=%s", trade_date)

        _set_stage("LLM 分析中（最久环节，约 1-3 分钟）")
        market_text = _collect_market_context(trade_date)
        sector_text, candidates = _collect_sector_strength(trade_date)
        news_text, heat_map = _collect_news_heat(trade_date, candidates)
        stock_text, pool = _collect_stock_pool(trade_date, candidates)

        if not candidates and not pool:
            raise RuntimeError(
                f"无可用的板块/个股数据 trade_date={trade_date}，"
                "已尝试自动补采但仍失败，可能是非交易日或上游数据源异常"
            )

        messages = _build_prompt(trade_date, sector_text, news_text, stock_text, market_text)
        logger.info("tomorrow_strategy prompt 构造完成 trade_date=%s", trade_date)

        try:
            raw = llm.function_chat("tomorrow_strategy", messages)
        except Exception:
            logger.exception("tomorrow_strategy LLM 调用失败 trade_date=%s", trade_date)
            raise

        _set_stage("结果解析与落库")
        model_used = llm.get_model_for_function("tomorrow_strategy")
        parsed = _extract_json_block(raw)
        if not parsed:
            logger.warning("无法解析 LLM JSON 输出，落库 raw_text trade_date=%s", trade_date)
            parsed = {"sectors": [], "stocks": [], "strategy_advice": {}}
        if isinstance(parsed.get("sectors"), list):
            parsed["sectors"] = _enrich_sectors_with_news(parsed["sectors"], trade_date)
        _persist(trade_date, parsed, raw, model_used)

        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["active"] = False
                _running_tasks[key]["status"] = "completed"
                _running_tasks[key]["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _running_tasks[key]["stage"] = None
        logger.info("明日策略生成完成 trade_date=%s", trade_date)
    except Exception as e:
        logger.exception("明日策略生成任务异常 trade_date=%s", trade_date)
        with _tasks_lock:
            if key in _running_tasks:
                _running_tasks[key]["active"] = False
                _running_tasks[key]["status"] = "failed"
                _running_tasks[key]["error"] = str(e)
                _running_tasks[key]["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _running_tasks[key]["stage"] = None


def start_strategy_task(trade_date: str) -> dict:
    """启动后台策略生成任务，立即返回任务状态。

    返回值语义：
    - started=True: 新任务已启动
    - started=False + already_running=True: 已有任务在跑
    - started=False + no_data=True: 数据采集后仍无可用数据（仅在同步预检能判定时）
    """
    key = trade_date
    with _tasks_lock:
        existing = _running_tasks.get(key)
        if existing and existing.get("active"):
            return {
                "started": False,
                "already_running": True,
                "trade_date": trade_date,
                "started_at": existing.get("started_at"),
                "stage": existing.get("stage"),
            }

    with _tasks_lock:
        _running_tasks[key] = {
            "active": True,
            "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None,
            "stage": "初始化",
            "error": None,
        }

    t = threading.Thread(target=_strategy_worker, args=(trade_date,), daemon=True)
    t.start()
    logger.info("已启动明日策略生成任务 trade_date=%s", trade_date)

    return {
        "started": True,
        "already_running": False,
        "trade_date": trade_date,
        "started_at": _running_tasks[key]["started_at"],
        "stage": _running_tasks[key]["stage"],
    }


def generate_tomorrow_strategy(trade_date: str | None = None) -> dict:
    """同步入口（供定时任务 main.py 直接调用，与原签名兼容）。

    若已有同日任务在跑则直接复用，避免定时任务与手动触发重复执行。
    """
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    with _tasks_lock:
        existing = _running_tasks.get(trade_date)
        if existing and existing.get("active"):
            logger.info("已有同日策略任务在跑 trade_date=%s，跳过", trade_date)
            return get_strategy(trade_date) or {"trade_date": trade_date, "status": "running"}

    start_strategy_task(trade_date)
    # 同步等待完成（定时任务在后台线程，本函数需要阻塞到结束）
    import time
    while True:
        with _tasks_lock:
            task = _running_tasks.get(trade_date)
            if not task or not task["active"]:
                break
        time.sleep(2)
    return get_strategy(trade_date) or {"trade_date": trade_date, "status": "unknown"}


def get_latest_strategy() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tomorrow_strategy ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_strategy(date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tomorrow_strategy WHERE trade_date=?", (date,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_strategy_history(limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM tomorrow_strategy").fetchone()[0]
        rows = conn.execute(
            "SELECT id, trade_date, status, model_used, created_at, updated_at, "
            "json_array_length(sectors_json) AS sector_count, "
            "json_array_length(stocks_json) AS stock_count "
            "FROM tomorrow_strategy ORDER BY trade_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()
