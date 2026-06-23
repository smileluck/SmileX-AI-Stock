"""券商研报 AI 选股服务：规则过滤 → 多研报共识排序 → AI 深度分析。

异步任务管理参考 backend/app/services/stock.py 的 _running_rec_tasks 范式。
"""
import json
import logging
import threading
import time
from datetime import datetime

from app.database import db_session, get_connection
from app.services import llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 阈值与权重（可调）
# ---------------------------------------------------------------------------
LOOKBACK_DAYS = 90         # 半年内机构共识更稳定，14 天数据不足以支撑共识筛选
MIN_ORG_COUNT = 3          # 至少 3 家机构覆盖（"机构普遍看好"）
MIN_BUY_RATING = 2         # 至少 2 个买入/增持评级
MIN_UPSIDE_PCT = 10.0      # 有目标价的样本空间 ≥ 10%（仅作加分，不作硬过滤）
MAX_GAIN_60D = 30.0        # 60 日涨幅 ≤ 30%（"未大幅上涨"，避免追高）
TOP_PRE_FILTER = 60        # 拉历史 K 线前的预筛上限（控制新浪接口调用量）
TOP_N_CANDIDATES = 25      # AI 分析候选数上限
AI_BATCH_SIZE = 6          # AI 单批分析股票数

# 共识分权重：买入数 + 机构数 + 涨幅安全垫（去掉 upside_pct，目标价覆盖仅 3%）
W_BUY = 0.4
W_ORG = 0.3
W_SAFETY = 0.3

# 买入类评级（与 sources/research_eastmoney.py:BUY_LIKE_RATINGS 一致）
BUY_LIKE_RATINGS = ("买入", "增持")


# ---------------------------------------------------------------------------
# 异步任务管理
# ---------------------------------------------------------------------------
_running_pick_tasks: dict[tuple[str, str], dict] = {}
_pick_tasks_lock = threading.Lock()


def _set_pick_stage(key: tuple[str, str], stage: str) -> None:
    with _pick_tasks_lock:
        if key in _running_pick_tasks:
            _running_pick_tasks[key]["stage"] = stage


def _set_pick_progress(key: tuple[str, str], finished: int, total: int) -> None:
    with _pick_tasks_lock:
        if key in _running_pick_tasks:
            _running_pick_tasks[key]["finished"] = finished
            _running_pick_tasks[key]["total"] = total


def get_pick_task_status(trade_date: str, phase: str = "close") -> dict:
    """查询选股任务进度，供前端轮询。"""
    key = (trade_date, phase)
    with _pick_tasks_lock:
        task = _running_pick_tasks.get(key)
        if not task:
            return {
                "active": False, "status": "idle", "trade_date": trade_date,
                "phase": phase, "started_at": None, "finished_at": None,
                "stage": None, "finished": 0, "total": 0, "error": None,
            }
        return {
            "active": task["active"],
            "status": task.get("status", "idle"),
            "trade_date": trade_date,
            "phase": phase,
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "stage": task.get("stage"),
            "finished": task.get("finished", 0),
            "total": task.get("total", 0),
            "error": task.get("error"),
        }


# ---------------------------------------------------------------------------
# 三阶段算法
# ---------------------------------------------------------------------------

def _get_latest_close(code: str) -> float | None:
    """从 stock_daily 取最新收盘价。"""
    with db_session() as conn:
        row = conn.execute(
            "SELECT close FROM stock_daily WHERE code = ? AND close IS NOT NULL "
            "ORDER BY trade_date DESC LIMIT 1",
            (code,),
        ).fetchone()
    return row["close"] if row else None


