"""
Containers Auto Sync — har 15s portal se container report fetch + Supabase upsert.
Log model: attendance jaisa REWRITE — file mein sirf CURRENT cycle ki lines rehti hain.
"""
import os
import sys
import json
import time
from datetime import datetime

METHOD_DIR = os.path.dirname(os.path.abspath(__file__))
SYS_DIR = os.path.dirname(METHOD_DIR)
BACKEND_DIR = os.path.dirname(SYS_DIR)
LOGS_DIR = os.path.join(SYS_DIR, "containerlogs")
LOG_FILE = os.path.join(LOGS_DIR, "containers_auto.log")
PID_FILE = os.path.join(LOGS_DIR, "containers.pid")
FP_FILE = os.path.join(LOGS_DIR, ".containers_fingerprint")

sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, METHOD_DIR)

# pythonw.exe (background) mein console nahi hota — print crash na kare
if sys.stdout is None or sys.stderr is None:
    class _Null:
        def write(self, s): return len(s)
        def flush(self): pass
    if sys.stdout is None: sys.stdout = _Null()
    if sys.stderr is None: sys.stderr = _Null()

# Redirected stdout (DEVNULL/file) par Windows cp1252 crash se bachao — UTF-8 force
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from containerfetchingsystem.containerfetchingmethod import containers_portal as CP
from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
from supabase import create_client

SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
CHECK_SECONDS = 15

# ---- Log (REWRITE model): har nayi cycle purani lines replace karti hai ----
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
            "id": 2, "status": status, "message": message,
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

# ---- Flexible field reader (portal report keys) ----
def _get(row, *names):
    for n in names:
        for k in row.keys():
            if str(k).strip().lower() == n.lower():
                v = row[k]
                return "" if v is None else str(v).strip()
    return ""

def map_rows(rows):
    out = []
    now = datetime.now().isoformat()
    for r in rows:
        site = _get(r, "Primary Site", "Site", "site")
        if not site:
            continue
        sa = _get(r, "Serviced On App", "serviced_on_app").upper()
        st = _get(r, "Serviced By Tracker", "serviced_by_tracker").upper()
        cs = _get(r, "Container Serviced", "container_serviced").upper()
        if not cs:
            cs = "YES" if (sa == "YES" and st == "YES") else "NO"
        out.append({
            "site": site,
            "container_serviced": cs,
            "serviced_on_app": sa or "NO",
            "serviced_by_tracker": st or "NO",
            "app_vehicle": _get(r, "App Vehicle", "app_vehicle"),
            "app_date_time": _get(r, "App Date/Time", "App DateTime", "app_date_time"),
            "fetched_at": now,
        })
    return out

# ---- Ek cycle: login -> fetch -> compare -> upsert ----
def run_cycle():
    t0 = time.time()
    token, office_id, designation_id = CP.login()
    rows = CP.fetch_container_report(token, office_id, designation_id)
    mapper = getattr(CP, "map_records", None)
    mapped = mapper(rows) if callable(mapper) else map_rows(rows)

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

    for i in range(0, len(mapped), 100):
        SB.table("conatnersportaldata").upsert(mapped[i:i + 100], on_conflict="site").execute()
    with open(FP_FILE, "w", encoding="utf-8") as f:
        f.write(fp)
    serviced = sum(1 for m in mapped if m["container_serviced"] == "YES")
    log(f"Data fetched - {len(mapped)} sites upserted ({serviced} serviced) ({time.time() - t0:.1f}s)", new_cycle=True)
    return "updated"

def main():
    write_pid()
    log("PROCESS STARTED - Containers auto sync (check every 15s)", new_cycle=True)
    heartbeat("containers_started", "Server Started")
    backoff = 15
    while True:
        try:
            result = run_cycle()
            if result == "updated":
                heartbeat("containers_data_updated", "Data successfully updated")
            else:
                heartbeat("containers_running")
            backoff = 15
        except KeyboardInterrupt:
            log("PROCESS STOPPED - keyboard interrupt")
            heartbeat("containers_stopped", "Server Stopped")
            break
        except Exception as e:
            log(f"Error: {e} - re-login + backoff", new_cycle=True)
            heartbeat("containers_error", "Error: Portal Issue")
            time.sleep(min(backoff, 60))
            backoff = min(backoff * 2, 60)
            continue
        nxt = datetime.fromtimestamp(time.time() + CHECK_SECONDS).strftime("%H:%M:%S")
        log(f"Paused {CHECK_SECONDS}s - next check at {nxt}")
        time.sleep(CHECK_SECONDS)
    remove_pid()

if __name__ == "__main__":
    main()