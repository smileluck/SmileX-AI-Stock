"""Backfill sector historical capital flow data from East Money.

Finds sector_snapshot_item rows where capital flow fields are NULL,
fetches historical fund flow from push2his API, and updates the records.

Supports both East Money BK codes (direct) and THS 881xxx codes (matched by name).

Usage:
  python backfill_sector_capital_flow.py
"""

import time
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.database import get_connection

DELAY = 1.5
BATCH_SIZE = 10
BATCH_PAUSE = 5.0

_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# Field mapping for fflow/daykline API (from akshare source):
#   f52=主力净流入, f53=小单净流入, f54=中单净流入,
#   f55=大单净流入, f56=超大单净流入, f57=主力净流入占比
FFLOW_FIELDS = "f51,f52,f53,f54,f55,f56,f57"


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.0, status_forcelist=[502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _f(v: str) -> float | None:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def build_em_name_map() -> dict[str, str]:
    """Fetch East Money sector list and return {name: code} mapping."""
    name_map: dict[str, str] = {}
    for fs in ("m:90+t:2", "m:90+t:3"):
        try:
            r = _session().get(
                "http://push2.eastmoney.com/api/qt/clist/get",
                params={
                    "pn": 1, "pz": 500, "po": 1, "np": 1,
                    "fltt": 2, "invt": 2, "fid": "f3",
                    "fs": fs,
                    "fields": "f12,f14",
                },
                headers=_EM_HEADERS,
                timeout=10,
            )
            r.raise_for_status()
            diff = r.json().get("data", {}).get("diff", [])
            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                if code and name:
                    name_map[name] = code
        except Exception:
            print(f"Warning: failed to fetch EM sector list for fs={fs}")
    return name_map


def em_fetch_capital_flow(secid: str, start: str, end: str) -> list[dict]:
    """Fetch daily capital flow for a sector from East Money fflow API."""
    try:
        r = _session().get(
            "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": FFLOW_FIELDS,
                "klt": "101",
                "fqt": "0",
                "beg": start,
                "end": end,
                "lmt": "0",
            },
            headers=_EM_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        klines = r.json().get("data", {}).get("klines", [])
        records = []
        for line in klines:
            p = line.split(",")
            if len(p) < 7:
                continue
            records.append({
                "trade_date": p[0],
                "main_net_inflow": _f(p[1]),
                "small_net": _f(p[2]),
                "medium_net": _f(p[3]),
                "large_net": _f(p[4]),
                "super_large_net": _f(p[5]),
                "main_net_inflow_pct": _f(p[6]),
            })
        return records
    except Exception:
        return []


def backfill():
    conn = get_connection()

    # Find distinct sectors that have NULL capital flow data
    sectors = conn.execute(
        """SELECT DISTINCT code, name, sector_type
           FROM sector_snapshot_item
           WHERE main_net_inflow IS NULL
           ORDER BY sector_type, code"""
    ).fetchall()

    if not sectors:
        print("No sectors with missing capital flow data. Nothing to do.")
        conn.close()
        return

    print(f"Found {len(sectors)} sectors with missing capital flow data")

    # Build name→code mapping for non-BK codes (THS 881xxx)
    non_bk = [s for s in sectors if not s["code"].startswith("BK")]
    name_map: dict[str, str] = {}
    if non_bk:
        print(f"Building East Money name→code mapping for {len(non_bk)} non-BK sectors...")
        name_map = build_em_name_map()
        if not name_map:
            print("Warning: EM name map is empty. Non-BK sectors will be skipped.")

    # Build secid lookup: code → secid
    secid_map: dict[str, str] = {}
    matched = 0
    skipped = 0
    for s in sectors:
        code = s["code"]
        if code.startswith("BK"):
            secid_map[code] = f"90.{code}"
            matched += 1
        else:
            em_code = name_map.get(s["name"])
            if em_code:
                secid_map[code] = f"90.{em_code}"
                matched += 1
            else:
                skipped += 1

    print(f"Matched: {matched}, Skipped (no EM code): {skipped}")

    if not secid_map:
        print("No sectors can be queried. Exiting.")
        conn.close()
        return

    # Date range
    start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    total_updated = 0
    total_sectors = len(secid_map)

    for i, (code, secid) in enumerate(secid_map.items()):
        print(f"[{i+1}/{total_sectors}] {code} → {secid} ... ", end="", flush=True)

        records = em_fetch_capital_flow(secid, start, end)
        if not records:
            print("no data")
            time.sleep(2)
            continue

        updated = 0
        for rec in records:
            res = conn.execute(
                """UPDATE sector_snapshot_item
                   SET main_net_inflow=?, main_net_inflow_pct=?,
                       super_large_net=?, large_net=?, medium_net=?, small_net=?
                   WHERE trade_date=? AND code=? AND main_net_inflow IS NULL""",
                (rec["main_net_inflow"], rec["main_net_inflow_pct"],
                 rec["super_large_net"], rec["large_net"],
                 rec["medium_net"], rec["small_net"],
                 rec["trade_date"], code),
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

    conn.close()
    print(f"\nDone! Total rows updated: {total_updated}")


if __name__ == "__main__":
    backfill()