def _fetch_history_gain(code: str, days: int = 60) -> dict | None:
    """从新浪 K 线接口拉历史，返回 60 日涨幅 + 高点回撤。

    直接请求接口并解析 var=(<json>) 格式（不复用 backfill_daily._fetch_hist_sina，
    该函数依赖的正则有 bug）。Returns:
        {"latest", "oldest", "gain_pct", "high", "drawdown_from_high"} 或 None
    """
    import re
    import requests
    try:
        # 6 位代码 → 新浪符号
        if code.startswith(("6", "5", "9")):
            sina_code = f"sh{code}"
        elif code.startswith(("0", "3", "2")):
            sina_code = f"sz{code}"
        elif code.startswith(("8", "4")):
            sina_code = f"bj{code}"
        else:
            sina_code = f"sz{code}"

        resp = requests.get(
            "https://quotes.sina.cn/cn/api/jsonp_v2.php/var=/CN_MarketDataService.getKLineData",
            params={"symbol": sina_code, "scale": 240, "ma": "no", "datalen": days + 15},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"},
            timeout=10,
        )
        # 解析 var=([{"day":"...","close":"..."}, ...]) 格式
        m = re.search(r"\((\[.*?\])\)", resp.text, re.DOTALL)
        if not m:
            return None
        records = json.loads(m.group(1))
        if not records or len(records) < 5:
            return None

        records = records[-days:]
        latest = float(records[-1]["close"])
        oldest = float(records[0]["close"])
        high = max(float(r["high"]) for r in records if r.get("high"))
        gain_pct = (latest - oldest) / oldest * 100 if oldest > 0 else 0
        drawdown = (latest - high) / high * 100 if high > 0 else 0
        return {
            "latest": latest,
            "oldest": oldest,
            "gain_pct": round(gain_pct, 2),
            "high": high,
            "drawdown_from_high": round(drawdown, 2),
        }
    except Exception:
        logger.debug("[research_pick] fetch history gain failed for %s", code, exc_info=True)
        return None


