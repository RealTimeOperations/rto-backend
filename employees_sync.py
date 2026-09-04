"""
Employees (HR) Sync v2 — Portal -> Supabase
Sirf wahi columns jo portal par display hote hain (23) + id + fetched_at
"""
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client
from portal_client import login, get_item_listing

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY', '')

EMPLOYEES_CONFIG = {
    "slug": "sw-assigned",
    "module_id": 37,
    "requesting_url": "/solid-waste/assign/view/sw-assigned",
    "filters_data": {
        "is_face_register": "",
        "division_id": 1,
        "district_id": 2,
        "office_id": 9827,
        "area_id": "",
    },
}

# Clean column -> portal raw field
FIELD_MAP = {
    "name": "op_first_name",
    "father_name": "op_father_name",
    "employee_code": "op_employee_code",
    "division": "op_division_name",
    "district": "op_district_name",
    "office": "op_officename",
    "designation": "op_designationname",
    "urban_rural": "op_zonename",
    "uc_ward": "op_areaname",
    "attendance_point": "op_meetingpoint_name",
    "shift": "op_shift_name",
    "shift_id": "shift_id",
    "role": "role",
    "employment_mode": "employment_mode",
    "work_type": "assign_shift_type",
    "sanitation_beat": "source_beat_name",
    "is_face_register": "is_face_register",
    "assigned_by": "assiged_by",
}

DATE_FIELDS = {
    "assigned_date": "assiged_date",
    "registered_at": "registered_datetime",
}

def fmt_cnic(v):
    s = str(v if v is not None else "").replace("-", "").strip()
    if len(s) == 13:
        return f"{s[:5]}-{s[5:12]}-{s[12]}"
    return str(v or "")

def to_ts(v):
    s = str(v if v is not None else "").strip()
    return s if s else None

def clean_record(rec):
    out = {"id": rec.get("id")}
    for clean_key, raw_key in FIELD_MAP.items():
        if clean_key == "shift_id":
            out[clean_key] = str(rec.get(raw_key) or "")
        else:
            out[clean_key] = str(rec.get(raw_key) or "")
    out["cnic"] = fmt_cnic(rec.get("op_cnic"))
    try:
        out["is_cnic_verified"] = int(rec.get("is_cnic_verified") or 0)
    except Exception:
        out["is_cnic_verified"] = 0
    for clean_key, raw_key in DATE_FIELDS.items():
        out[clean_key] = to_ts(rec.get(raw_key))
    out["fetched_at"] = datetime.now().isoformat()
    return out

def fetch_all(token, office_id, designation_id, page_size=500):
    out = []
    page = 1
    while page <= 10:
        print(f"   📥 Page {page}...")
        resp = get_item_listing(token, office_id, designation_id, EMPLOYEES_CONFIG, page=page, size=page_size)
        node = resp.get("data", {}) if isinstance(resp, dict) else {}
        recs = node.get("listings", []) if isinstance(node, dict) else []
        total = node.get("totalInDB", 0) if isinstance(node, dict) else 0
        print(f"      ✅ +{len(recs)} (total {total})")
        for r in recs:
            out.append(clean_record(r))
        if len(recs) < page_size:
            break
        page += 1
        time.sleep(1)
    return out

def main():
    print("=" * 60)
    print(f"🚀 Employees Sync (clean columns) | {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    token, office_id, designation_id = login()
    records = fetch_all(token, office_id, designation_id)
    if not records:
        print("❌ No records")
        return
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    for i in range(0, len(records), 100):
        batch = records[i:i+100]
        sb.table("assigned_employees").upsert(batch, on_conflict="id").execute()
        print(f"   ☁️ Batch {i//100 + 1} uploaded ({len(batch)})")
    print(f"✅ {len(records)} employees synced — sirf clean columns!")

if __name__ == "__main__":
    main()