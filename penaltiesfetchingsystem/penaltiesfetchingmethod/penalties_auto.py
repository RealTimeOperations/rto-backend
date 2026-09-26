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

# ✅ Image disk cache — SAME folder + SAME key scheme jo /attachment-image proxy use karta hai,
#    taake auto-sync ki cached images proxy ko foran mil jayein (eye button = instant)
import hashlib
CACHE_DIR = os.path.join(LOGS_DIR, "imagecache")
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_paths(url):
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, key + ".bin"), os.path.join(CACHE_DIR, key + ".ctype")

def _is_cached(url):
    b, _ = _cache_paths(url)
    try:
        return os.path.exists(b) and os.path.getsize(b) > 0
    except Exception:
        return False

def _sniff_ctype(data, header_ct):
    ct = (header_ct or "").split(";")[0].strip().lower()
    if ct.startswith("image/"):
        return ct
    b = data[:8]
    if b[:3] == b"\xff\xd8\xff": return "image/jpeg"
    if b[:4] == b"\x89PNG": return "image/png"
    if b[:3] == b"GIF": return "image/gif"
    if b[:4] == b"RIFF": return "image/webp"
    return ""

def prefetch_images(urls, token=None, limit=12):
    """✅ Background mein images PARALLEL download kar ke disk cache mein rakho (4 workers)."""
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    todo = []
    for u in urls:
        if len(todo) >= limit:
            break
        if not _is_cached(u):
            todo.append(u)
    if not todo:
        return 0
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": PP.REFERER,
        "Origin": "https://suthra.punjab.gov.pk",
    }
    def _one(u):
        try:
            r = requests.get(u, headers=hdrs, timeout=45, allow_redirects=True)
            if r.status_code in (401, 403) and token:
                h2 = dict(hdrs)
                h2["Authorization"] = "Bearer " + token
                r = requests.get(u, headers=h2, timeout=45, allow_redirects=True)
            if r.status_code != 200 or not r.content:
                return False
            ct = _sniff_ctype(r.content, r.headers.get("Content-Type"))
            if not ct:
                return False
            bb, mm = _cache_paths(u)
            with open(bb, "wb") as f:
                f.write(r.content)
            with open(mm, "w", encoding="utf-8") as f:
                f.write(ct)
            return True
        except Exception:
            return False
    n = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_one, u) for u in todo]
        for f in as_completed(futs):
            if f.result():
                n += 1
    return n
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
    # ✅ Attachments (FMO images): raw mein na hon to portal detail se EK dafa fetch kar ke DB mein store karo
    #    (next date ka data aane par sync-delete + upsert se ye khud rewrite ho jati hain)
    try:
        need = [m for m in mapped if not m.get("attachments")]
        if need:
            have = {}
            try:
                ex = SB.table("penaltiesdata").select("id, attachments").in_("id", [m["id"] for m in need]).execute()
                have = {r["id"]: (r.get("attachments") or []) for r in (ex.data or [])}
            except Exception:
                have = {}
            fetched_cnt = 0
            for m in need:
                if have.get(m["id"]):
                    m["attachments"] = have[m["id"]]
                    continue
                if fetched_cnt >= 10:
                    continue
                num = (m.get("raw") or {}).get("id") or m["id"]
                det = PP.fetch_penalty_detail(token, office_id, designation_id, num)
                m["attachments"] = PP.extract_attachments(det) if det else []
                fetched_cnt += 1
    except Exception as e:
        log(f"Warning: attachments enrichment failed: {e}")
    # ✅ Fingerprint = SIRF asal data (fetched_at exclude) → data same ho to "no_change"
    #    → heartbeat "penalties_running" likhe gi → frontend pill PURANI time par rahe gi
    fp = json.dumps([{k: v for k, v in m.items() if k != "fetched_at"} for m in mapped], sort_keys=True, default=str)
    # ✅ BACKGROUND PRE-CACHE: portal se attachments aate hi images khud cache ho jati hain
    #    (har cycle max 4 nayi images → portal par load bhi nahi parta, user ko pata bhi nahi chalta)
    try:
        pending = []
        for m in mapped:
            atts = m.get("attachments") or (PP.extract_attachments(m.get("raw")) if m.get("raw") else [])
            for u in atts:
                if u not in pending and not _is_cached(u):
                    pending.append(u)
        if pending:
            cnt = prefetch_images(pending, token=token, limit=12)
            if cnt:
                log(f"Image pre-cache: {cnt} images cached ({len(pending)} pending)")
    except Exception as e:
        log(f"Warning: image pre-cache failed: {e}")
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