def _stage_filter(days: int = LOOKBACK_DAYS) -> list[dict]:
    """阶段1：规则过滤。

    流程：
    1. SQL 聚合：org_count >= MIN_ORG_COUNT 且 buy_rating_count >= MIN_BUY_RATING
    2. 预筛 TOP_PRE_FILTER 只（按 buy_rating_count + org_count 排）
    3. 对预筛候选批量补现价（stock_daily → 新浪实时接口）
    4. 对预筛候选拉 60 日 K 线，过滤 gain_pct <= MAX_GAIN_60D
    5. 算 upside_pct（有目标价的样本）
    """
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT je.value AS code,
                   COUNT(DISTINCT rr.id) AS report_count,
                   COUNT(DISTINCT rr.org) AS org_count,
                   AVG(rr.target_price) AS avg_target_price,
                   SUM(CASE WHEN rr.rating IN ('买入','增持') THEN 1 ELSE 0 END) AS buy_rating_count,
                   MAX(rr.publish_date) AS latest_publish
            FROM research_report rr, JSON_EACH(rr.stock_codes) je
            WHERE rr.publish_date >= date('now', ?)
              AND rr.report_type = 'stock'
              AND je.value != ''
            GROUP BY je.value
            HAVING buy_rating_count >= ? AND org_count >= ?
            ORDER BY buy_rating_count DESC, org_count DESC
            LIMIT ?
            """,
            (f"-{days} days", MIN_BUY_RATING, MIN_ORG_COUNT, TOP_PRE_FILTER),
        ).fetchall()

    if not rows:
        return []

    # 第一遍：取 stock_daily 现价，记录需要从新浪补的代码
    pending_codes: list[str] = []
    raw: list[dict] = []
    for r in rows:
        code = r["code"]
        latest_close = _get_latest_close(code)
        raw.append({
            "code": code,
            "report_count": r["report_count"],
            "org_count": r["org_count"],
            "buy_rating_count": r["buy_rating_count"],
            "avg_target_price": r["avg_target_price"],
            "latest_publish": r["latest_publish"],
            "current_price": latest_close,
        })
        if not latest_close:
            pending_codes.append(code)

    # 批量补现价
    if pending_codes:
        try:
            from app.services.stock import _fetch_stock_prices_from_sina
            price_map = _fetch_stock_prices_from_sina(pending_codes)
            for item in raw:
                if item["current_price"] is None:
                    p = price_map.get(item["code"], {})
                    cur = p.get("current")
                    if cur and cur > 0:
                        item["current_price"] = cur
        except Exception:
            logger.exception("[research_pick] fetch prices from sina failed")

    # 第二遍：拉 60 日 K 线，过滤涨幅，算 upside
    candidates = []
    for r in raw:
        code = r["code"]
        latest_close = r["current_price"]

        hist = _fetch_history_gain(code, days=60)
        gain_60d = hist.get("gain_pct") if hist else None
        drawdown = hist.get("drawdown_from_high") if hist else None

        # 涨幅过滤：有数据时严格过滤；无数据时跳过过滤（不强求，留给 AI 判断）
        if gain_60d is not None and gain_60d > MAX_GAIN_60D:
            logger.info("[research_pick] %s filtered out: 60d gain=%.1f%% > %.0f%%",
                        code, gain_60d, MAX_GAIN_60D)
            continue

        # 现价兜底：K 线现价 > stock_daily 现价 > 新浪实时
        if not latest_close and hist:
            latest_close = hist["latest"]

        avg_target = r["avg_target_price"]
        upside_pct = None
        if latest_close and avg_target and latest_close > 0:
            upside_pct = round((avg_target - latest_close) / latest_close * 100, 2)

        candidates.append({
            "code": code,
            "report_count": r["report_count"],
            "org_count": r["org_count"],
            "buy_rating_count": r["buy_rating_count"],
            "avg_target_price": round(avg_target, 2) if avg_target else None,
            "current_price": latest_close,
            "upside_pct": upside_pct,
            "gain_60d": gain_60d,
            "drawdown_from_high": drawdown,
            "latest_publish": r["latest_publish"],
        })
    return candidates


def _stage_rank(candidates: list[dict], top_n: int = TOP_N_CANDIDATES) -> list[dict]:
    """阶段2：共识排序。

    consensus_score = W_BUY * buy_rating_count
                    + W_ORG * org_count
                    + W_SAFETY * safety_score
    其中 safety_score = max(0, 1 - gain_60d / MAX_GAIN_60D)
    （涨幅越低分越高；涨超阈值的安全垫为 0；没数据的给中等 0.5）
    """
    for c in candidates:
        buy = c["buy_rating_count"]
        org = c["org_count"]
        gain = c.get("gain_60d")
        if gain is None:
            safety = 0.5
        elif gain <= 0:
            safety = 1.0
        else:
            safety = max(0.0, 1.0 - gain / MAX_GAIN_60D)
        c["safety_score"] = round(safety, 3)
        c["consensus_score"] = round(W_BUY * buy + W_ORG * org + W_SAFETY * safety, 3)
    candidates.sort(key=lambda x: x["consensus_score"], reverse=True)
    return candidates[:top_n]


def _get_stock_name(code: str) -> str:
    """优先 stock_daily.name，其次 research_report 里的 stock_name。"""
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM stock_daily WHERE code = ? ORDER BY trade_date DESC LIMIT 1",
            (code,),
        ).fetchone()
        if row and row["name"]:
            return row["name"]
        row = conn.execute(
            """
            SELECT extra FROM research_report
            WHERE stock_codes LIKE ? AND report_type='stock'
            ORDER BY publish_date DESC LIMIT 1
            """,
            (f'%"{code}"%',),
        ).fetchone()
        if row:
            try:
                extra = json.loads(row["extra"] or "{}")
                if extra.get("stock_name"):
                    return extra["stock_name"]
            except (json.JSONDecodeError, TypeError):
                pass
    return ""


def _get_fundamental(code: str) -> dict:
    """取最新基本面：ROE/营收增长/利润增长。"""
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT roe, revenue_growth, profit_growth, report_date
            FROM stock_fundamental
            WHERE code = ? ORDER BY report_date DESC LIMIT 1
            """,
            (code,),
        ).fetchone()
    if not row:
        return {}
    return {
        "roe": row["roe"],
        "revenue_growth": row["revenue_growth"],
        "profit_growth": row["profit_growth"],
        "report_date": row["report_date"],
    }


