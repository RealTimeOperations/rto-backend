"""
Vehicles Sync API — manual trigger endpoint (koi auto-sync / watchdog NAHI).
POST /vehicles/sync  → portal se fetch + Supabase upsert (vehicle_sync.sync_to_supabase)
GET  /vehicles/status → aakhri sync ka result
Log: vehiclelogs/vehicles_sync.log
"""
import os
import sys
import threading
from datetime import datetime
import time
from fastapi import APIRouter

vehicles_router = APIRouter(prefix="/vehicles", tags=["vehicles"])

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))      # .../vehiclefetchingsystem/vehiclelogs
SYS_DIR = os.path.dirname(LOGS_DIR)                        # .../vehiclefetchingsystem
BASE_DIR = os.path.dirname(SYS_DIR)                        # .../backend
METHOD_DIR = os.path.join(SYS_DIR, "vehiclefetchingmethod")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, METHOD_DIR)

LOG_FILE = os.path.join(LOGS_DIR, "vehicles_sync.log")

_SYNC_LOCK = threading.Lock()
_LAST = {"at": None, "ok": None, "message": ""}


def _log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


@vehicles_router.post("/sync")
def vehicles_sync():
    """✅ Manual trigger — frontend ka 'Update Vehicles' button isi ko call karta hai."""
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "Sync already running — please wait"}
    try:
        _log("Sync START (manual trigger)")
        from vehiclefetchingsystem.vehiclefetchingmethod import vehicle_sync
        result = vehicle_sync.sync_to_supabase()
        _LAST["at"] = datetime.now().isoformat()
        _LAST["ok"] = result.get("ok")
        _LAST["message"] = result.get("message", "")
        _log(f"Sync FINISHED: ok={result.get('ok')} total={result.get('total')}")
        return result
    except Exception as e:
        _LAST["at"] = datetime.now().isoformat()
        _LAST["ok"] = False
        _LAST["message"] = str(e)
        _log(f"Sync ERROR: {e}")
        return {"ok": False, "total": 0, "message": f"Sync failed: {e}"}
    finally:
        _SYNC_LOCK.release()


@vehicles_router.get("/status")
def vehicles_status():
    return {"last_sync": _LAST}


# ============================================================
# ✅ AUTO-SYNC CONTROL (Vehicle Status + Distance Report)
# ============================================================
import subprocess
import ctypes

AUTO_STATUS_SCRIPT = os.path.join(METHOD_DIR, "vehiclestatus_auto.py")
AUTO_DISTANCE_SCRIPT = os.path.join(METHOD_DIR, "distancereport_auto.py")

STATUS_LOG = os.path.join(LOGS_DIR, "vehiclestatus_auto.log")
DISTANCE_LOG = os.path.join(LOGS_DIR, "distancereport_auto.log")
STATUS_PID = os.path.join(LOGS_DIR, "vehiclestatus.pid")
DISTANCE_PID = os.path.join(LOGS_DIR, "distancereport.pid")


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
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


def _read_pid(path):
    try:
        pid = int(open(path, "r").read().strip())
        return pid if _pid_alive(pid) else None
    except Exception:
        return None


def _terminate_pid(pid: int):
    if os.name == "nt":
        PROCESS_TERMINATE = 0x0001
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            kernel32.TerminateProcess(h, 1)
            kernel32.CloseHandle(h)
            return True
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            pass
    return False


def _spawn_auto(script_path: str):
    exe = sys.executable
    if os.name == "nt":
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
    subprocess.Popen(
        [exe, script_path],
        cwd=METHOD_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=0x00000008 | 0x08000000 if os.name == "nt" else 0,
    )


# ---- Vehicle Status Auto endpoints ----
@vehicles_router.get("/auto/status")
def vehicle_status_auto_status():
    pid = _read_pid(STATUS_PID)
    return {"running": pid is not None, "pid": pid}


