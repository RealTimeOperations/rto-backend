"""
RTO Attendance AUTO Sync — continuous background loop
- Checks the portal every 15 seconds
- The log file is REWRITTEN per cycle (only the latest cycle lines are kept)
- Watchdog: restarts the Sync API server if it is down
Run: python auto_attendance.py   (or hidden via start_background.vbs)
"""
import os
import sys
import json
import time
import hashlib
import subprocess
from datetime import datetime, timedelta

import requests

# ---- Folder layout -----------------------------------------------------------
PKG_DIR = os.path.dirname(os.path.abspath(__file__))         # .../attendancefetchingmethod
SYS_DIR = os.path.dirname(PKG_DIR)                           # .../attendancefetchingsystem
ROOT_DIR = os.path.dirname(SYS_DIR)                          # .../backend
LOGS_DIR = os.path.join(SYS_DIR, "attendancelogs")           # .../attendancelogs

LOG_FILE = os.path.join(LOGS_DIR, "auto_attendance.log")
FP_FILE = os.path.join(LOGS_DIR, ".attendance_fingerprint")
PID_FILE = os.path.join(LOGS_DIR, ".attendance.pid")

# Safety net: if ever run without a console (pythonw), send prints to devnull
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# Imports work both ways: as a package module OR as a direct script
try:
    from . import attendance_sync as AS
    from .attendance_sync import BASE_FILTERS, clean_record, fetch_page, heartbeat
except ImportError:
    import attendance_sync as AS
    from attendance_sync import BASE_FILTERS, clean_record, fetch_page, heartbeat

PAUSE_SECONDS = 15       # pause between checks
ERROR_BACKOFF = 30       # pause after an error (once login succeeded at least once)
STARTUP_BACKOFF = 5      # pause after an error before the first successful login

SERVER_HEALTH_URL = "http://localhost:8000/health"

_state = {"token": None, "office_id": None, "designation_id": None}
_ever_logged = False
_last_server_check = 0.0
_started_sent = False   # "started" heartbeat sirf pehle successful cycle par jata hai

_cycle_lines = []   # lines of the current cycle (old cycles are removed)


def reset_log():
    """Start a new log cycle - previous cycle lines are removed."""
    global _cycle_lines
    _cycle_lines = []


def log(msg, new_cycle=False):
    """Append a line to the current cycle and REWRITE the file with it."""
    global _cycle_lines
    line = "[" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "] " + msg
    print(line, flush=True)
    if new_cycle:
        _cycle_lines = []
    _cycle_lines.append(line)
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_cycle_lines) + "\n")
    except Exception:
        pass


def ensure_login():
    global _ever_logged
    if not _state["token"]:
        token, office_id, designation_id = AS.login()
        _state.update(token=token, office_id=office_id, designation_id=designation_id)
        _ever_logged = True


def ensure_api_server():
    """Watchdog: start the Sync API server (main.py) if it is not responding."""
    global _last_server_check
    now = time.time()
    if now - _last_server_check < 60:
        return
    _last_server_check = now
    try:
        requests.get(SERVER_HEALTH_URL, timeout=3)
    except Exception:
        try:
            subprocess.Popen(
                [sys.executable, os.path.join(ROOT_DIR, "main.py")],
                cwd=ROOT_DIR,
                creationflags=0x08000000,  # CREATE_NO_WINDOW (hidden console)
            )
            log("Sync API server was not running - started it in background")
        except Exception as e:
            log(f"Could not start Sync API server: {e}")


def today_filters():
    f = dict(BASE_FILTERS)
    f["date"] = datetime.now().strftime("%Y-%m-%d")
    return f


def run_cycle():
    t0 = time.time()
    reset_log()          # new cycle - old log lines are removed
    ensure_api_server()
    ensure_login()
    filters = today_filters()

    # ---- 1) Light check: page 1 + total (change detection)
    recs, total = fetch_page(_state["token"], _state["office_id"], _state["designation_id"], filters, page=1, size=500)
    # First successful cycle after process start = "started" event (frontend notification);
    # all later cycles = "running" (alive signal only)
    global _started_sent
    if not _started_sent:
        heartbeat("started", "Server Started")
        _started_sent = True
    else:
        heartbeat("running")
    sig = [{"id": r.get("id"), "c": r.get("created_at"), "u": r.get("updated_at")} for r in recs]
    fp = hashlib.md5((str(total) + json.dumps(sig, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()

    last = ""
    if os.path.exists(FP_FILE):
        try:
            last = open(FP_FILE, encoding="utf-8").read().strip()
        except Exception:
            pass

    if fp == last:
        log(f"No data update - no new records on portal ({time.time() - t0:.1f}s)")
        return "no_change"

    # ---- 2) Full fetch (remaining pages)
    all_recs = [clean_record(r) for r in recs]
    page = 1
    while len(all_recs) < total and page < 30:
        page += 1
        more, _ = fetch_page(_state["token"], _state["office_id"], _state["designation_id"], filters, page=page, size=500)
        if not more:
            break
        all_recs += [clean_record(r) for r in more]
        time.sleep(0.4)

    # ---- 3) Supabase upload (incremental: only OLD dates deleted)
    from supabase import create_client
    sb = create_client(AS.SUPABASE_URL, AS.SUPABASE_KEY)
    sb.table("attendance_logs").delete().neq("date", filters["date"]).execute()
    for i in range(0, len(all_recs), 100):
        sb.table("attendance_logs").upsert(all_recs[i:i+100], on_conflict="id").execute()

    with open(FP_FILE, "w", encoding="utf-8") as f:
        f.write(fp)

    log(f"Data fetched ({filters['date']}) - {len(all_recs)} records uploaded to Supabase ({time.time() - t0:.1f}s)")
    return "updated"


def main():
    # PID file so the API server / admin panel can monitor & stop this process
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    log("PROCESS STARTED - Attendance auto sync (check every 15s)", new_cycle=True)
    while True:
        try:
            run_cycle()
            next_at = datetime.now() + timedelta(seconds=PAUSE_SECONDS)
            log(f"Paused {PAUSE_SECONDS}s - next check at {next_at.strftime('%H:%M:%S')}")
            time.sleep(PAUSE_SECONDS)
        except KeyboardInterrupt:
            log("PROCESS STOPPED - stopped by user (Ctrl+C)", new_cycle=True)
            heartbeat("stopped", "Process stopped by user")
            break
        except Exception as e:
            err_str = str(e).lower()
            # Simplify network, HTTP, and login errors for the frontend notification
            keywords = [
                "timed out", "timeout", "connection", "login failed",
                "500 server error", "internal server error", "502 bad gateway",
                "503 service unavailable", "504 gateway timeout", "404 not found",
                "403 forbidden", "401 unauthorized"
            ]
            if any(kw in err_str for kw in keywords):
                hb_msg = "Error in Data Fetching: Portal Issue"
            else:
                hb_msg = f"Error in Data Fetching: {str(e)[:120]}"
            
            log(f"❌ Error: {e} - re-login + {ERROR_BACKOFF}s backoff")
            heartbeat("portal_error", hb_msg)
            _state["token"] = None
            time.sleep(ERROR_BACKOFF)


if __name__ == "__main__":
    main()