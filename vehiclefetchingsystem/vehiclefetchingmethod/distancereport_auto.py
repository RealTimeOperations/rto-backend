"""
Distance Report Auto Sync — har 15s Tracking World portal se mileage report fetch + Supabase upsert.
Fingerprint: fetched_at exclude kar ke data compare → same data par DB write NAHI.
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta

METHOD_DIR = os.path.dirname(os.path.abspath(__file__))
SYS_DIR    = os.path.dirname(METHOD_DIR)
BACKEND_DIR = os.path.dirname(SYS_DIR)
LOGS_DIR   = os.path.join(SYS_DIR, "vehiclelogs")

LOG_FILE = os.path.join(LOGS_DIR, "distancereport_auto.log")
PID_FILE = os.path.join(LOGS_DIR, "distancereport.pid")
FP_FILE  = os.path.join(LOGS_DIR, ".distancereport_fingerprint")

sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, METHOD_DIR)

if sys.stdout is None or sys.stderr is None:
    class _Null:
        def write(self, s): return len(s)
        def flush(self): pass
    if sys.stdout is None: sys.stdout = _Null()
    if sys.stderr is None: sys.stderr = _Null()

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

from distancereport import fetch_all_distance_report
from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
from supabase import create_client

SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
TABLE_NAME = "vehicle_distance_reports"
CHECK_SECONDS = 15
HEARTBEAT_ID = 5   # 5 = distance report


# ---- Log (REWRITE model + persistent LIFECYCLE) ----
# ✅ File har cycle REWRITE hoti hai — line-by-line grow NAHI karti.
#    Content = [LIFECYCLE: STARTED/STOPPED (max 8)] + [CURRENT cycle ki lines]
#    Start/stop state hamesha visible rehti hai, history file ko bharti nahi.
_CYCLE = []
_LIFECYCLE = []

def log(msg, new_cycle=False, lifecycle=False):
    global _CYCLE
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if lifecycle:
        _LIFECYCLE.append(line)
        if len(_LIFECYCLE) > 8:
            _LIFECYCLE.pop(0)
        _CYCLE = []
    elif new_cycle:
        _CYCLE = [line]
    else:
        _CYCLE.append(line)
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_LIFECYCLE + _CYCLE) + "\n")
    except Exception:
        pass
    print(line, flush=True)


def heartbeat(status, message=""):
    try:
        SB.table("system_heartbeat").upsert({
            "id": HEARTBEAT_ID,
            "status": status,
            "message": message,
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
    try: os.remove(PID_FILE)
    except Exception: pass


def stopped_flag_exists():
    try:
        return os.path.exists(os.path.join(LOGS_DIR, "distancereport.stopped"))
    except Exception:
        return False


# ✅ Fingerprint helpers — order-insensitive + normalized + diff logging
def _fp_rows(mapped):
    rows = []
    for m in mapped:
        r = {k: v for k, v in m.items() if k != "fetched_at"}
        for k, v in list(r.items()):
            if isinstance(v, str):
                r[k] = v.strip()
            elif isinstance(v, float):
                r[k] = round(v, 2)
        rows.append(r)
    rows.sort(key=lambda r: str(r.get("id", "")))
    return rows


def _diff_summary(old_rows, new_rows):
    old_map = {str(r.get("id")): r for r in old_rows}
    new_ids = set()
    changed = []
    for r in new_rows:
        rid = str(r.get("id"))
        new_ids.add(rid)
        o = old_map.get(rid)
        if o is None:
            changed.append(f"{rid}(new)")
        elif o != r:
            keys = [k for k in r if r[k] != o.get(k)]
            changed.append(f"{rid}[{','.join(keys[:3])}]")
    for oid in old_map:
        if oid not in new_ids:
            changed.append(f"{oid}(removed)")
    return changed


def run_cycle():
    t0 = time.time()

    if stopped_flag_exists():
        log("Stopped by admin — skipping cycle", new_cycle=True)
        heartbeat("distancereport_stopped", "Stopped by admin")
        return "stopped"

    meta, report = fetch_all_distance_report(days_back=0)   # ✅ AAJ ki live report
    if not report:
        log("No distance report fetched from portal", new_cycle=True)
        return "no_data"    

    report_date = meta["from_date"]

    mapped = []
    for v in report:
        reg_no = str(v.get("vehicleRegNumber") or "").strip().upper()
        if not reg_no:
            continue
        mapped.append({
            "id": reg_no,
            "unit_id": str(v.get("unitID", "")),
            "vehicle_reg_number": reg_no,
            "veh_type": v.get("vehType", ""),
            "town": v.get("town", ""),
            "mileage": float(v.get("mileage", 0) or 0),
            "ig_on_time": v.get("igONTime", ""),
            "fuel_allocated": float(v.get("fuelAllocated", 0) or 0),
            "report_date": report_date,
            "fetched_at": datetime.now().isoformat(),
        })

    # ✅ Fingerprint = normalized + sorted rows (order / whitespace / float jitter ignore)
    rows = _fp_rows(mapped)
    fp = json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False)
    old = ""
    old_rows = []
    if os.path.exists(FP_FILE):
        try:
            old = open(FP_FILE, encoding="utf-8").read()
            old_rows = json.loads(old) or []
        except Exception:
            old = ""

    if fp == old:
        log(f"No data update - portal data same, DB untouched ({len(mapped)} distance records) ({time.time()-t0:.1f}s)", new_cycle=True)
        return "no_change"

    diff = _diff_summary(old_rows, rows) if old_rows else [f"first sync: {len(rows)} rows"]
    _now = datetime.now().isoformat()
    for m in mapped:
        m["fetched_at"] = _now

    for i in range(0, len(mapped), 100):
        SB.table(TABLE_NAME).upsert(mapped[i:i+100], on_conflict="id").execute()

    with open(FP_FILE, "w", encoding="utf-8") as f:
        f.write(fp)

    zero_mileage = sum(1 for m in mapped if m["mileage"] == 0)
    log(f"Data updated - {len(mapped)} distance records upserted ({zero_mileage} with 0 mileage) | changed:{len(diff)} e.g. {diff[:3]} ({time.time()-t0:.1f}s)", new_cycle=True)
    return "updated"


def main():
    write_pid()
    log("PROCESS STARTED - Distance Report auto sync (check every 15s)", lifecycle=True)
    heartbeat("distancereport_started", "Server Started")

    backoff = 15
    while True:
        if stopped_flag_exists():
            log("PROCESS STOPPED - admin flag detected", lifecycle=True)
            heartbeat("distancereport_stopped", "Stopped from Admin Panel")
            break

        try:
            result = run_cycle()
            if result == "updated":
                heartbeat("distancereport_data_updated", "Data successfully updated")
            elif result == "no_change":
                heartbeat("distancereport_running", "No data change")
            elif result == "stopped":
                break
            else:
                heartbeat("distancereport_running", "No data / idle")
            backoff = 15
        except KeyboardInterrupt:
            log("PROCESS STOPPED - keyboard interrupt", lifecycle=True)
            heartbeat("distancereport_stopped", "Server Stopped")
            break
        except Exception as e:
            log(f"Error: {e} - backoff {min(backoff, 60)}s", new_cycle=True)
            heartbeat("distancereport_error", f"Error: {e}")
            time.sleep(min(backoff, 60))
            backoff = min(backoff * 2, 60)
            continue

        nxt = datetime.fromtimestamp(time.time() + CHECK_SECONDS).strftime("%H:%M:%S")
        log(f"Paused {CHECK_SECONDS}s - next check at {nxt}")
        # ✅ 1s steps mein sleep — stop flag FORAN detect ho (graceful fast stop ~1s)
        for _ in range(CHECK_SECONDS):
            if stopped_flag_exists():
                break
            time.sleep(1)

    remove_pid()


if __name__ == "__main__":
    main()