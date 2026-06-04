"""Backfill sector history data. Supports East Money and THS (同花顺) sources.

Strategy:
  1. Try East Money (push2his) first — matches real-time data board codes.
  2. If blocked, fall back to THS (同花顺) via akshare — different board codes.
  3. Auto-skip boards that already have history.

Usage:
  python backfill_sector.py          # auto-detect source
  python backfill_sector.py --source em
  python backfill_sector.py --source ths
"""

import argparse
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.database import get_connection

# ── Shared settings ──
DELAY_EM = 1.0
DELAY_THS = 1.0
BATCH_SIZE = 10
BATCH_PAUSE = 5.0

# ── East Money helpers ──
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def _em_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.0, status_forcelist=[502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def em_test_available() -> bool:
    """Quick check if push2his API is reachable."""
    try:
        r = _em_session().get(
            "http://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": "90.BK0437",
                "fields1": "f1,f2,f3",
                "fields2": "f51,f52,f53",
                "klt": "101", "fqt": "0",
                "beg": datetime.now().strftime("%Y%m%d"),
                "end": datetime.now().strftime("%Y%m%d"),
                "lmt": "1",
            },
            headers=_EM_HEADERS,
            timeout=10,
        )
        klines = r.json().get("data", {}).get("klines", [])
        return len(klines) > 0
    except Exception:
        return False


def em_fetch_kline(secid: str, start: str, end: str) -> list[dict]:
    """Fetch daily kline from East Money. Returns list of {trade_date, name, price, change_pct, change, volume, amount}."""
    try:
        r = _em_session().get(
            "http://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101", "fqt": "0",
                "beg": start, "end": end, "lmt": "365",
            },
            headers=_EM_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        klines = data.get("klines", [])
        name = data.get("name", "")
        records = []
        for line in klines:
            p = line.split(",")
            if len(p) < 11:
                continue
            records.append({
                "trade_date": p[0],
                "name": name,
                "price": _f(p[2]),
                "change_pct": _f(p[9]),
                "change": _f(p[10]),
                "volume": _f(p[5]),
                "amount": _f(p[6]),
            })
        return records
    except Exception:
        return []


# ── THS helpers ──
def ths_fetch_kline(board_name: str, sector_type: str, start: str, end: str) -> list[dict]:
    """Fetch daily kline from THS via akshare. Returns list of {trade_date, name, price, change_pct, change, volume, amount}."""
    import akshare as ak

    func = ak.stock_board_industry_index_ths if sector_type == "industry" else ak.stock_board_concept_index_ths
    try:
        df = func(symbol=board_name, start_date=start, end_date=end)
    except Exception:
        return []

    if df is None or len(df) == 0:
        return []

    closes = df["收盘价"].astype(float)
    pcts = closes.pct_change() * 100
    pcts.iloc[0] = 0

    records = []
    for j, (_, row) in enumerate(df.iterrows()):
        pct = float(pcts.iloc[j]) if pd.notna(pcts.iloc[j]) else None
        price = float(row["收盘价"]) if pd.notna(row["收盘价"]) else None
        change_val = None
        if pct is not None and price is not None:
            change_val = price - price / (1 + pct / 100)
        records.append({
            "trade_date": str(row["日期"])[:10],
            "name": board_name,
            "price": price,
            "change_pct": pct,
            "change": change_val,
            "volume": float(row["成交量"]) if pd.notna(row["成交量"]) else None,
            "amount": float(row["成交额"]) if pd.notna(row["成交额"]) else None,
        })
    return records


def ths_get_board_list(sector_type: str) -> list[tuple[str, str]]:
    """Return [(code, name), ...] from THS."""
    import akshare as ak
    func = ak.stock_board_industry_name_ths if sector_type == "industry" else ak.stock_board_concept_name_ths
    df = func()
    return [(str(r["code"]), str(r["name"])) for _, r in df.iterrows()]


# ── Shared helpers ──
def _f(v: str) -> float | None:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _insert_records(conn, records: list[dict], board_code: str, board_name: str,
                    sector_type: str, now: str) -> int:
    """Insert fetched records into DB. Returns count of new inserts."""
    inserted = 0
    for rec in records:
        td = rec["trade_date"]

        snap = conn.execute(
            "SELECT id FROM sector_snapshot WHERE trade_date=? AND sector_type=?",
            (td, sector_type),
        ).fetchone()
        if not snap:
            cur = conn.execute(
                "INSERT INTO sector_snapshot (trade_date, sector_type, item_count, status, created_at) VALUES (?,?,0,'ok',?)",
                (td, sector_type, now),
            )
            snap_id = cur.lastrowid
        else:
            snap_id = snap["id"]

        exists = conn.execute(
            "SELECT 1 FROM sector_snapshot_item WHERE trade_date=? AND sector_type=? AND code=?",
            (td, sector_type, board_code),
        ).fetchone()
        if exists:
            continue

        conn.execute(
            """INSERT INTO sector_snapshot_item
               (snapshot_id, trade_date, sector_type, code, name,
                price, change_pct, change, volume, amount)
               VALUES (?,?,?,?,?, ?,?,?,?,?)""",
            (snap_id, td, sector_type, board_code, board_name,
             rec["price"], rec["change_pct"], rec["change"],
             rec["volume"], rec["amount"]),
        )
        inserted += 1
    return inserted


