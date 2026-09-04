"""
Discovery script v2 - Exact portal payload structure + date filters
Run: python test_listing.py
"""
import json
from datetime import datetime
from portal_client import login, get_item_listing, extract_records

# Portal ka EXACT payload structure (original capture se)
ATTENDANCE = {
    "slug": "sw-attendance-logs",
    "module_id": 81,
    "requesting_url": "/solid-waste/view/sw-attendance-logs",
    "filters_data": {
        "verify_status": "",
        "division_id": 1,
        "district_id": 2,
        "office_id": 9827,
        "area_id": "",
        "meeting_point_id": "",
        "shift_id": "",
        "employee_type": "",
        "designation_id": "",
        "date_from": datetime.now().strftime("%Y-%m-%d"),
        "date_to": datetime.now().strftime("%Y-%m-%d"),
    },
    "displayedColumnsAll": [
        {"key": "sr_no", "column": True, "value": "Sr#"},
        {"key": "employee_name", "column": True, "value": "Employee Name"},
        {"key": "designation", "column": True, "value": "Designation"},
        {"key": "check_in", "column": True, "value": "Check In"},
        {"key": "check_out", "column": True, "value": "Check Out"},
        {"key": "total_hours", "column": True, "value": "Total Hours"},
        {"key": "status", "column": True, "value": "Status"},
    ],
}

ASSIGNED = {
    "slug": "sw-assigned",
    "module_id": 37,
    "requesting_url": "/solid-waste/assign/view/sw-assigned",
    "filters_data": {
        "is_face_register": "",
        "division_id": 1,
        "district_id": 2,
        "office_id": 9827,
        "area_id": "",
        "employee_type": "",
        "designation_id": "",
        "status": "",
    },
    "displayedColumnsAll": [
        {"key": "bulk_action", "column": True, "value": "Select"},
        {"key": "sr_no", "column": True, "value": "Sr#"},
        {"key": "employee_name", "column": True, "value": "Employee Name"},
        {"key": "cnic", "column": True, "value": "CNIC"},
        {"key": "designation", "column": True, "value": "Designation"},
        {"key": "mobile", "column": True, "value": "Mobile"},
        {"key": "status", "column": True, "value": "Status"},
    ],
}

def probe(token, office_id, designation_id, cfg):
    print("=" * 70)
    print(f"🔎 Probing: {cfg['slug']}")
    
    # Enhanced request with displayedColumnsAll
    import requests
    import hashlib
    import hmac
    import time
    from urllib.parse import urlparse, parse_qs
    
    API_URL = "https://suthra.punjab.gov.pk/suthra-punjab/backend/public/api"
    GUARD_KEY = "suthra-web-v1"
    
    def sha256_hex(s): return hashlib.sha256(s.encode()).hexdigest()
    def hmac_sha256(key, msg): return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()
    def random_nonce(): return hashlib.md5((str(time.time()) + str(os.getpid())).encode()).hexdigest()
    def normalized_api_path(url):
        p = urlparse(url).path
        i = p.find("api/")
        return p[i:] if i >= 0 else p
    def canonical_query(url):
        q = urlparse(url).query
        if not q: return ""
        return "&".join(f"{k}={v}" for k, v in sorted(parse_qs(q).items()) for v in v)
    def sign_headers(method, url, body, bearer=None):
        ts = str(int(time.time() * 1000))
        nonce = random_nonce()
        bhash = sha256_hex(body or " ")
        msg = "\n".join(["SUTHRA_WEB_V1", method.upper(), normalized_api_path(url),
                         canonical_query(url), ts, nonce, bhash, GUARD_KEY])
        return {
            "X-Web-Key": GUARD_KEY, "X-Time": ts, "X-Web-Nonce": nonce,
            "X-Body-SHA256": bhash,
            "X-Signature": hmac_sha256(bearer or "suthra-web-request-guard-v1", msg),
        }
    
    import os
    url = API_URL + "/autoform/get-item-listing"
    body = json.dumps({
        "slug": cfg["slug"],
        "id": "0",
        "module_id": cfg["module_id"],
        "page": 1,
        "size": 20,
        "search_keyword": "",
        "sorting": "",
        "plateform": "web",
        "requesting_url": cfg["requesting_url"],
        "user_type": "contractor",
        "displayedColumnsAll": cfg.get("displayedColumnsAll", []),
        "filters_data": cfg["filters_data"],
    }, separators=(',', ':'))
    
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://suthra.punjab.gov.pk",
        "Referer": "https://suthra.punjab.gov.pk" + cfg["requesting_url"],
        "Authorization": "Bearer " + token,
        "Active-Office-Id": str(office_id),
        "Active-Designation-Id": str(designation_id),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    h.update(sign_headers("POST", url, body, token))
    
    r = requests.post(url, data=body, headers=h, timeout=30)
    d = r.json()
    
    # Deep extraction - try multiple paths
    print(f"📦 Response keys: {list(d.keys()) if isinstance(d, dict) else 'not dict'}")
    
    # Try different data paths
    if isinstance(d, dict):
        if "data" in d:
            data_node = d["data"]
            print(f"   data keys: {list(data_node.keys()) if isinstance(data_node, dict) else type(data_node)}")
            
            # Try nested data.data.records or data.data.rows
            if isinstance(data_node, dict):
                print(f"   📊 totalInDB: {data_node.get('totalInDB')}")
                for key in ["listings", "records", "rows", "items", "list", "data"]:
                    if key in data_node and isinstance(data_node[key], list):
                        recs = data_node[key]
                        print(f"✅ Found in data.{key}: {len(recs)} records")
                        if recs:
                            print("🔑 RECORD KEYS:")
                            print(sorted(recs[0].keys()))
                            print("📄 FIRST RECORD:")
                            print(json.dumps(recs[0], ensure_ascii=False, indent=2))
                        return
                # If data is itself a list
                if isinstance(data_node, list) and len(data_node) > 0:
                    print(f"✅ data is list: {len(data_node)} records")
                    print("🔑 RECORD KEYS:")
                    print(sorted(data_node[0].keys()))
                    print("📄 FIRST RECORD:")
                    print(json.dumps(data_node[0], ensure_ascii=False, indent=2))
                    return
            # If data_node is user profile (fallback), print it
            if isinstance(data_node, dict) and "id" in data_node and "cnic" in data_node:
                print("⚠️ Portal returned USER PROFILE (fallback) - listing endpoint rejected request")
                print(f"   User: {data_node.get('first_name')} {data_node.get('last_name')} | CNIC: {data_node.get('cnic')}")
                return
    
    print("⚠️ Could not extract records - raw response:")
    print(json.dumps(d, ensure_ascii=False)[:1500])

if __name__ == "__main__":
    token, office_id, designation_id = login()
    probe(token, office_id, designation_id, ATTENDANCE)
    probe(token, office_id, designation_id, ASSIGNED)