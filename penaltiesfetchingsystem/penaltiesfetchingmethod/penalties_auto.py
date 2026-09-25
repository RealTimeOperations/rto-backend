"""
Penalties Auto Sync — har 15s portal se penalties fetch + Supabase upsert.
Log model: REWRITE (sirf current cycle ki lines) — heartbeat id = 3.
"""
import os
import sys
import json
import time
from datetime import datetime

METHOD_DIR = os.path.dirname(os.path.abspath(__file__))
SYS_DIR = os.path.dirname(METHOD_DIR)
BACKEND_DIR = os.path.dirname(SYS_DIR)
LOGS_DIR = os.path.join(SYS_DIR, "penaltieslogs")
LOG_FILE = os.path.join(LOGS_DIR, "penalties_auto.log")
PID_FILE = os.path.join(LOGS_DIR, "penalties.pid")
FP_FILE = os.path.join(LOGS_DIR, ".penalties_fingerprint")

sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, METHOD_DIR)

if sys.stdout is None or sys.stderr is None:
    class _Null:
        def write(self, s): return len(s)
        def flush(self): pass
    if sys.stdout is None: sys.stdout = _Null()
    if sys.stderr is None: sys.stderr = _Null()

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from penaltiesfetchingsystem.penaltiesfetchingmethod import penalties_portal as PP
from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
from supabase import create_client

SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
CHECK_SECONDS = 15
_CYCLE = []

def log(msg, new_cycle=False):
    global _CYCLE
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if new_cycle:
        _CYCLE = [line]
    else:
        _CYCLE.append(line)
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_CYCLE) + "\n")
    except Exception:
        pass
    print(line, flush=True)

def heartbeat(status, message=""):
    try:
        SB.table("system_heartbeat").upsert({
            "id": 3, "status": status, "message": message,
            "updated_at": datetime.now().isoformat(),
        }).execute()
    except Exception:
        pass

def write_pid():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

def remove_pid():
    try:
        os.remove(PID_FILE)
    except Exception:
        pass

def run_cycle():
    t0 = time.time()
    token, office_id, designation_id = PP.login()
    rows = PP.fetch_penalties_report(token, office_id, designation_id)
    mapped = PP.map_records(rows)
    # ✅ Fingerprint = SIRF asal data (fetched_at exclude) → data same ho to "no_change"
    #    → heartbeat "penalties_running" likhe gi → frontend pill PURANI time par rahe gi
    fp = json.dumps([{k: v for k, v in m.items() if k != "fetched_at"} for m in mapped], sort_keys=True, default=str)
    old = ""
    if os.path.exists(FP_FILE):
        try:
            old = open(FP_FILE, encoding="utf-8").read()
        except Exception:
            old = ""
    if fp == old:
        log(f"No data update - No new records on portal ({time.time() - t0:.1f}s)", new_cycle=True)
        return "no_change"
    # ✅ fetched_at SIRF tab refresh karo jab asal data change hua ho
    #    → DB ka time = sacha last-data-update time → frontend pill + notification SAME time
    _now = datetime.now().isoformat()
    for _m in mapped:
        _m["fetched_at"] = _now
    
    # ✅ SYNC-DELETE: portal se ghayab penalties + purani date ka data remove
    today = datetime.now().strftime("%Y-%m-%d")
    fetched_ids = {m["id"] for m in mapped}
    
    if fetched_ids:
        try:
            existing = SB.table("penaltiesdata").select("id, penalty_date").execute()
            rows_now = existing.data or []
            gone = [r["id"] for r in rows_now if r.get("penalty_date") == today and r["id"] not in fetched_ids]
            old_dates = [r["id"] for r in rows_now if r.get("penalty_date") != today]
            remove_ids = gone + old_dates
            
            for i in range(0, len(remove_ids), 500):
                SB.table("penaltiesdata").delete().in_("id", remove_ids[i:i + 500]).execute()
            
            if gone:
                log(f"Sync-delete: {len(gone)} penalties portal par delete/cancel hoin -> DB se remove")
            if old_dates:
                log(f"Cleanup: {len(old_dates)} purani date ki penalties DB se remove")
        except Exception as e:
            log(f"Warning: sync-delete failed: {e}")
    
    for i in range(0, len(mapped), 100):
        SB.table("penaltiesdata").upsert(mapped[i:i + 100], on_conflict="id").execute()
    
    with open(FP_FILE, "w", encoding="utf-8") as f:
        f.write(fp)
    
    new_ct = sum(1 for m in mapped if (m["status"] or "").strip().lower() == "new")
    log(f"Data fetched - {len(mapped)} penalties upserted ({new_ct} new) ({time.time() - t0:.1f}s)", new_cycle=True)
    return "updated"

def main():
    write_pid()
    log(f"PROCESS STARTED - Penalties auto sync (check every {CHECK_SECONDS}s)", new_cycle=True)
    heartbeat("penalties_started", "Server Started")
    
    backoff = 15
    
    while True:
        try:
            result = run_cycle()
            if result == "updated":
                heartbeat("penalties_data_updated", "Data successfully updated")
            else:
                heartbeat("penalties_running")
            backoff = 15
        except KeyboardInterrupt:
            log("PROCESS STOPPED - keyboard interrupt")
            heartbeat("penalties_stopped", "Server Stopped")
            break
        except Exception as e:
            log(f"Error: {e} - re-login + backoff", new_cycle=True)
            heartbeat("penalties_error", "Error: Portal Issue")
            time.sleep(min(backoff, 60))
            backoff = min(backoff * 2, 60)
            continue
        
        nxt = datetime.fromtimestamp(time.time() + CHECK_SECONDS).strftime("%H:%M:%S")
        log(f"Paused {CHECK_SECONDS}s - next check at {nxt}")
        time.sleep(CHECK_SECONDS)
    
    remove_pid()

if __name__ == "__main__":
    main()