"""自选股 / 自选板块 服务层。

关注股支持手动添加、从推荐一键加入、从板块成分股加入；
记录 add_price 作为买入时机分析基准；
每日行情快照与 stock_daily 解耦（watchlist_stock_daily）。
"""
from datetime import datetime
import logging

from app.database import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _latest_stock_name(code: str) -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT name FROM stock_daily WHERE code = ? ORDER BY trade_date DESC LIMIT 1",
            (code,),
        ).fetchone()
        return row["name"] if row else ""
    finally:
        conn.close()


def _fetch_spot(code: str) -> dict | None:
    """实时完整行情（OHLC + 资金流），用于 add_price 回填、search、snapshot。

    复用 stock_daily._fetch_one_stock_spot（东方财富主、新浪备）；任何异常吞掉返回 None。
    """
    try:
        from app.services.stock_daily import _fetch_one_stock_spot
        return _fetch_one_stock_spot(code)
    except Exception:
        logger.warning("fetch spot failed for %s", code, exc_info=True)
        return None


def get_watchlist_codes() -> set[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT code FROM watchlist_stock WHERE status = 'watching'"
        ).fetchall()
        return {r["code"] for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 关注股 CRUD
# ---------------------------------------------------------------------------

def list_watchlist(trade_date: str | None = None) -> list[dict]:
    """返回自选股列表，LEFT JOIN 当日 stock_daily + 最新一条 watchlist_analysis。"""
    conn = get_connection()
    try:
        if trade_date is None:
            row = conn.execute("SELECT MAX(trade_date) AS trade_date FROM stock_daily").fetchone()
            trade_date = row["trade_date"] if row and row["trade_date"] else _today()

        rows = conn.execute(
            """SELECT
                w.id AS watchlist_id,
                w.code,
                COALESCE(NULLIF(w.name, ''), sd.name, '') AS name,
                w.note,
                w.sort_order,
                w.add_price,
                w.add_date,
                w.target_buy_price,
                w.stop_loss_price,
                w.status,
                w.source,
                w.custom_sector_id,
                w.created_at AS watchlist_created_at,
                w.updated_at AS watchlist_updated_at,
                cs.name AS custom_sector_name,
                sd.trade_date,
                sd.board,
                sd.open,
                sd.close,
                sd.high,
                sd.low,
                sd.prev_close,
                sd.change_pct,
                sd.change,
                sd.volume,
                sd.amount,
                sd.turnover_rate,
                sd.volume_ratio,
                sd.amplitude,
                sd.pe_ttm,
                sd.pe_static,
                sd.pb,
                sd.total_market_cap,
                sd.circulating_market_cap,
                sd.main_net_inflow,
                sd.main_net_inflow_pct,
                wa.suggested_action AS latest_action,
                wa.phase AS latest_phase,
                wa.confidence AS latest_confidence,
                wa.buy_low AS latest_buy_low,
                wa.buy_high AS latest_buy_high,
                wa.support_price AS latest_support,
                wa.resistance_price AS latest_resistance,
                wa.reason AS latest_reason,
                wa.trade_date AS latest_analysis_date
             FROM watchlist_stock w
             LEFT JOIN stock_daily sd ON sd.code = w.code AND sd.trade_date = ?
             LEFT JOIN watchlist_custom_sector cs ON cs.id = w.custom_sector_id
             LEFT JOIN watchlist_analysis wa ON wa.id = (
                 SELECT id FROM watchlist_analysis sub
                 WHERE sub.code = w.code
                 ORDER BY trade_date DESC, id DESC LIMIT 1
             )
             ORDER BY w.sort_order ASC, w.created_at DESC""",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    items = []
    for r in rows:
        item = dict(r)
        item["is_watchlist"] = True
        item["trade_date"] = item.get("trade_date") or trade_date
        # 距添加价涨跌幅（基于当日收盘）
        add_price = item.get("add_price")
        cur_close = item.get("close")
        if add_price and cur_close and add_price > 0:
            item["gain_since_add_pct"] = round((cur_close - add_price) / add_price * 100, 2)
        else:
            item["gain_since_add_pct"] = None
        items.append(item)
    return items


def add_watchlist_stock(
    code: str,
    name: str | None = None,
    note: str | None = None,
    add_price: float | None = None,
    target_buy: float | None = None,
    stop_loss: float | None = None,
    source: str = "manual",
    custom_sector_id: int | None = None,
) -> dict:
    """添加关注股。add_price 缺失时调 _fetch_one_stock_spot 自动回填。"""
    code = code.strip()
    stock_name = (name or "").strip() or _latest_stock_name(code)
    today = _today()
    now = _now()

    # add_price 缺失时实时回填
    resolved_price = add_price
    if resolved_price is None:
        spot = _fetch_spot(code)
        if spot:
            resolved_price = spot.get("close")
            if not stock_name:
                stock_name = spot.get("name", "") or stock_name

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO watchlist_stock
               (code, name, note, add_price, add_date, target_buy_price,
                stop_loss_price, status, source, custom_sector_id,
                sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'watching', ?, ?, 0, ?, ?)
               ON CONFLICT(code) DO UPDATE SET
                   name = CASE WHEN excluded.name != '' THEN excluded.name ELSE watchlist_stock.name END,
                   note = CASE WHEN excluded.note IS NOT NULL THEN excluded.note ELSE watchlist_stock.note END,
                   add_price = CASE WHEN watchlist_stock.add_price IS NULL THEN excluded.add_price ELSE watchlist_stock.add_price END,
                   add_date = CASE WHEN watchlist_stock.add_date IS NULL THEN excluded.add_date ELSE watchlist_stock.add_date END,
                   target_buy_price = COALESCE(excluded.target_buy_price, watchlist_stock.target_buy_price),
                   stop_loss_price = COALESCE(excluded.stop_loss_price, watchlist_stock.stop_loss_price),
                   status = 'watching',
                   source = excluded.source,
                   custom_sector_id = COALESCE(excluded.custom_sector_id, watchlist_stock.custom_sector_id),
                   updated_at = excluded.updated_at""",
            (
                code, stock_name, note or "",
                resolved_price, today, target_buy, stop_loss,
                source, custom_sector_id, now, now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM watchlist_stock WHERE code = ?", (code,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def upsert_from_recommendation(code: str, name: str | None, add_price: float | None) -> dict:
    """从推荐/涨停/板块页一键加入。幂等：已存在则不覆盖 add_price。"""
    return add_watchlist_stock(
        code=code,
        name=name,
        add_price=add_price,
        source="recommendation",
    )


def update_watchlist_stock(code: str, fields: dict) -> dict:
    """更新关注股字段：target_buy_price/stop_loss_price/status/note/custom_sector_id。"""
    allowed = {"target_buy_price", "stop_loss_price", "status", "note", "custom_sector_id", "name", "sort_order"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        row = get_watchlist_stock(code)
        return row

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [_now(), code]
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE watchlist_stock SET {set_clause}, updated_at = ? WHERE code = ?",
            params,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM watchlist_stock WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_watchlist_stock(code: str) -> dict:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM watchlist_stock WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def delete_watchlist_stock(code: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM watchlist_stock WHERE code = ?", (code,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_stock(q: str, limit: int = 20) -> list[dict]:
    """搜索股票：6 位代码走实时行情，名称/代码片段走 stock_daily LIKE。"""
    q = q.strip()
    if not q:
        return []

    # 纯 6 位代码：直接拉实时行情
    if q.isdigit() and len(q) == 6:
        spot = _fetch_spot(q)
        if spot and spot.get("close"):
            return [{
                "code": spot.get("code", q),
                "name": spot.get("name", ""),
                "price": spot.get("close"),
                "change_pct": spot.get("change_pct"),
                "pe_ttm": spot.get("pe_ttm"),
                "board": spot.get("board", ""),
            }]
        # 实时失败兜底查历史
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT code, name, close, change_pct FROM stock_daily "
                "WHERE code = ? ORDER BY trade_date DESC LIMIT 1",
                (q,),
            ).fetchone()
            return [dict(row)] if row else []
        finally:
            conn.close()

    # 名称/代码片段：走 stock_daily LIKE
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT code, MAX(name) AS name, MAX(close) AS close, MAX(change_pct) AS change_pct
               FROM stock_daily
               WHERE code LIKE ? OR name LIKE ?
               GROUP BY code
               LIMIT ?""",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_watchlist_daily(code: str, days: int = 30) -> list[dict]:
    """返回关注股近 N 日行情：优先 watchlist_stock_daily，不足部分补 stock_daily。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT trade_date, open, high, low, close, prev_close,
                      change_pct, change, volume, amount, turnover_rate,
                      main_net_inflow, main_net_inflow_pct, 'watchlist_stock_daily' AS src
               FROM watchlist_stock_daily
               WHERE code = ?
               ORDER BY trade_date DESC LIMIT ?""",
            (code, days),
        ).fetchall()
        wsd_dates = {r["trade_date"] for r in rows}

        if len(rows) < days:
            need = days - len(rows)
            extra = conn.execute(
                """SELECT trade_date, open, high, low, close, prev_close,
                          change_pct, change, volume, amount, turnover_rate,
                          main_net_inflow, main_net_inflow_pct, 'stock_daily' AS src
                   FROM stock_daily
                   WHERE code = ? AND trade_date NOT IN (
                       SELECT trade_date FROM watchlist_stock_daily WHERE code = ?
                   )
                   ORDER BY trade_date DESC LIMIT ?""",
                (code, code, need),
            ).fetchall()
            rows = list(rows) + list(extra)
    finally:
        conn.close()

    rows.sort(key=lambda r: r["trade_date"])
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 市场板块关注 CRUD
# ---------------------------------------------------------------------------

def list_market_sectors() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM watchlist_sector ORDER BY sector_type, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_market_sector(sector_name: str, sector_type: str, note: str = "") -> dict:
    sector_name = sector_name.strip()
    sector_type = sector_type.strip() or "industry"
    if not sector_name:
        raise ValueError("板块名不能为空")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO watchlist_sector (sector_name, sector_type, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(sector_name, sector_type) DO UPDATE SET
                   note = excluded.note, updated_at = excluded.updated_at""",
            (sector_name, sector_type, note, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM watchlist_sector WHERE sector_name = ? AND sector_type = ?",
            (sector_name, sector_type),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_market_sector(sector_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM watchlist_sector WHERE id = ?", (sector_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 自定义板块 CRUD
# ---------------------------------------------------------------------------

def list_custom_sectors() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT cs.*,
                   (SELECT COUNT(*) FROM watchlist_stock w WHERE w.custom_sector_id = cs.id
                    AND w.status = 'watching') AS stock_count
               FROM watchlist_custom_sector cs
               ORDER BY cs.sort_order, cs.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_custom_sector(name: str, note: str = "") -> dict:
    name = name.strip()
    if not name:
        raise ValueError("板块名不能为空")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO watchlist_custom_sector (name, note, sort_order, created_at, updated_at)
               VALUES (?, ?, 0, ?, ?)""",
            (name, note, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM watchlist_custom_sector WHERE rowid = last_insert_rowid()"
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_custom_sector(sector_id: int, fields: dict) -> dict:
    allowed = {"name", "note", "sort_order"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [_now(), sector_id]
        conn = get_connection()
        try:
            conn.execute(
                f"UPDATE watchlist_custom_sector SET {set_clause}, updated_at = ? WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM watchlist_custom_sector WHERE id = ?", (sector_id,)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def delete_custom_sector(sector_id: int) -> bool:
    conn = get_connection()
    try:
        # 先解除成分股关联（ON DELETE SET NULL 等价效果，SQLite 默认不强制 FK）
        conn.execute(
            "UPDATE watchlist_stock SET custom_sector_id = NULL WHERE custom_sector_id = ?",
            (sector_id,),
        )
        cur = conn.execute(
            "DELETE FROM watchlist_custom_sector WHERE id = ?", (sector_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_custom_sector_stock(sector_id: int, code: str, name: str | None = None) -> dict:
    """把股票加入自定义板块。

    若 watchlist_stock 中不存在该 code，则同时创建一条关注股记录（source='sector'）。
    """
    code = code.strip()
    if not get_watchlist_stock(code):
        add_watchlist_stock(code=code, name=name, source="sector", custom_sector_id=sector_id)
    return update_watchlist_stock(code, {"custom_sector_id": sector_id})


def remove_custom_sector_stock(sector_id: int, code: str) -> dict:
    """从自定义板块移除成分股（仅解除关联，不删除关注股记录）。"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE watchlist_stock SET custom_sector_id = NULL "
            "WHERE custom_sector_id = ? AND code = ?",
            (sector_id, code),
        )
        conn.commit()
    finally:
        conn.close()
    return get_watchlist_stock(code)


def list_custom_sector_stocks(sector_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT w.code, COALESCE(NULLIF(w.name, ''), sd.name, '') AS name,
                      w.add_price, w.add_date, w.status, w.source,
                      sd.close, sd.change_pct
               FROM watchlist_stock w
               LEFT JOIN stock_daily sd ON sd.code = w.code AND sd.trade_date = (
                   SELECT MAX(trade_date) FROM stock_daily
               )
               WHERE w.custom_sector_id = ?
               ORDER BY w.sort_order, w.created_at DESC""",
            (sector_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
