"""
Vehicle Portal Fetcher — Suthra portal se Vehicle/Machinery data (Tehsil Haroonabad).
3 categories — SAME endpoint, different slug/module:
  • Assigned    → slug: sw-assigned-machinary     (module_id: 77)
  • Un-Assigned → slug: sw-un-assigned-machinary  (module_id: 76)
  • In-Active   → slug: sw-in-active-machinary    (module_id: 231)
Response ka `data` field ENCODED hota hai (base64 reversed) → decode kar ke records nikalte hain.
Sirf terminal verification ke liye — abhi koi DB write NAHI.
"""
import os
import sys
import json
import time
import base64
import requests
from datetime import datetime
from collections import deque

# Backend root ko sys.path mein add karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from attendancefetchingsystem.attendancefetchingmethod import portal_client as PC

LISTING_URL = PC.API_URL + "/autoform/get-item-listing"

# ✅ Tehsil Office, Haroonabad ke fixed filters (browser capture se)
DIVISION_ID = 1
DISTRICT_ID = 2
OFFICE_ID = 9827
PAGE_SIZE = 250

# ✅ Teenon categories ki exact portal configuration (Network tab se capture)
CATEGORIES = {
    "assigned": {
        "slug": "sw-assigned-machinary",
        "module_id": 77,
        "requesting_url": "/solid-waste/machinary/custom-view/sw-assigned-machinary",
        "filters": {
            "division_id": DIVISION_ID,
            "district_id": DISTRICT_ID,
            "office_id": OFFICE_ID,
            "vehicle_type": "",
            "owned_by": "",
            "used_for": "",
        },
    },
    "unassigned": {
        "slug": "sw-un-assigned-machinary",
        "module_id": 76,
        "requesting_url": "/solid-waste/machinary/custom-view/sw-un-assigned-machinary",
        "filters": {
            "division_id": DIVISION_ID,
            "district_id": DISTRICT_ID,
            "office_id": OFFICE_ID,
            "vehicle_type": "",
            "owned_by": "",
        },
    },
    "inactive": {
        "slug": "sw-in-active-machinary",
        "module_id": 231,
        "requesting_url": "/solid-waste/machinary/custom-view/sw-in-active-machinary",
        "filters": {
            "division_id": DIVISION_ID,
            "district_id": DISTRICT_ID,
            "office_id": OFFICE_ID,
        },
    },
}

# ✅ Columns jo humein chahiye (displayedColumnsAll)
COLS = [
    {"key": "bulk_action", "column": True, "value": "Select"},
    {"key": "sr_no", "column": True, "value": "Sr#"},
    {"key": "vehicle_id", "column": True, "value": "Vehicle ID"},
    {"key": "assigned_user", "column": True, "value": "Assigned User"},
    {"key": "type_of_vehicle", "column": True, "value": "Type Of Vehicle"},
    {"key": "registration_number", "column": True, "value": "Registration Number"},
    {"key": "owned_by", "column": True, "value": "Owned By"},
    {"key": "used_for", "column": True, "value": "Used For"},
    {"key": "uc_circle", "column": True, "value": "UC/Circle"},
    {"key": "status", "column": True, "value": "Status"},
]


def login():
    """Portal login — attendance wala shared portal_client"""
    return PC.login()


# ================= DECODER (encoded `data` field) =================
def decode_data(s):
    """✅ Portal encoded string bhejta hai: base64(REVERSED json).
    Decode = string reverse karo → base64 decode → JSON parse."""
    s = str(s or "").strip()
    if not s:
        return None
    rev = s[::-1]
    if not rev.endswith("="):
        m = len(rev) % 4
        if m == 2:
            rev += "=="
        elif m == 3:
            rev += "="
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(rev)
            txt = raw.decode("utf-8", errors="replace")
            try:
                return json.loads(txt)
            except Exception:
                return txt
        except Exception:
            continue
    return None


def extract_records(d):
    """Decoded object mein se records list dhoondho (flexible nesting)"""
    pref = ["records", "rows", "items", "listing", "list", "results", "result", "content", "items_list", "data"]
    q = deque([d])
    seen = set()
    while q:
        node = q.popleft()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, list):
            if node and isinstance(node[0], dict):
                return node
            continue
        if isinstance(node, dict):
            for k in pref:
                if k in node and isinstance(node[k], (list, dict)):
                    q.append(node[k])
            for v in node.values():
                if isinstance(v, (list, dict)):
                    q.append(v)
    return []


# ================= FIELD GETTERS (case-insensitive + fallback) =================
def _g(rec, *names):
    for n in names:
        for k in rec.keys():
            if str(k).strip().lower() == n.lower():
                v = rec[k]
                if isinstance(v, dict):
                    for kk in ("first_name", "name", "title", "value"):
                        if kk in v:
                            return str(v[kk]).strip()
                    return ""
                if isinstance(v, list):
                    return ""
                return "" if v is None else str(v).strip()
    return ""


def _gc(rec, *frags):
    """Fallback: key name mein fragment match ho (e.g. 'assign', 'registration')"""
    for k in rec.keys():
        kl = str(k).lower()
        for f in frags:
            if f in kl:
                v = rec[k]
                if isinstance(v, (dict, list)):
                    continue
                return "" if v is None else str(v).strip()
    return ""


