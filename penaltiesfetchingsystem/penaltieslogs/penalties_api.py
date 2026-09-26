"""
Penalties Fetch Logs API — heartbeat id = 3.
✅ Historical mode REMOVE (koi pause flag / hist table nahi).
✅ Naya stateless endpoint: /penalties/imposed-report — kisi bhi date ki rows
   SIRF response mein return hoti hain (koi DB write nahi, auto-sync affect nahi).
"""
import os
import subprocess
import sys
import time
import hashlib
import requests
from datetime import datetime
from fastapi import APIRouter

penalties_router = APIRouter(prefix="/penalties", tags=["penalties"])

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))
SYS_DIR = os.path.dirname(LOGS_DIR)
BASE_DIR = os.path.dirname(SYS_DIR)
METHOD_DIR = os.path.join(SYS_DIR, "penaltiesfetchingmethod")
LOG_FILE = os.path.join(LOGS_DIR, "penalties_auto.log")
PID_FILE = os.path.join(LOGS_DIR, "penalties.pid")
# ✅ Image disk cache — portal image ek dafa fetch hoti hai, phir local se instant
CACHE_DIR = os.path.join(LOGS_DIR, "imagecache")
os.makedirs(CACHE_DIR, exist_ok=True)

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

@penalties_router.post("/imposed-report")
def penalties_imposed_report(req: dict):
    """✅ STATELESS on-demand fetch: kisi bhi (purani) date ki penalties rows return karo.
    - Koi DB write NAHI, koi pause flag NAHI — auto-sync process bilkul affect nahi hota
    - Data sirf HTTP response mein jata hai (frontend memory mein temporary rakhta hai)
    """
    date_str = str((req or {}).get("date") or "").strip()
    if not date_str:
        return {"ok": False, "message": "Date required"}
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"ok": False, "message": "Invalid date format (YYYY-MM-DD)"}
    if date_str > datetime.now().strftime("%Y-%m-%d"):
        return {"ok": False, "message": "Future date allowed nahi"}
    try:
        from penaltiesfetchingsystem.penaltiesfetchingmethod import penalties_portal as PP
        token, office_id, designation_id = PP.login()
        rows = PP.fetch_penalties_report(token, office_id, designation_id, custom_date=date_str)
        mapped = PP.map_records(rows)
        for m in mapped:
            m.pop("raw", None)   # payload halka rakho
        return {"ok": True, "date": date_str, "count": len(mapped), "rows": mapped}
    except Exception as e:
        return {"ok": False, "message": f"Fetch failed: {e}"}

@penalties_router.get("/attachment-image")
def attachment_image(url: str):
    """✅ Portal image proxy + DISK CACHE — pehli dafa portal se, us ke baad local cache se instant."""
    from fastapi.responses import Response
    u = str(url or "").strip()
    if not u.startswith("http"):
        return Response(content=b"Bad url", status_code=400)
    # ✅ Cache lookup (url ka hash = filename)
    key = hashlib.sha256(u.encode("utf-8")).hexdigest()
    data_path = os.path.join(CACHE_DIR, key + ".bin")
    meta_path = os.path.join(CACHE_DIR, key + ".ctype")
    try:
        if os.path.exists(data_path) and os.path.getsize(data_path) > 0:
            with open(data_path, "rb") as f:
                data = f.read()
            ctype = "image/jpeg"
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    ctype = f.read().strip() or ctype
            except Exception:
                pass
            return Response(content=data, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        pass
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://suthra.punjab.gov.pk/penalty-management/view/contractor-penalties",
        "Origin": "https://suthra.punjab.gov.pk",
    }
    try:
        r = requests.get(u, headers=hdrs, timeout=45, allow_redirects=True)
        if r.status_code in (401, 403):
            from penaltiesfetchingsystem.penaltiesfetchingmethod import penalties_portal as PP
            token, _o, _d = PP.login()
            h2 = dict(hdrs)
            h2["Authorization"] = "Bearer " + token
            r = requests.get(u, headers=h2, timeout=45, allow_redirects=True)
        if r.status_code != 200 or not r.content:
            return Response(content=b"Not found", status_code=502)
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            b = r.content[:8]
            if b[:3] == b"\xff\xd8\xff":
                ctype = "image/jpeg"
            elif b[:4] == b"\x89PNG":
                ctype = "image/png"
            elif b[:3] == b"GIF":
                ctype = "image/gif"
            elif b[:4] == b"RIFF":
                ctype = "image/webp"
            else:
                return Response(content=b"Not an image", status_code=502)
        # ✅ Cache mein save (agli dafa instant)
        try:
            with open(data_path, "wb") as f:
                f.write(r.content)
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(ctype)
        except Exception:
            pass
        return Response(content=r.content, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        return Response(content=b"Fetch failed", status_code=502)