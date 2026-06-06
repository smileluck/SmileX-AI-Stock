"""Backfill AI daily reports for specific dates."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.ai_daily_report import generate_ai_daily_report

dates = ["2025-06-04", "2025-06-05"]

for d in dates:
    print(f"Generating AI daily report for {d} ...")
    try:
        result = generate_ai_daily_report(d)
        print(f"  -> status={result['status']}, id={result['id']}")
    except Exception as e:
        print(f"  -> FAILED: {e}")
