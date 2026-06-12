from datetime import datetime

from app.database import get_connection


def get_watchlist_codes() -> set[str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT code FROM watchlist_stock").fetchall()
        return {r["code"] for r in rows}
    finally:
        conn.close()


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


def list_watchlist(trade_date: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        if trade_date is None:
            row = conn.execute("SELECT MAX(trade_date) AS trade_date FROM stock_daily").fetchone()
            trade_date = row["trade_date"] if row and row["trade_date"] else datetime.now().strftime("%Y-%m-%d")

        rows = conn.execute(
            """SELECT
                w.id AS watchlist_id,
                w.code,
                COALESCE(NULLIF(w.name, ''), sd.name, '') AS name,
                w.note,
                w.sort_order,
                w.created_at AS watchlist_created_at,
                w.updated_at AS watchlist_updated_at,
                sd.id,
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
                sd.super_large_net,
                sd.large_net,
                sd.medium_net,
                sd.small_net,
                sd.created_at
             FROM watchlist_stock w
             LEFT JOIN stock_daily sd ON sd.code = w.code AND sd.trade_date = ?
             ORDER BY w.sort_order ASC, w.created_at DESC""",
            (trade_date,),
        ).fetchall()
    finally:
        conn.close()

    items = [dict(r) for r in rows]
    for item in items:
        item["is_watchlist"] = True
        item["trade_date"] = item.get("trade_date") or trade_date
    return items


def add_watchlist_stock(code: str, name: str | None = None, note: str | None = None) -> dict:
    code = code.strip()
    stock_name = (name or "").strip() or _latest_stock_name(code)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO watchlist_stock (code, name, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(code) DO UPDATE SET
                   name = CASE WHEN excluded.name != '' THEN excluded.name ELSE watchlist_stock.name END,
                   note = excluded.note,
                   updated_at = excluded.updated_at""",
            (code, stock_name, note or "", now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM watchlist_stock WHERE code = ?", (code,)).fetchone()
        return dict(row)
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