def _get_recent_reports_for_stock(code: str, limit: int = 5) -> list[dict]:
    """取该股最近 N 篇研报摘要给 AI 参考。"""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT title, org, rating, target_price, publish_date, summary, industry
            FROM research_report
            WHERE report_type='stock' AND stock_codes LIKE ?
            ORDER BY publish_date DESC LIMIT ?
            """,
            (f'%"{code}"%', limit),
        ).fetchall()
    return [dict(r) for r in rows]


_SYSTEM_PROMPT = """你是 A 股机构共识选股分析师。基于多家券商研报对候选股做最终判断。

输出 JSON 数组（仅输出 JSON，无任何额外文本），每个元素：
{
  "code": "股票代码",
  "name": "股票名称",
  "advice": "buy|watch|avoid",
  "buy_low": 数字或null,
  "buy_high": 数字或null,
  "stop_loss": 数字或null,
  "catalyst": "1-2句核心催化剂",
  "risk": "1-2句主要风险",
  "analysis": "1段综合分析(150字内)",
  "confidence": 0-1的浮点,
  "score": 0-100的整数
}

判断要点：
- buy：共识强烈（多家买入评级）+ 估值合理 + 催化剂明确
- watch：方向偏正面但有不确定性（估值偏高/催化剂未落地/市场情绪弱）
- avoid：评级分歧大 / 估值泡沫 / 高位风险明显
- buy_low/buy_high 给合理买入区间，stop_loss 给止损位（基于现价）
- confidence 反映信息充分度，score 综合吸引力
"""


def _build_user_prompt(batch: list[dict]) -> str:
    """构造每批 AI 输入。"""
    lines = ["以下是近期券商研报覆盖度较高的候选股，请逐只分析并输出 JSON 数组：\n"]
    for c in batch:
        code = c["code"]
        name = _get_stock_name(code)
        c["name"] = name
        fund = _get_fundamental(code)
        reports = _get_recent_reports_for_stock(code, limit=5)

        lines.append(f"### {code} {name}")
        lines.append(f"- 共识研报数：{c['report_count']}，机构数：{c['org_count']}，买入评级数：{c['buy_rating_count']}")
        if c.get("avg_target_price"):
            lines.append(f"- 平均目标价：{c['avg_target_price']}")
        if c.get("upside_pct") is not None:
            lines.append(f"- 目标价空间：{c['upside_pct']}%")
        lines.append(f"- 最新现价：{c.get('current_price')}")
        if fund:
            lines.append(
                f"- 基本面（{fund.get('report_date','')}）：ROE={fund.get('roe')}，"
                f"营收增长={fund.get('revenue_growth')}%，利润增长={fund.get('profit_growth')}%"
            )
        if reports:
            lines.append("- 近期研报要点：")
            for r in reports[:5]:
                tp = f"目标价{r['target_price']}" if r.get("target_price") else ""
                lines.append(
                    f"  · {r['publish_date']} {r['org']} [{r['rating']}] {tp} - {r['title']}"
                )
        lines.append("")
    lines.append("请输出 JSON 数组。")
    return "\n".join(lines)


def _stage_ai(candidates: list[dict], trade_date: str, task_key: tuple[str, str]) -> list[dict]:
    """阶段3：AI 深度分析（分批）。"""
    if not candidates:
        return []

    model_used = llm.get_model_for_function("research_pick")
    picks: list[dict] = []

    # 分批
    batches = [candidates[i:i + AI_BATCH_SIZE] for i in range(0, len(candidates), AI_BATCH_SIZE)]
    total_batches = len(batches)

    for idx, batch in enumerate(batches, 1):
        _set_pick_stage(task_key, f"AI 分析中（批 {idx}/{total_batches}）")
        try:
            user_prompt = _build_user_prompt(batch)
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            resp = llm.function_chat("research_pick", messages)
            arr = llm.parse_json_response(resp, expect="array")
            if not isinstance(arr, list):
                arr = []

            # 按 code 索引候选项以补充共识数据
            cand_by_code = {c["code"]: c for c in batch}
            for item in arr:
                code = item.get("code", "")
                if not code or code not in cand_by_code:
                    continue
                cand = cand_by_code[code]
                picks.append({
                    "trade_date": trade_date,
                    "code": code,
                    "name": item.get("name") or cand.get("name", ""),
                    "report_count": cand["report_count"],
                    "buy_rating_count": cand["buy_rating_count"],
                    "avg_target_price": cand.get("avg_target_price"),
                    "upside_pct": cand.get("upside_pct"),
                    "current_price": cand.get("current_price"),
                    "org_count": cand["org_count"],
                    "consensus_score": cand.get("consensus_score", 0),
                    "ai_advice": item.get("advice", ""),
                    "ai_buy_low": item.get("buy_low"),
                    "ai_buy_high": item.get("buy_high"),
                    "ai_stop_loss": item.get("stop_loss"),
                    "ai_catalyst": item.get("catalyst", ""),
                    "ai_risk": item.get("risk", ""),
                    "ai_analysis": item.get("analysis", ""),
                    "confidence": float(item.get("confidence") or 0),
                    "score": float(item.get("score") or 0),
                    "model_used": model_used,
                    "status": "done",
                })
        except Exception:
            logger.exception("[research_pick] AI batch %d failed", idx)
            # 失败的批次，候选项不入库（不强行写半成品）

    return picks


def _save_picks(picks: list[dict], trade_date: str) -> int:
    """保存选股结果到 research_pick 表。"""
    if not picks:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        # 先清掉当日旧记录（重跑场景）
        conn.execute("DELETE FROM research_pick WHERE trade_date = ?", (trade_date,))
        for p in picks:
            conn.execute(
                """
                INSERT INTO research_pick (
                    trade_date, code, name, report_count, buy_rating_count,
                    avg_target_price, upside_pct, current_price, org_count,
                    consensus_score, ai_advice, ai_buy_low, ai_buy_high,
                    ai_stop_loss, ai_catalyst, ai_risk, ai_analysis,
                    confidence, score, model_used, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["trade_date"], p["code"], p["name"],
                    p["report_count"], p["buy_rating_count"],
                    p["avg_target_price"], p["upside_pct"], p["current_price"],
                    p["org_count"], p["consensus_score"],
                    p["ai_advice"], p["ai_buy_low"], p["ai_buy_high"],
                    p["ai_stop_loss"], p["ai_catalyst"], p["ai_risk"], p["ai_analysis"],
                    p["confidence"], p["score"], p["model_used"], p["status"],
                    now, now,
                ),
            )
        conn.commit()
    return len(picks)


