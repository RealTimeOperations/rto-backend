"""
Containers Fetch Logs API — attendance jaisa pattern:
- Log file (containerlogs/containers_auto.log) direct padhi jati hai (koi DB table nahi)
- Start/Stop background process control (PID file se)
"""
import os
import subprocess
import sys
import time
from datetime import datetime

from fastapi import APIRouter

containers_router = APIRouter(prefix="/containers", tags=["containers"])

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))     # .../containerfetchingsystem/containerlogs
SYS_DIR = os.path.dirname(LOGS_DIR)                        # .../containerfetchingsystem
BASE_DIR = os.path.dirname(SYS_DIR)                        # .../backend
METHOD_DIR = os.path.join(SYS_DIR, "containerfetchingmethod")
LOG_FILE = os.path.join(LOGS_DIR, "containers_auto.log")
PID_FILE = os.path.join(LOGS_DIR, "containers.pid")

# ✅ Supabase client LAZY banata hai (import ke waqt crash nahi kare ga)
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


def _heartbeat(status: str, message: str = ""):
    try:
        _sb().table("system_heartbeat").upsert({
            "id": 2,
            "status": status,
            "message": message,
            "updated_at": datetime.now().isoformat(),
        }).execute()
    except Exception:
        pass


@containers_router.get("/status")
def containers_status():
    pid = _running_pid()
    return {"running": pid is not None, "pid": pid}


@containers_router.get("/logs")
def containers_logs():
    """Log file ki lines (file har cycle REWRITE hoti hai — attendance jaisa)"""
    lines = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        lines = []
    pid = _running_pid()
    return {"running": pid is not None, "pid": pid, "lines": lines}


@containers_router.post("/start")
def containers_start():
    if _running_pid():
        return {"ok": False, "message": "Containers server already running"}
    script = os.path.join(METHOD_DIR, "containers_auto.py")
    if not os.path.exists(script):
        return {"ok": False, "message": "containers_auto.py not found"}
    exe = sys.executable
    if os.name == "nt":
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
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
            break
    pid = _running_pid()
    if pid:
        return {"ok": True, "message": "Containers server started", "pid": pid}
    return {"ok": False, "message": "Start failed - check containers_auto.log"}


@containers_router.post("/stop")
def containers_stop():
    pid = _running_pid()
    if not pid:
        return {"ok": False, "message": "Containers server already stopped"}
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
    except Exception as e:
        return {"ok": False, "message": f"Stop failed: {e}"}
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
    _heartbeat("containers_stopped", "Server Stopped")
    return {"ok": True, "message": "Containers server stopped"}


@containers_router.post("/mark-stopped")
def containers_mark_stopped():
    """stop_containers_background.bat ke baad heartbeat foran update"""
    _heartbeat("containers_stopped", "Process stopped from stop script")
    return {"ok": True}