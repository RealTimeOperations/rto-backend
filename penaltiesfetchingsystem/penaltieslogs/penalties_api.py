"""
Penalties Fetch Logs API — heartbeat id = 3.
Historical mode: PAUSE-FLAG + alag table (penaltiesdata_hist) —
main table (penaltiesdata) kabhi rewrite nahi hoti, is liye baqi devices
par today ka last-updated data safe rehta hai.
"""
import os
import subprocess
import sys
import time
from datetime import datetime
from fastapi import APIRouter

penalties_router = APIRouter(prefix="/penalties", tags=["penalties"])

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))
SYS_DIR = os.path.dirname(LOGS_DIR)
BASE_DIR = os.path.dirname(SYS_DIR)
METHOD_DIR = os.path.join(SYS_DIR, "penaltiesfetchingmethod")
LOG_FILE = os.path.join(LOGS_DIR, "penalties_auto.log")
PID_FILE = os.path.join(LOGS_DIR, "penalties.pid")
PAUSE_FILE = os.path.join(LOGS_DIR, ".penalties_paused")

_SB = None


def _sb():
    global _SB
    if _SB is None:
        from supabase import create_client
        from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
        _SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
    return _SB


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        STILL_ACTIVE = 259
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(h)
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _running_pid():
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if _pid_alive(pid):
            return pid
    except Exception:
        pass
    return None


def _kill_pid(pid: int):
    try:
        if os.name == "nt":
            import ctypes
            PROCESS_TERMINATE = 0x0001
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if h:
                kernel32.TerminateProcess(h, 1)
                kernel32.CloseHandle(h)
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def _heartbeat(status: str, message: str = ""):
    try:
        _sb().table("system_heartbeat").upsert({
            "id": 3, "status": status, "message": message,
            "updated_at": datetime.now().isoformat(),
        }).execute()
    except Exception:
        pass


def _start_auto_process():
    script = os.path.join(METHOD_DIR, "penalties_auto.py")
    if not os.path.exists(script):
        return False
    exe = sys.executable
    if os.name == "nt":
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x08000000
    subprocess.Popen(
        [exe, script],
        cwd=METHOD_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )
    for _ in range(20):
        time.sleep(0.25)
        if _running_pid():
            return True
    return _running_pid() is not None


@penalties_router.get("/status")
def penalties_status():
    pid = _running_pid()
    return {"running": pid is not None, "pid": pid}


@penalties_router.get("/logs")
def penalties_logs():
    lines = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        lines = []
    pid = _running_pid()
    return {"running": pid is not None, "pid": pid, "lines": lines}


@penalties_router.post("/start")
def penalties_start():
    if _running_pid():
        return {"ok": False, "message": "Penalties server already running"}
    if _start_auto_process():
        return {"ok": True, "message": "Penalties server started", "pid": _running_pid()}
    return {"ok": False, "message": "Start failed - check penalties_auto.log"}


@penalties_router.post("/stop")
def penalties_stop():
    pid = _running_pid()
    if not pid:
        return {"ok": False, "message": "Penalties server already stopped"}
    _kill_pid(pid)
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] PROCESS STOPPED - stopped from Admin Panel\n")
    except Exception:
        pass
    _heartbeat("penalties_stopped", "Server Stopped")
    return {"ok": True, "message": "Penalties server stopped"}


@penalties_router.post("/mark-stopped")
def penalties_mark_stopped():
    _heartbeat("penalties_stopped", "Process stopped from stop script")
    return {"ok": True}


@penalties_router.post("/fetch-date")
def penalties_fetch_date(req: dict):
    """Historical date: pause flag + data sirf penaltiesdata_hist mein (main table safe)."""
    date_str = str((req or {}).get("date") or "").strip()
    if not date_str:
        return {"ok": False, "message": "Date required"}
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"ok": False, "message": "Invalid date format (YYYY-MM-DD)"}

    # 1) Pause flag — auto process agla cycle skip kare (process zinda rehta hai)
    try:
        with open(PAUSE_FILE, "w", encoding="utf-8") as f:
            f.write(date_str)
    except Exception as e:
        return {"ok": False, "message": f"Pause flag write failed: {e}"}
    _heartbeat("paused_for_fetch", f"Fetching historical data for {date_str}")

    # 2) Portal se us date ka data → ALAG table mein (baki devices affect nahi hote)
    try:
        from penaltiesfetchingsystem.penaltiesfetchingmethod import penalties_portal as PP
        token, office_id, designation_id = PP.login()
        rows = PP.fetch_penalties_report(token, office_id, designation_id, custom_date=date_str)
        mapped = PP.map_records(rows)
        sb = _sb()
        sb.table("penaltiesdata_hist").delete().neq("id", "").execute()
        for i in range(0, len(mapped), 100):
            sb.table("penaltiesdata_hist").upsert(mapped[i:i + 100], on_conflict="id").execute()
        _heartbeat("date_data_ready", f"Historical data for {date_str} loaded ({len(mapped)} records)")
        return {"ok": True, "message": f"Fetched {len(mapped)} penalties for {date_str}", "count": len(mapped)}
    except Exception as e:
        try:
            os.remove(PAUSE_FILE)
        except Exception:
            pass
        _heartbeat("fetch_date_error", f"Error: {e}")
        return {"ok": False, "message": f"Fetch failed: {e}"}


@penalties_router.post("/reset")
def penalties_reset():
    """Pause flag remove + hist table clear + auto sync resume (today ka data wapis)."""
    try:
        os.remove(PAUSE_FILE)
    except Exception:
        pass
    try:
        _sb().table("penaltiesdata_hist").delete().neq("id", "").execute()
    except Exception:
        pass
    if not _running_pid():
        _start_auto_process()
    _heartbeat("penalties_started", "Server Started (reset)")
    return {"ok": True, "message": "Reset complete - today's data restored, auto sync resumed"}