# ── Backfill via East Money ──
def backfill_em(conn, start: str, end: str, today: str, now: str):
    """Backfill using East Money push2his API. Board codes match real-time data."""
    from app.services.sector import _fetch_sector_list, INDUSTRY_FS, CONCEPT_FS, _SECTOR_FIELDS

    print("\n" + "=" * 60)
    print("Source: East Money (push2his)")
    print("=" * 60)

    for sector_type, fs in [("industry", INDUSTRY_FS), ("concept", CONCEPT_FS)]:
        print(f"\n--- {sector_type} ---")
        boards_raw = _fetch_sector_list(fs, _SECTOR_FIELDS)
        boards = [(b.get("f12", ""), b.get("f14", "")) for b in boards_raw if b.get("f12")]
        print(f"Found {len(boards)} boards")

        total = 0
        for i, (code, name) in enumerate(boards):
            existing = conn.execute(
                "SELECT COUNT(*) FROM sector_snapshot_item WHERE code=? AND sector_type=? AND trade_date < ?",
                (code, sector_type, today),
            ).fetchone()[0]
            if existing > 0:
                print(f"[{i+1}/{len(boards)}] {name} ({code}) ... skip ({existing})")
                continue

            print(f"[{i+1}/{len(boards)}] {name} ({code}) ... ", end="", flush=True)
            records = em_fetch_kline(f"90.{code}", start, end)
            if not records:
                print("no data")
                time.sleep(2)
                continue

            inserted = _insert_records(conn, records, code, name, sector_type, now)
            total += inserted
            print(f"{len(records)} days, {inserted} new")
            conn.commit()

            if (i + 1) % BATCH_SIZE == 0:
                print(f"  --- batch pause {BATCH_PAUSE}s ---")
                time.sleep(BATCH_PAUSE)
            else:
                time.sleep(DELAY_EM)

        print(f"{sector_type} total: {total}")


# ── Backfill via THS ──
def backfill_ths(conn, start: str, end: str, today: str, now: str):
    """Backfill using THS (同花顺) via akshare."""
    import akshare as ak

    print("\n" + "=" * 60)
    print("Source: THS (同花顺) via akshare")
    print("=" * 60)

    for sector_type in ["industry", "concept"]:
        print(f"\n--- {sector_type} ---")
        try:
            boards = ths_get_board_list(sector_type)
        except Exception as e:
            print(f"Failed to get board list: {e}")
            continue

        print(f"Found {len(boards)} boards")
        total = 0

        for i, (code, name) in enumerate(boards):
            existing = conn.execute(
                "SELECT COUNT(*) FROM sector_snapshot_item WHERE code=? AND sector_type=? AND trade_date < ?",
                (code, sector_type, today),
            ).fetchone()[0]
            if existing > 0:
                print(f"[{i+1}/{len(boards)}] {name} ({code}) ... skip ({existing})")
                continue

            print(f"[{i+1}/{len(boards)}] {name} ({code}) ... ", end="", flush=True)
            records = ths_fetch_kline(name, sector_type, start, end)
            if not records:
                print("no data")
                time.sleep(1)
                continue

            inserted = _insert_records(conn, records, code, name, sector_type, now)
            total += inserted
            print(f"{len(records)} days, {inserted} new")
            conn.commit()

            if (i + 1) % BATCH_SIZE == 0:
                print(f"  --- batch pause {BATCH_PAUSE}s ---")
                time.sleep(BATCH_PAUSE)
            else:
                time.sleep(DELAY_THS)

        print(f"{sector_type} total: {total}")


# ── Main ──
def backfill(source: str = "auto"):
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine source
    if source == "auto":
        print("Auto-detecting data source...")
        if em_test_available():
            source = "em"
            print("East Money API is available, using EM source.")
        else:
            source = "ths"
            print("East Money API is blocked, falling back to THS source.")

    if source == "em":
        backfill_em(conn, start, end, today, now)
    else:
        backfill_ths(conn, start, end, today, now)

    # Update snapshot item counts
    conn.execute("""
        UPDATE sector_snapshot SET item_count = (
            SELECT COUNT(*) FROM sector_snapshot_item
            WHERE sector_snapshot_item.trade_date = sector_snapshot.trade_date
            AND sector_snapshot_item.sector_type = sector_snapshot.sector_type
        )
    """)
    conn.commit()
    conn.close()
    print("\nAll done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill sector history data")
    parser.add_argument("--source", choices=["auto", "em", "ths"], default="auto",
                        help="Data source: auto (detect), em (East Money), ths (同花顺)")
    args = parser.parse_args()
    backfill(args.source)