@vehicles_router.get("/auto/status/logs")
def vehicle_status_auto_logs():
    lines = []
    try:
        with open(STATUS_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        lines = []
    pid = _read_pid(STATUS_PID)
    return {"running": pid is not None, "pid": pid, "lines": lines}


@vehicles_router.post("/auto/status/start")
def vehicle_status_auto_start():
    try: os.remove(os.path.join(LOGS_DIR, "vehiclestatus.stopped"))
    except Exception: pass
    if _read_pid(STATUS_PID):
        return {"ok": False, "message": "Vehicle Status auto already running"}
    if not os.path.exists(AUTO_STATUS_SCRIPT):
        return {"ok": False, "message": "vehiclestatus_auto.py not found"}
    _spawn_auto(AUTO_STATUS_SCRIPT)
    for _ in range(20):
        time.sleep(0.25)
        if _read_pid(STATUS_PID):
            break
    pid = _read_pid(STATUS_PID)
    if pid:
        return {"ok": True, "message": "Vehicle Status auto started", "pid": pid}
    return {"ok": False, "message": "Start failed — check vehiclestatus_auto.log"}


@vehicles_router.post("/auto/status/stop")
def vehicle_status_auto_stop():
    pid = _read_pid(STATUS_PID)
    if not pid:
        return {"ok": False, "message": "Vehicle Status auto not running"}
    _terminate_pid(pid)
    try: os.remove(STATUS_PID)
    except Exception: pass
    try:
        with open(os.path.join(LOGS_DIR, "vehiclestatus.stopped"), "w") as f:
            f.write("stopped")
    except Exception: pass
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(STATUS_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] PROCESS STOPPED - stopped from Admin Panel\n")
    except Exception: pass
    return {"ok": True, "message": "Vehicle Status auto stopped"}


# ---- Distance Report Auto endpoints ----
@vehicles_router.get("/auto/distance")
def vehicle_distance_auto_status():
    pid = _read_pid(DISTANCE_PID)
    return {"running": pid is not None, "pid": pid}


@vehicles_router.get("/auto/distance/logs")
def vehicle_distance_auto_logs():
    lines = []
    try:
        with open(DISTANCE_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        lines = []
    pid = _read_pid(DISTANCE_PID)
    return {"running": pid is not None, "pid": pid, "lines": lines}


@vehicles_router.post("/auto/distance/start")
def vehicle_distance_auto_start():
    try: os.remove(os.path.join(LOGS_DIR, "distancereport.stopped"))
    except Exception: pass
    if _read_pid(DISTANCE_PID):
        return {"ok": False, "message": "Distance Report auto already running"}
    if not os.path.exists(AUTO_DISTANCE_SCRIPT):
        return {"ok": False, "message": "distancereport_auto.py not found"}
    _spawn_auto(AUTO_DISTANCE_SCRIPT)
    for _ in range(20):
        time.sleep(0.25)
        if _read_pid(DISTANCE_PID):
            break
    pid = _read_pid(DISTANCE_PID)
    if pid:
        return {"ok": True, "message": "Distance Report auto started", "pid": pid}
    return {"ok": False, "message": "Start failed — check distancereport_auto.log"}


@vehicles_router.post("/auto/distance/stop")
def vehicle_distance_auto_stop():
    pid = _read_pid(DISTANCE_PID)
    if not pid:
        return {"ok": False, "message": "Distance Report auto not running"}
    _terminate_pid(pid)
    try: os.remove(DISTANCE_PID)
    except Exception: pass
    try:
        with open(os.path.join(LOGS_DIR, "distancereport.stopped"), "w") as f:
            f.write("stopped")
    except Exception: pass
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(DISTANCE_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] PROCESS STOPPED - stopped from Admin Panel\n")
    except Exception: pass
    return {"ok": True, "message": "Distance Report auto stopped"}


# ---- Combined control (start/stop both) ----
@vehicles_router.post("/auto/start-all")
def vehicles_auto_start_all():
    r1 = vehicle_status_auto_start()
    r2 = vehicle_distance_auto_start()
    return {"status": r1, "distance": r2}


@vehicles_router.post("/auto/stop-all")
def vehicles_auto_stop_all():
    r1 = vehicle_status_auto_stop()
    r2 = vehicle_distance_auto_stop()
    return {"status": r1, "distance": r2}


@vehicles_router.get("/auto/status-all")
def vehicles_auto_status_all():
    return {
        "status": vehicle_status_auto_status(),
        "distance": vehicle_distance_auto_status(),
    }