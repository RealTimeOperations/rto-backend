"""
RTO Attendance Sync — Portal (sw-attendance-logs) -> Supabase (attendance_logs)
✅ Sirf AAJ ki attendance (date filter auto-detect)
✅ Images exclude, baqi sara data
Usage:
  python attendance_sync.py --schema   # pehli dafa: SQL file banaye
  python attendance_sync.py            # daily sync
"""
import os, sys, json, time, requests
from datetime import datetime, timezone
from dotenv import load_dotenv
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(ROOT_DIR, ".env"))
try:
    from .portal_client import login, base_headers, sign_headers, API_URL
except ImportError:
    from portal_client import login, base_headers, sign_headers, API_URL

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY', '')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # method folder (schema sql yahan banti hai)
SLUG = "sw-attendance-logs"

# ============================================================================
# ✅ HEARTBEAT — frontend (Attendance Dashboard) live status ke liye
#    status: running | portal_error | stopped
# ============================================================================
_sb_client = None

def _sb():
    global _sb_client
    if _sb_client is None:
        from supabase import create_client
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb_client

def heartbeat(status, message=None):
    """Frontend ke liye health status likho (system_heartbeat table)"""
    try:
        _sb().table("system_heartbeat").upsert(
            {
                "id": 1,
                "status": status,
                "message": message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="id",
        ).execute()
    except Exception as e:
        print(f"⚠️ Heartbeat update fail: {e}")
MODULE_ID = 81
REQUESTING_URL = "/solid-waste/view/sw-attendance-logs"

BASE_FILTERS = {
    "verify_status": "",
    "division_id": 1,
    "district_id": 2,
    "office_id": 9827,
    "area_id": "",
    "meeting_point_id": "",
}

def is_image_key(k):
    k = k.lower()
    return any(w in k for w in ('picture', 'photo', 'img', 'attachment', 'selfie'))

def safe_key(k):
    return k.replace('.', '_').replace('-', '_')

def fetch_page(token, office_id, designation_id, filters, page=1, size=500):
    url = API_URL + "/autoform/get-item-listing"
    body = json.dumps({
        "slug": SLUG, "id": "0", "module_id": MODULE_ID,
        "page": page, "size": size,
        "search_keyword": "", "sorting": "",
        "plateform": "web", "requesting_url": REQUESTING_URL,
        "user_type": "contractor",
        "displayedColumnsAll": [],
        "filters_data": filters,
    }, separators=(',', ':'))
    h = base_headers()
    h["Referer"] = "https://suthra.punjab.gov.pk" + REQUESTING_URL
    h["Authorization"] = "Bearer " + token
    h["Active-Office-Id"] = str(office_id)
    h["Active-Designation-Id"] = str(designation_id)
    h.update(sign_headers("POST", url, body, token))
    r = requests.post(url, data=body, headers=h, timeout=30)
    r.raise_for_status()
    node = r.json().get("data", {}) or {}
    return node.get("listings", []), node.get("totalInDB", 0)

def detect_date_filter(token, office_id, designation_id, today):
    """Portal wala exact date key auto-detect kare (sirf aaj ka data)"""
    candidates = [
        {"date": today},
        {"attendance_date": today},
        {"date_from": today, "date_to": today},
        {"from_date": today, "to_date": today},
        {"log_date": today},
        {"check_date": today},
    ]
    for cand in candidates:
        filters = dict(BASE_FILTERS)
        filters.update(cand)
        try:
            recs, total = fetch_page(token, office_id, designation_id, filters, page=1, size=5)
        except Exception as e:
            print(f"   ⚠️ {cand} fail: {e}")
            continue
        print(f"   🔎 {cand} → total={total}")
        if 0 < total < 50000:
            print(f"   ✅ Date filter mil gaya: {cand} (total={total})")
            return filters
    return None

# Portal ke display columns -> raw API fields (employees jaisa clean)
FIELD_MAP = {
    "user_id": "user_ids",
    "supervisor": "supervisor_name",
    "date": "date",
    "user_name": "user_name",
    "cnic": "cnic",
    "designation": "emp_designation_str",
    "employee_type": "employee_type",
    "employee_code": "employee_code",
    "district": "district_name",
    "office": "office_name",
    "uc_ward": "area_name",
    "attendance_point": "meeting_point_name",
    "shift": "shift_name",
    "check_type": "checkout_type",
    "date_time": "created_at",
}

def clean_record(rec):
    out = {"id": rec.get("id")}
    for clean_key, raw_key in FIELD_MAP.items():
        v = rec.get(raw_key)
        out[clean_key] = None if v is None else str(v)
    return out

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"🚀 Attendance Sync | {today}")
    print("=" * 60)
    token, office_id, designation_id = login()

    filters = detect_date_filter(token, office_id, designation_id, today)
    if not filters:
        print("❌ Date filter nahi mila — DevTools → get-item-listing → Payload → View source copy kar ke bhejein")
        return 1

    recs, total = fetch_page(token, office_id, designation_id, filters, page=1, size=500)
    if not recs:
        print("❌ Aaj ka koi record nahi mila")
        return 1
    print(f"📥 Page 1... ✅ +{len(recs)} (total={total})")

    # ✅ Schema generate (pehli dafa)
    if "--schema" in sys.argv:
        keys = []
        for r in recs:
            for k in r.keys():
                if not is_image_key(k) and safe_key(k) not in keys:
                    keys.append(safe_key(k))
        cols = ["    id BIGINT PRIMARY KEY"]
        cols += [f'    "{k}" TEXT' for k in keys if k != "id"]
        cols.append("    fetched_at TIMESTAMPTZ DEFAULT NOW()")
        sql = "DROP TABLE IF EXISTS attendance_logs;\nCREATE TABLE attendance_logs (\n" + ",\n".join(cols) + "\n);\n"
        sql += "CREATE INDEX idx_att_date ON attendance_logs(date);\n"
        out = os.path.join(BASE_DIR, "attendance_schema.sql")
        with open(out, "w", encoding="utf-8") as f:
            f.write(sql)
        print(f"✅ {out} ban gayi — Supabase SQL Editor mein run karein, phir normal sync karein")
        return 0

    # ✅ Baqi pages
    all_recs = [clean_record(r) for r in recs]
    pages_needed = min(30, (total + 499) // 500)
    page = 1
    while page < pages_needed:
        page += 1
        more, _ = fetch_page(token, office_id, designation_id, filters, page=page, size=500)
        if not more:
            break
        all_recs += [clean_record(r) for r in more]
        print(f"📥 Page {page}... ✅ +{len(more)}")
        time.sleep(0.5)

    # ✅ Supabase upload (full refresh)
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    # ✅ Sirf PURANI date ka data remove — aaj ka data safe rahe
    sb.table("attendance_logs").delete().neq("date", filters["date"]).execute()
    print("🗑️ Purani date ka data remove — aaj ka data safe...")
    for i in range(0, len(all_recs), 100):
        batch = all_recs[i:i+100]
        sb.table("attendance_logs").upsert(batch, on_conflict="id").execute()
        print(f"☁️ Batch {i//100 + 1} uploaded ({len(batch)})")
    print(f"✅ {len(all_recs)} attendance records Supabase mein upsert")
    return 0

if __name__ == "__main__":
    sys.exit(main())