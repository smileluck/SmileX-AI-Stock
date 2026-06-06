"""Backfill sector historical capital flow data via akshare (East Money).

Finds sector_snapshot_item rows where capital flow fields are NULL,
fetches historical fund flow from EM via akshare, and updates the records.

Handles both industry and concept sectors, matching by code or name.

Usage:
  cd backend && python backfill_sector_capital_flow.py
"""

import sys
import time
from datetime import datetime, timedelta

import akshare as ak

from app.database import get_connection

DELAY = 1.5
BATCH_SIZE = 10
BATCH_PAUSE = 5.0


def backfill():
    conn = get_connection()

    sectors = conn.execute(
        """SELECT DISTINCT code, name, sector_type
           FROM sector_snapshot_item
           WHERE main_net_inflow IS NULL
           ORDER BY sector_type, name"""
    ).fetchall()

    if not sectors:
        print("No sectors with missing capital flow data. Nothing to do.")
        conn.close()
        return

    print(f"Found {len(sectors)} sectors with missing capital flow data")

    # Group by sector_type
    industry_sectors = [s for s in sectors if s["sector_type"] == "industry"]
    concept_sectors = [s for s in sectors if s["sector_type"] == "concept"]
    print(f"  Industry: {len(industry_sectors)}, Concept: {len(concept_sectors)}")

    total_updated = 0

    # Backfill industry sectors
    if industry_sectors:
        print("\n=== Backfilling industry sectors ===")
        total_updated += _backfill_group(conn, industry_sectors, "industry")

    # Backfill concept sectors
    if concept_sectors:
        print("\n=== Backfilling concept sectors ===")
        total_updated += _backfill_group(conn, concept_sectors, "concept")

    conn.close()
    print(f"\nDone! Total rows updated: {total_updated}")


def _backfill_group(conn, sectors: list, sector_type: str) -> int:
    total_updated = 0

    for i, s in enumerate(sectors):
        name = s["name"]
        code = s["code"]
        print(f"[{i+1}/{len(sectors)}] {name} ({code}) ... ", end="", flush=True)

        records = _fetch_hist(name, sector_type)
        if not records:
            print("no data")
            time.sleep(2)
            continue

        updated = 0
        for rec in records:
            # Try matching by code first, then by name
            for key, val in [("code", code), ("name", name)]:
                if not val:
                    continue
                res = conn.execute(
                    f"""UPDATE sector_snapshot_item
                       SET main_net_inflow=?, main_net_inflow_pct=?,
                           super_large_net=?, large_net=?, medium_net=?, small_net=?
                       WHERE trade_date=? AND sector_type=? AND {key}=?
                         AND main_net_inflow IS NULL""",
                    (rec["main_net_inflow"], rec["main_net_inflow_pct"],
                     rec["super_large_net"], rec["large_net"],
                     rec["medium_net"], rec["small_net"],
                     rec["trade_date"], sector_type, val),
                )
                updated += res.rowcount

        conn.commit()
        total_updated += updated
        print(f"{len(records)} days fetched, {updated} rows updated")

        if (i + 1) % BATCH_SIZE == 0:
            print(f"  --- batch pause {BATCH_PAUSE}s ---")
            time.sleep(BATCH_PAUSE)
        else:
            time.sleep(DELAY)

    return total_updated


def _fetch_hist(name: str, sector_type: str) -> list[dict]:
    """Fetch historical capital flow for a sector via akshare."""
    try:
        if sector_type == "industry":
            df = ak.stock_sector_fund_flow_hist(symbol=name)
        else:
            df = ak.stock_concept_fund_flow_hist(symbol=name)
    except Exception:
        print(f"fetch err, ", end="", flush=True)
        return []

    if df is None or df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        date_val = row.get("日期")
        if date_val is None:
            continue
        records.append({
            "trade_date": str(date_val.date()) if hasattr(date_val, "date") else str(date_val),
            "main_net_inflow": _f(row.get("主力净流入-净额")),
            "main_net_inflow_pct": _f(row.get("主力净流入-净占比")),
            "super_large_net": _f(row.get("超大单净流入-净额")),
            "large_net": _f(row.get("大单净流入-净额")),
            "medium_net": _f(row.get("中单净流入-净额")),
            "small_net": _f(row.get("小单净流入-净额")),
        })
    return records


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    backfill()
