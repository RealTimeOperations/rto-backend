# -*- coding: utf-8 -*-
"""
TMO Score → Supabase sync (single-range storage: purana sab delete, naya store)
"""
import os
import datetime
from supabase import create_client
from . import tmo_portal

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
)
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def current_month_range():
    today = datetime.date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


def sync_range(date_from: str = None, date_to: str = None):
    if not date_from or not date_to:
        date_from, date_to = current_month_range()

    now = datetime.datetime.now().isoformat()
    rows = tmo_portal.fetch_range(date_from, date_to)
    if not rows:
        # ✅ DB bhi khali karo + meta mein requested range rakho —
        #    taake frontend par "No Data" show ho, purana data table mein na rahe
        sb.table("tmoscoredata").delete().neq("report_date", "1900-01-01").execute()
        sb.table("tmoscoremeta").delete().neq("range_from", "1900-01-01").execute()
        sb.table("tmoscoremeta").insert({
            "range_from": date_from,
            "range_to": date_to,
            "rows_count": 0,
            "fetched_at": now,
        }).execute()
        return {"status": "empty", "range": [date_from, date_to], "rows": 0}

    # ✅ SINGLE-RANGE STORAGE: DB ka purana SAB data delete
    sb.table("tmoscoredata").delete().neq("report_date", "1900-01-01").execute()
    sb.table("tmoscoremeta").delete().neq("range_from", "1900-01-01").execute()

    # ✅ Naya data insert (chunks of 100)
    db_rows = [
        {
            "report_date": r["report_date"],
            "sr_no": r["sr_no"],
            "row_data": r["row"],
            "fetched_at": now,
        }
        for r in rows
    ]
    for i in range(0, len(db_rows), 100):
        sb.table("tmoscoredata").insert(db_rows[i:i + 100]).execute()

    sb.table("tmoscoremeta").insert({
        "range_from": date_from,
        "range_to": date_to,
        "rows_count": len(rows),
        "fetched_at": now,
    }).execute()

    return {"status": "updated", "range": [date_from, date_to], "rows": len(rows)}


if __name__ == "__main__":
    import sys
    df = sys.argv[1] if len(sys.argv) > 1 else None
    dt = sys.argv[2] if len(sys.argv) > 2 else None
    print(sync_range(df, dt))