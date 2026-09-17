"""
FastAPI Backend — manual sync endpoints + admin log viewer + process control
"""
import os
import sys
import io
import ctypes
import subprocess
import contextlib
from datetime import datetime

# ---- Folder layout -----------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))                    # .../backend
SYS_DIR = os.path.join(ROOT_DIR, "attendancefetchingsystem")
METHOD_DIR = os.path.join(SYS_DIR, "attendancefetchingmethod")
LOGS_DIR = os.path.join(SYS_DIR, "attendancelogs")

LOG_MAX_BYTES = 200_000
LOG_KEEP_LINES = 400


def _trim_log(path):
    """Rewrite a log file keeping only the latest lines."""
    try:
        if os.path.getsize(path) > LOG_MAX_BYTES:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read().splitlines()
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(data[-LOG_KEEP_LINES:]) + "\n")
    except Exception:
        pass


class _RotatingLog:
    """File-like stream used when running under pythonw (no console)."""
    def __init__(self, path):
        self.path = path
        self._f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, s):
        self._f.write(s)
        try:
            if os.path.getsize(self.path) > LOG_MAX_BYTES:
                self._f.close()
                _trim_log(self.path)
                self._f = open(self.path, "a", encoding="utf-8", buffering=1)
        except Exception:
            pass
        return len(s)

    def flush(self):
        self._f.flush()


# pythonw.exe (background) has no console — print() would crash without this
if sys.stdout is None or sys.stderr is None:
    _log = _RotatingLog(os.path.join(LOGS_DIR, "sync_api.log"))
    sys.stdout = _log
    sys.stderr = _log

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from attendancefetchingsystem.attendancefetchingmethod import attendance_sync, employees_sync

ATT_LOG = os.path.join(LOGS_DIR, "auto_attendance.log")
EMP_LOG = os.path.join(LOGS_DIR, "employees_sync.log")
PID_FILE = os.path.join(LOGS_DIR, ".attendance.pid")
PYTHON_EXE = sys.executable  # hidden-console python (same behavior as terminal)
AUTO_SCRIPT = os.path.join(METHOD_DIR, "auto_attendance.py")

app = FastAPI(title="RTO Attendance & HR Sync API")

# CORS (allow calls from the frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "RTO Attendance & HR Sync API",
        "endpoints": {
            "/sync/attendance": "POST - Fetch attendance logs from portal & sync to Supabase",
            "/sync/employees": "POST - Fetch assigned employees from portal & sync to Supabase",
            "/logs/attendance": "GET - tail of auto_attendance.log",
            "/logs/employees": "GET - tail of employees_sync.log",
            "/logs/employees/clear": "POST - clear the employees sync log",
            "/process/status": "GET - is the auto attendance process running",
            "/process/start": "POST - start the auto attendance process",
            "/process/stop": "POST - stop the auto attendance process",
            "/health": "GET - health check",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "rto-sync"}


@app.post("/sync/attendance")
def sync_attendance():
    """Manual trigger: attendance fetch + Supabase upload"""
    try:
        attendance_sync.main()
        return {"success": True, "message": "Attendance sync completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class _Tee(io.TextIOBase):
    """Copy stdout into multiple streams (console/log + employees log file)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


@app.post("/sync/employees")
def sync_employees():
    """Manual trigger: fetch assigned employees + upload to Supabase.
    Output is also copied to employees_sync.log for the admin log viewer."""
    import json as _json
    from supabase import create_client
    sb = create_client(attendance_sync.SUPABASE_URL, attendance_sync.SUPABASE_KEY)
    before = sb.table("assigned_employees").select("*").order("id", desc=False).execute().data
    emp_file = open(EMP_LOG, "a", encoding="utf-8", buffering=1)
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, emp_file)):
            employees_sync.main()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        emp_file.close()
        _trim_log(EMP_LOG)
    after = sb.table("assigned_employees").select("*").order("id", desc=False).execute().data
    changed = _json.dumps(before, sort_keys=True, default=str) != _json.dumps(after, sort_keys=True, default=str)
    return {"success": True, "status": "updated" if changed else "no_change", "count": len(after)}


# ----------------------------------------------------------------------------
# FETCHING LOGS + PROCESS CONTROL (Admin Panel > Fetching Logs)
# ----------------------------------------------------------------------------
def _tail(path: str, lines: int):
    """Return the last N lines of a log file."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-lines:]


def _read_pid():
    try:
        return int(open(PID_FILE, "r").read().strip())
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    """In-process Win32 liveness check — no subprocess, no console window."""
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


@app.get("/logs/attendance")
def logs_attendance(lines: int = 300):
    """Tail of auto_attendance.log"""
    return {"lines": _tail(ATT_LOG, lines)}


@app.get("/logs/employees")
def logs_employees(lines: int = 300):
    """Tail of employees_sync.log"""
    return {"lines": _tail(EMP_LOG, lines)}


@app.post("/logs/employees/clear")
def logs_employees_clear():
    """Clear the employees sync log file."""
    try:
        with open(EMP_LOG, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass
    return {"success": True}


@app.get("/process/status")
def process_status():
    """Is the auto attendance process running?"""
    pid = _read_pid()
    running = pid is not None and _pid_alive(pid)
    return {"running": running, "pid": pid if running else None}


@app.post("/process/start")
def process_start():
    """Start auto_attendance.py in background (hidden console)."""
    pid = _read_pid()
    if pid and _pid_alive(pid):
        return {"success": True, "status": "already_running", "pid": pid}
    subprocess.Popen(
        [PYTHON_EXE, AUTO_SCRIPT],
        cwd=ROOT_DIR,
        creationflags=0x08000000,  # CREATE_NO_WINDOW (hidden console)
    )
    return {"success": True, "status": "started"}


@app.post("/process/stop")
def process_stop():
    """Stop the auto attendance process + notify the frontend instantly."""
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        return {"success": True, "status": "not_running"}
    PROCESS_TERMINATE = 0x0001
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        kernel32.TerminateProcess(h, 1)
        kernel32.CloseHandle(h)
    try:
        with open(ATT_LOG, "w", encoding="utf-8") as f:   # rewrite: only the latest line is kept
            f.write("[" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "] PROCESS STOPPED - stopped from Admin Panel\n")
    except Exception:
        pass
    try:
        attendance_sync.heartbeat("stopped", "Process stopped from Admin Panel")
    except Exception:
        pass
    return {"success": True, "status": "stopped"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)