def _pick_worker(trade_date: str, phase: str) -> None:
    """后台线程：跑完整三阶段流程，更新任务状态。"""
    key = (trade_date, phase)
    try:
        _set_pick_stage(key, f"阶段1：规则过滤（近 {LOOKBACK_DAYS} 天研报 + 60 日涨幅 ≤ {MAX_GAIN_60D:.0f}%）")
        candidates = _stage_filter(days=LOOKBACK_DAYS)
        logger.info("[research_pick] stage1 filtered: %d candidates", len(candidates))

        if not candidates:
            # 写一条 skipped 占位
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with db_session() as conn:
                conn.execute("DELETE FROM research_pick WHERE trade_date = ?", (trade_date,))
                conn.execute(
                    """INSERT INTO research_pick
                       (trade_date, code, name, status, created_at, updated_at)
                       VALUES (?, '', '', 'skipped', ?, ?)""",
                    (trade_date, now, now),
                )
                conn.commit()
            with _pick_tasks_lock:
                if key in _running_pick_tasks:
                    _running_pick_tasks[key].update({
                        "active": False, "status": "completed", "stage": None,
                        "total": 0, "finished": 0,
                        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
            return

        _set_pick_stage(key, "阶段2：共识排序")
        ranked = _stage_rank(candidates)
        logger.info("[research_pick] stage2 ranked top %d", len(ranked))

        _set_pick_progress(key, 0, len(ranked))
        _set_pick_stage(key, f"阶段3：AI 深度分析（{len(ranked)} 只，分 {(len(ranked) + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE} 批）")
        picks = _stage_ai(ranked, trade_date, key)
        logger.info("[research_pick] stage3 ai picks: %d", len(picks))

        saved = _save_picks(picks, trade_date)

        with _pick_tasks_lock:
            if key in _running_pick_tasks:
                _running_pick_tasks[key].update({
                    "active": False, "status": "completed", "stage": None,
                    "total": len(ranked), "finished": saved,
                    "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
        logger.info("[research_pick] task done trade_date=%s picks=%d", trade_date, saved)
    except Exception as e:
        logger.exception("[research_pick] worker failed")
        with _pick_tasks_lock:
            if key in _running_pick_tasks:
                _running_pick_tasks[key].update({
                    "active": False, "status": "failed", "stage": None,
                    "error": str(e),
                    "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })


def start_pick_task(trade_date: str, phase: str = "close") -> dict:
    """立即启动后台选股任务。"""
    key = (trade_date, phase)
    with _pick_tasks_lock:
        existing = _running_pick_tasks.get(key)
        if existing and existing.get("active"):
            return {
                "started": False, "already_running": True,
                "trade_date": trade_date, "phase": phase,
                "started_at": existing.get("started_at"), "stage": existing.get("stage"),
            }
        _running_pick_tasks[key] = {
            "active": True, "status": "running",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": None, "stage": "初始化",
            "finished": 0, "total": 0, "error": None,
        }

    t = threading.Thread(target=_pick_worker, args=(trade_date, phase), daemon=True)
    t.start()
    logger.info("[research_pick] started trade_date=%s phase=%s", trade_date, phase)

    return {
        "started": True, "already_running": False,
        "trade_date": trade_date, "phase": phase,
        "started_at": _running_pick_tasks[key]["started_at"],
        "stage": _running_pick_tasks[key]["stage"],
    }


def generate_research_picks(trade_date: str | None = None, phase: str = "close") -> dict:
    """同步入口（定时任务用）。"""
    if not trade_date:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    with _pick_tasks_lock:
        existing = _running_pick_tasks.get((trade_date, phase))
        if existing and existing.get("active"):
            logger.info("[research_pick] already running trade_date=%s", trade_date)
        else:
            start_pick_task(trade_date, phase)

    while True:
        with _pick_tasks_lock:
            task = _running_pick_tasks.get((trade_date, phase))
            if not task or not task["active"]:
                break
        time.sleep(2)

    picks = get_picks_by_date(trade_date)
    return {"items": picks, "total": len(picks)}


# ---------------------------------------------------------------------------
# 查询接口
# ---------------------------------------------------------------------------

def get_picks_by_date(trade_date: str) -> list[dict]:
    """查指定日期的选股结果，按 score 降序。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM research_pick WHERE trade_date = ? ORDER BY score DESC, consensus_score DESC",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_latest_pick_date() -> str | None:
    """最近的选股日期（用于前端默认展示）。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT trade_date FROM research_pick ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        return row["trade_date"] if row else None
    finally:
        conn.close()


def get_pick_history(limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """历史选股日期汇总。"""
    conn = get_connection()
    try:
        total = conn.execute(
            "SELECT COUNT(DISTINCT trade_date) FROM research_pick"
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT trade_date,
                   COUNT(*) AS total_picks,
                   SUM(CASE WHEN ai_advice='buy' THEN 1 ELSE 0 END) AS buy_count,
                   SUM(CASE WHEN ai_advice='watch' THEN 1 ELSE 0 END) AS watch_count,
                   SUM(CASE WHEN ai_advice='avoid' THEN 1 ELSE 0 END) AS avoid_count,
                   ROUND(AVG(score), 1) AS avg_score
            FROM research_pick
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows], total