def _deep_str(v):
    """✅ Nested dict/list mein se pehla meaningful string nikalo (e.g. areas.name)"""
    if isinstance(v, dict):
        for kk in ("name", "title", "value", "uc_circle", "area_name", "label"):
            if kk in v and not isinstance(v[kk], (dict, list)):
                s = str(v[kk] or "").strip()
                if s:
                    return s
        for vv in v.values():
            s = _deep_str(vv)
            if s:
                return s
        return ""
    if isinstance(v, list):
        for item in v:
            s = _deep_str(item)
            if s:
                return s
        return ""
    return "" if v is None else str(v).strip()


def _uc_circle(v):
    """✅ UC/Circle value nikalo — exact names, nested dicts, aur fragment fallback.
    Numeric ids (area_id waghera) skip hoti hain."""
    # 1) Exact key names
    for n in ("uc_circle", "uc", "circle", "uc_ward", "area_name", "uc_name", "circle_name", "area_title", "chak"):
        for k in v.keys():
            if str(k).strip().lower() == n:
                s = _deep_str(v[k])
                if s and not s.isdigit():
                    return s
    # 2) Fragment match (ids skip)
    for k in v.keys():
        kl = str(k).lower()
        if kl.endswith("_id") or kl == "id":
            continue
        if any(f in kl for f in ("circle", "uc_", "area", "chak")):
            s = _deep_str(v[k])
            if s and not s.isdigit():
                return s
    return ""


# ================= FETCH =================
def _fetch_page(token, office_id, designation_id, category, page):
    cfg = CATEGORIES[category]
    payload = {
        "slug": cfg["slug"],
        "id": "0",
        "page": page,
        "search_keyword": "",
        "displayedColumnsAll": COLS,
        "filters_data": dict(cfg["filters"]),
        "module_id": cfg["module_id"],
        "plateform": "web",
        "requesting_url": cfg["requesting_url"],
        "size": PAGE_SIZE,
        "sorting": "",
        "user_type": "contractor",
    }
    body = json.dumps(payload, separators=(",", ":"))
    h = PC.base_headers()
    h["Referer"] = "https://suthra.punjab.gov.pk" + cfg["requesting_url"]
    h["Authorization"] = "Bearer " + token
    h["Active-Office-Id"] = str(office_id)
    h["Active-Designation-Id"] = str(designation_id)
    h.update(PC.sign_headers("POST", LISTING_URL, body, token))
    r = requests.post(LISTING_URL, data=body, headers=h, timeout=45)
    r.raise_for_status()
    j = r.json()
    data = j.get("data") if isinstance(j, dict) else None
    if isinstance(data, str):
        decoded = decode_data(data)
    else:
        decoded = data
    recs = extract_records(decoded) if decoded is not None else extract_records(j)
    return recs, j


def fetch_category(token, office_id, designation_id, category):
    cfg = CATEGORIES[category]
    print(f"\n📋 Fetching {category.upper()} vehicles... (slug: {cfg['slug']}, module: {cfg['module_id']})")
    out = []
    page = 1
    last_json = None
    while page <= 10:
        try:
            recs, last_json = _fetch_page(token, office_id, designation_id, category, page)
        except Exception as e:
            print(f"❌ Error on page {page}: {e}")
            break
        if page == 1 and not recs:
            # ✅ Debug: raw response ka structure dikhao taake pata chale decode theek hua ya nahi
            print(f"⚠️ Koi record nahi mila. Raw response keys: {list(last_json.keys()) if isinstance(last_json, dict) else type(last_json)}")
            if isinstance(last_json, dict):
                d = last_json.get("data")
                print(f"   data type: {type(d).__name__} | prefix: {str(d)[:80] if d else None}")
            break
        out.extend(recs)
        if len(recs) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.3)
    print(f"✅ {category.upper()}: {len(out)} records fetched")
    if out:
        print(f"   🔑 Raw keys (first record, ALL): {list(out[0].keys())}")
        uc_hits = {
            k: out[0][k]
            for k in out[0].keys()
            if any(f in str(k).lower() for f in ("uc", "circle", "area", "chak"))
            and not isinstance(out[0][k], (dict, list))
        }
        print(f"   🧭 UC/Circle candidate fields: {uc_hits}")
    return out


def fetch_assigned_vehicles(token, office_id, designation_id):
    return fetch_category(token, office_id, designation_id, "assigned")


def fetch_unassigned_vehicles(token, office_id, designation_id):
    return fetch_category(token, office_id, designation_id, "unassigned")


def fetch_inactive_vehicles(token, office_id, designation_id):
    return fetch_category(token, office_id, designation_id, "inactive")


# ================= MAP (sirf required columns) =================
def _map_common(v):
    return {
        "portal_id": _g(v, "id"),
        "type_of_vehicle": _g(v, "type_of_vehicle", "vehicle_type", "typeofvehicle") or _gc(v, "type_of_vehicle", "vehicle_type"),
        "registration_number": _g(v, "registration_number", "reg_number", "registration_no", "registration_id") or _gc(v, "registration"),
        "owned_by": _g(v, "owned_by", "owner") or _gc(v, "owned"),
        "used_for": _g(v, "used_for", "purpose") or _gc(v, "used_for", "used"),
    }


