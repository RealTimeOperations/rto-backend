"""
Suthra Portal Client — verified signature formula (containers project se)
Login -> token -> /autoform/get-item-listing (generic listing API)
"""
import os
import json
import time
import hashlib
import hmac
import requests
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
load_dotenv()

CNIC = os.getenv('CNIC', '6110120068569')
PASSWORD = os.getenv('PASSWORD', 'Bwn@2026')
API_URL = "https://suthra.punjab.gov.pk/suthra-punjab/backend/public/api"
GUARD_KEY = "suthra-web-v1"
GUARD_SECRET = "suthra-web-request-guard-v1"
DEVICE_ID = "6eb7fcd9-23a6-4f4c-9f87-5bbc63d3792c"

# ============================================================================
# SIGNATURE (portal ka exact formula - verified)
# ============================================================================
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
        "X-Signature": hmac_sha256(bearer or GUARD_SECRET, msg),
    }

def base_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://suthra.punjab.gov.pk",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    }

# ============================================================================
# LOGIN
# ============================================================================
def login():
    url = API_URL + "/login"
    body = json.dumps({
        "cnic": CNIC, "password": PASSWORD, "user_type": "HRMIS_USER",
        "device_id": DEVICE_ID, "geo_status": "ok",
        "lat": 31.5497, "lng": 74.3436, "accuracy": 10
    }, separators=(',', ':'))
    
    # Retry logic: 3 attempts with backoff
    for attempt in range(1, 4):
        try:
            h = base_headers()
            h["Referer"] = "https://suthra.punjab.gov.pk/login"
            h.update(sign_headers("POST", url, body, None))
            r = requests.post(url, data=body, headers=h, timeout=60)
            r.raise_for_status()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < 3:
                print(f"⚠️ Attempt {attempt} failed: {type(e).__name__} — retrying in {attempt * 3}s...")
                time.sleep(attempt * 3)
            else:
                raise Exception(f"Login failed after 3 attempts: {e}")
    d = r.json()
    data = d.get("data") or {}
    user = data.get("user") or {}
    token = data.get("token") or d.get("token")
    if not token:
        raise Exception(f"Token nahi mila: {str(d)[:200]}")
    rmd = data.get("roles_menu_data") or {}
    office_id = rmd.get("active_lg") or 9827
    desigs = user.get("all_designations") or data.get("all_designations") or []
    designation_id = next((x.get("designation_id") for x in desigs if x.get("office_id") == office_id), None)
    if not designation_id:
        designation_id = user.get("official_designation_id") or 160578
    print(f"✅ Login OK | office={office_id} | designation={designation_id}")
    return token, office_id, designation_id

# ============================================================================
# GENERIC LISTING (autoform/get-item-listing)
# ============================================================================
def get_item_listing(token, office_id, designation_id, cfg, page=1, size=500):
    url = API_URL + "/autoform/get-item-listing"
    body = json.dumps({
        "slug": cfg["slug"],
        "id": "0",
        "module_id": cfg["module_id"],
        "page": page,
        "size": size,
        "search_keyword": "",
        "sorting": "",
        "plateform": "web",
        "requesting_url": cfg["requesting_url"],
        "user_type": "contractor",
        "displayedColumnsAll": [],
        "filters_data": cfg["filters_data"],
    }, separators=(',', ':'))
    h = base_headers()
    h["Referer"] = "https://suthra.punjab.gov.pk" + cfg["requesting_url"]
    h["Authorization"] = "Bearer " + token
    h["Active-Office-Id"] = str(office_id)
    h["Active-Designation-Id"] = str(designation_id)
    h.update(sign_headers("POST", url, body, token))
    # Retry logic for listing calls
    for attempt in range(1, 4):
        try:
            r = requests.post(url, data=body, headers=h, timeout=60)
            r.raise_for_status()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < 3:
                print(f"⚠️ Listing attempt {attempt} failed: {type(e).__name__} — retrying in {attempt * 2}s...")
                time.sleep(attempt * 2)
            else:
                raise
    r.raise_for_status()
    return r.json()

def extract_records(d):
    node = d
    for _ in range(4):
        if isinstance(node, list): return node
        if isinstance(node, dict):
            node = node.get("data", node.get("rows", node.get("records", node.get("result"))))
        else: break
    return node if isinstance(node, list) else []