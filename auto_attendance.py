"""
RTO Attendance AUTO Sync — continuous terminal loop
✅ Har 10 sec baad portal check
✅ Update nahi → "No data update" log
✅ Update hai → fetch + Supabase upload + date + elapsed time
Run: python auto_attendance.py
"""
import os
import json
import time
import hashlib
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

import attendance_sync as AS
from attendance_sync import BASE_FILTERS, clean_record, fetch_page

PAUSE_SECONDS = 10      # ✅ Har check ke baad pause
ERROR_BACKOFF = 30      # ✅ Error par 30 sec ruke

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FP_FILE = os.path.join(BASE_DIR, ".attendance_fingerprint")

_state = {"token": None, "office_id": None, "designation_id": None}

def log(msg):
    line = "[" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "] " + msg
    print(line, flush=True)

def ensure_login():
    if not _state["token"]:
        token, office_id, designation_id = AS.login()
        _state.update(token=token, office_id=office_id, designation_id=designation_id)

def today_filters():
    f = dict(BASE_FILTERS)
    f["date"] = datetime.now().strftime("%Y-%m-%d")   # ✅ detected date key
    return f

def run_cycle():
    t0 = time.time()
    ensure_login()
    filters = today_filters()

    # ---- 1) Light check: page 1 + total (change detection)
    recs, total = fetch_page(_state["token"], _state["office_id"], _state["designation_id"], filters, page=1, size=500)
    sig = [{"id": r.get("id"), "c": r.get("created_at"), "u": r.get("updated_at")} for r in recs]
    fp = hashlib.md5((str(total) + json.dumps(sig, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()

    last = ""
    if os.path.exists(FP_FILE):
        try:
            last = open(FP_FILE, encoding="utf-8").read().strip()
        except Exception:
            pass

    if fp == last:
        log(f"⏸️ No data update — portal par koi naya record nahi ({time.time() - t0:.1f}s)")
        return "no_change"

    # ---- 2) Full fetch (baqi pages)
    all_recs = [clean_record(r) for r in recs]
    page = 1
    while len(all_recs) < total and page < 30:
        page += 1
        more, _ = fetch_page(_state["token"], _state["office_id"], _state["designation_id"], filters, page=page, size=500)
        if not more:
            break
        all_recs += [clean_record(r) for r in more]
        time.sleep(0.4)

    # ---- 3) Supabase upload (incremental: sirf PURANI date delete, aaj ka data safe)
    from supabase import create_client
    sb = create_client(AS.SUPABASE_URL, AS.SUPABASE_KEY)
    sb.table("attendance_logs").delete().neq("date", filters["date"]).execute()
    for i in range(0, len(all_recs), 100):
        sb.table("attendance_logs").upsert(all_recs[i:i+100], on_conflict="id").execute()

    with open(FP_FILE, "w", encoding="utf-8") as f:
        f.write(fp)

    log(f"✅ Data fetched ({filters['date']}) — {len(all_recs)} records uploaded to Supabase ({time.time() - t0:.1f}s)")
    return "updated"

def main():
    log("=" * 60)
    log("🟢 ATTENDANCE AUTO SYNC START (har 10 sec check)")
    log("=" * 60)
    while True:
        try:
            run_cycle()
            log(f"💤 Pause {PAUSE_SECONDS}s...")
            time.sleep(PAUSE_SECONDS)
        except KeyboardInterrupt:
            log("🛑 User ne band kiya (Ctrl+C)")
            break
        except Exception as e:
            log(f"❌ Error: {e} — re-login + {ERROR_BACKOFF}s backoff")
            _state["token"] = None
            time.sleep(ERROR_BACKOFF)

if __name__ == "__main__":
    main()