def map_records(assigned, unassigned, inactive):
    all_vehicles = []
    now = datetime.now().isoformat()

    for idx, v in enumerate(assigned, 1):
        row = _map_common(v)
        row.update({
            "category": "assigned",
            "sr_no": idx,
            "assigned_user": _g(v, "assigned_user", "assigned_user_name", "user_name", "assigned_to") or _gc(v, "assign"),
            "uc_circle": _uc_circle(v),
            "status": "Active",
            "fetched_at": now,
        })
        all_vehicles.append(row)

    for idx, v in enumerate(unassigned, 1):
        row = _map_common(v)
        row.update({
            "category": "unassigned",
            "sr_no": idx,
            "assigned_user": None,
            "uc_circle": None,
            "status": _g(v, "status") or _gc(v, "status") or "Active",
            "fetched_at": now,
        })
        all_vehicles.append(row)

    for idx, v in enumerate(inactive, 1):
        row = _map_common(v)
        row.update({
            "category": "inactive",
            "sr_no": idx,
            "assigned_user": None,
            "uc_circle": None,
            "status": _g(v, "status") or _gc(v, "status") or "In-Active",
            "fetched_at": now,
        })
        all_vehicles.append(row)

    return all_vehicles


# ================= TERMINAL PREVIEW =================
def display_data(vehicles):
    print("\n" + "=" * 130)
    print(" VEHICLE DATA PREVIEW (Tehsil Haroonabad)")
    print("=" * 130)
    if not vehicles:
        print("❌ No vehicles found!")
        return

    assigned = [v for v in vehicles if v["category"] == "assigned"]
    unassigned = [v for v in vehicles if v["category"] == "unassigned"]
    inactive = [v for v in vehicles if v["category"] == "inactive"]
    print(f"\n✅ Total: {len(vehicles)}  |  Assigned: {len(assigned)}  |  Un-Assigned: {len(unassigned)}  |  In-Active: {len(inactive)}")

    if assigned:
        print(f"\n{'─' * 130}\n ASSIGNED VEHICLES (first 5)\n{'─' * 130}")
        print(f"{'Sr#':<4} {'Assigned User':<32} {'Type':<24} {'Reg Number':<14} {'Owned By':<12} {'Used For':<24} {'UC/Circle':<28}")
        print("-" * 130)
        for v in assigned[:5]:
            print(f"{v['sr_no']:<4} {v['assigned_user'][:31]:<32} {v['type_of_vehicle'][:23]:<24} {v['registration_number'][:13]:<14} {v['owned_by'][:11]:<12} {v['used_for'][:23]:<24} {v['uc_circle'][:27]:<28}")

    if unassigned:
        print(f"\n{'─' * 130}\n UN-ASSIGNED VEHICLES (first 5)\n{'─' * 130}")
        print(f"{'Sr#':<4} {'Type':<26} {'Reg Number':<16} {'Owned By':<12} {'Used For':<26} {'Status':<10}")
        print("-" * 130)
        for v in unassigned[:5]:
            print(f"{v['sr_no']:<4} {v['type_of_vehicle'][:25]:<26} {v['registration_number'][:15]:<16} {v['owned_by'][:11]:<12} {v['used_for'][:25]:<26} {v['status'][:9]:<10}")

    if inactive:
        print(f"\n{'─' * 130}\n IN-ACTIVE VEHICLES (first 5)\n{'─' * 130}")
        print(f"{'Sr#':<4} {'Type':<26} {'Reg Number':<16} {'Owned By':<12} {'Used For':<26} {'Status':<10}")
        print("-" * 130)
        for v in inactive[:5]:
            print(f"{v['sr_no']:<4} {v['type_of_vehicle'][:25]:<26} {v['registration_number'][:15]:<16} {v['owned_by'][:11]:<12} {v['used_for'][:25]:<26} {v['status'][:9]:<10}")


# ================= MAIN =================
def fetch_all_vehicles():
    print("🚗 VEHICLE MONITORING - DATA FETCH (Tehsil Haroonabad)")
    print("=" * 130)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n🔐 Logging into portal...")
    token, office_id, designation_id = login()
    if not token:
        print("❌ Login failed!")
        return None
    print(f"✅ Login OK | office={office_id} | designation={designation_id}")

    assigned = fetch_assigned_vehicles(token, office_id, designation_id)
    unassigned = fetch_unassigned_vehicles(token, office_id, designation_id)
    inactive = fetch_inactive_vehicles(token, office_id, designation_id)

    all_vehicles = map_records(assigned, unassigned, inactive)
    display_data(all_vehicles)

    print("\n" + "=" * 130)
    print("✅ Data fetch completed!")
    print("=" * 130)
    return all_vehicles


if __name__ == "__main__":
    vehicles = fetch_all_vehicles()
    if vehicles:
        print(f"\n💾 Total records ready for database: {len(vehicles)}")
    else:
        print("\n❌ No data to save!")