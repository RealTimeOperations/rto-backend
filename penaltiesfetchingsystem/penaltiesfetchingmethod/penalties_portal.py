"""
Penalties Portal Fetcher — Suthra portal se contractor-penalties listing.
Sirf TEHSIL HAROONABAD (tehsil_id=4) + sirf CURRENT DATE ki penalties.
✅ Added custom_date support for on-demand historical fetch.
"""
import os
import sys
import json
import time
import requests
from collections import deque
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from attendancefetchingsystem.attendancefetchingmethod import portal_client as PC

LISTING_URL = PC.API_URL + "/autoform/get-item-listing"
REFERER = "https://suthra.punjab.gov.pk/penalty-management/view/contractor-penalties"
TEHSIL_HAROONABAD = 4

COLS = [
    {"key": "sr_no", "column": True, "value": "Sr#"},
    {"key": "unique_id", "column": True, "value": "Penalty ID"},
    {"key": "division", "column": True, "value": "Division"},
    {"key": "district", "column": True, "value": "District"},
    {"key": "tehsil", "column": True, "value": "Tehsil"},
    {"key": "office", "column": True, "value": "Office"},
    {"key": "penalty_type", "column": True, "value": "Penalty Type"},
    {"key": "penalty_sub_type", "column": True, "value": "Penalty Sub Type"},
    {"key": "penalty_amount", "column": True, "value": "Penalty Amount (Rs.)"},
    {"key": "penalty_date", "column": True, "value": "Penalty Date"},
    {"key": "status", "column": True, "value": "Status"},
    {"key": "penalty_imposed", "column": True, "value": "Penalty Imposed"},
    {"key": "contractor", "column": True, "value": "Contractor"},
    {"key": "tat", "column": True, "value": "Tat"},
    {"key": "added_by", "column": True, "value": "Added By"},
    {"key": "lat_long", "column": True, "value": "Lat Long"},
    {"key": "created_date_time", "column": True, "value": "Created Date &Time"},
    {"key": "uc", "column": True, "value": "UC"},
    {"key": "remarks", "column": True, "value": "Remarks"},
    {"key": "in_grevience", "column": True, "value": "In Grevience"},
    {"key": "grevience_decisions", "column": True, "value": "Grevience Decisions"},
    {"key": "final_action_time", "column": True, "value": "Final Action Time"},
    {"key": "can_auto_imposed", "column": True, "value": "Can Auto Imposed"},
    {"key": "grevience_remarks", "column": True, "value": "Grevience Remarks"},
    {"key": "action", "column": True, "value": "Action"},
]

def login():
    return PC.login()

def extract_records(d):
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
# ================= Attachments (FMO images) =================
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

def _norm_url(u):
    u = str(u or "").strip().strip('"')
    if not u or len(u) > 600:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("//"):
        return "https:" + u
    return "https://suthra.punjab.gov.pk/" + u.lstrip("/")

def _looks_like_image(s):
    s = str(s or "").lower()
    return s.endswith(_IMAGE_EXT) or ("image" in s) or ("attach" in s) or ("storage" in s) or ("upload" in s)

def _collect_urls(v, out, bucket="other"):
    if isinstance(v, str):
        # ✅ Comma-joined strings bhi handle karo (portal "url1,/path2" format bhejta hai)
        for piece in str(v).split(','):
            piece = piece.strip()
            if piece and _looks_like_image(piece):
                u = _norm_url(piece)
                if u:
                    out.append((bucket, u))
    elif isinstance(v, dict):
        b = bucket
        for k in ("type", "category", "kind", "title", "label"):
            val = v.get(k)
            if isinstance(val, str):
                vl = val.lower()
                if "before" in vl or "prior" in vl:
                    b = "before"; break
                if "after" in vl or "later" in vl:
                    b = "after"; break
        hit = None
        for k in ("url", "file_url", "path", "file_path", "src", "link", "file", "name", "original_name", "title"):
            val = v.get(k)
            if isinstance(val, str) and _looks_like_image(val):
                hit = _norm_url(val)
                break
        if hit:
            out.append((b, hit))
        else:
            for vv in v.values():
                _collect_urls(vv, out, b)
    elif isinstance(v, list):
        for item in v:
            _collect_urls(item, out, bucket)

def _extract_attachments(node, out, depth=0, bucket="other"):
    if depth > 7 or node is None:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            kl = str(k).lower()
            if any(t in kl for t in ("attach", "image", "photo", "media", "document", "file")):
                _collect_urls(v, out, bucket)
            elif "before" in kl or "prior" in kl:
                _extract_attachments(v, out, depth + 1, "before")
            elif "after" in kl or "later" in kl:
                _extract_attachments(v, out, depth + 1, "after")
            else:
                _extract_attachments(v, out, depth + 1, bucket)
    elif isinstance(node, list):
        for item in node:
            _extract_attachments(item, out, depth + 1, bucket)
    return out

_ATTACH_HINTS = ("attach", "image", "photo", "media", "document", "file")
_META_HINTS = ("status", "created", "date", "time", "remark", "action", "actor", "user", "log", "assigned", "contractor", "officer", "resolved")

def _has_attach_key(d):
    return any(any(t in str(k).lower() for t in _ATTACH_HINTS) for k in d.keys())

def _has_meta_key(d):
    return any(any(t in str(k).lower() for t in _META_HINTS) for k in d.keys())

def _collect_flat(v, out):
    pairs = []
    _collect_urls(v, pairs, "other")
    for _b, u in pairs:
        if u not in out:
            out.append(u)

def _log_seq(lg):
    for k in ("sr_no", "sr", "no", "serial", "index"):
        try:
            return int(str(lg.get(k)).strip())
        except Exception:
            continue
    return None

def _log_time(lg):
    import re
    months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    for k, v in lg.items():
        if not isinstance(v, str):
            continue
        kl = str(k).lower()
        if not any(t in kl for t in ("created", "date", "time")):
            continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", v)
        if m:
            return tuple(int(x) for x in m.groups())
        m2 = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)", v)
        if m2:
            hh = int(m2.group(4)) % 12 + (0 if m2.group(7) == "AM" else 12)
            return (int(m2.group(3)), months.get(m2.group(1), 0), int(m2.group(2)), hh, int(m2.group(5)), int(m2.group(6)))
    return None

def _parse_dt(v):
    import re
    if not isinstance(v, str):
        return None
    s = v.strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", s)
    if m:
        try:
            return datetime(*[int(x) for x in m.groups()])
        except Exception:
            return None
    m2 = re.search(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)", s)
    if m2:
        months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
        hh = int(m2.group(4)) % 12 + (0 if m2.group(7) == "AM" else 12)
        try:
            return datetime(int(m2.group(3)), months.get(m2.group(1), 1), int(m2.group(2)), hh, int(m2.group(5)), int(m2.group(6)))
        except Exception:
            return None
    return None

def _log_dt(lg):
    d = _log_time(lg)
    if d:
        return d
    # ✅ Fallback: entry mein kahin bhi date-string ho (key name jo bhi ho)
    for v in lg.values():
        if isinstance(v, str) and len(v) < 45 and ("," in v or ":" in v or "-" in v):
            d = _parse_dt(v)
            if d:
                return d
    return None

def _find_base_dt(node, depth=0):
    """✅ Penalty ka created_at dhoondo (base time — before/after faisla isi se hoga)."""
    if depth > 3 or not isinstance(node, dict):
        return None
    for k in ("created_at", "created_date_time", "created", "penalty_created"):
        d = _parse_dt(node.get(k))
        if d:
            return d
    for v in node.values():
        if isinstance(v, dict):
            d = _find_base_dt(v, depth + 1)
            if d:
                return d
    return None

def _find_logs(node, depth=0):
    """✅ PENALTY LOGS jaisi list dhoondo (entries mein attachments + status/date hon)."""
    if depth > 6 or node is None:
        return None
    if isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node) and any(_has_attach_key(x) for x in node) and any(_has_meta_key(x) for x in node):
            return node
        for item in node:
            r = _find_logs(item, depth + 1)
            if r:
                return r
    elif isinstance(node, dict):
        vals = [v for v in node.values() if isinstance(v, dict)]
        if vals and len(vals) == len(node) and any(_has_attach_key(v) for v in vals):
            return vals
        for k in ("penalty_logs", "logs", "log", "history", "activities", "timeline", "records", "items"):
            if k in node:
                r = _find_logs(node[k], depth + 1)
                if r:
                    return r
        for v in node.values():
            if isinstance(v, (dict, list)):
                r = _find_logs(v, depth + 1)
                if r:
                    return r
    return None

def _url_epoch(u):
    """✅ Portal filename mein upload epoch embedded hota hai:
       .../264612-801790389424.jpg → last 10 digits = 1790389424 (upload time)"""
    import re
    m = re.search(r"/[A-Za-z0-9_]+-(\d{11,14})\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?|$)", u.lower())
    if not m:
        return None
    ep = int(m.group(1)[-10:])
    if 1_600_000_000 <= ep <= 2_200_000_000:
        return ep
    return None

def extract_attachments_grouped(node):
    """✅ BEFORE/AFTER = filename upload-epoch vs penalty created_at (koi detail call NAHI):
       - upload created_at ke ~5 min andar = BEFORE (FMO images) → UPER
       - us ke baad = AFTER (hamare account ki images) → NEECHAY
       - epoch/base na mile tab logs / key-name fallback"""
    groups = {"before": [], "after": [], "other": []}
    pairs = _extract_attachments(node, [], 0, "other")
    seen = set()
    uniq = []
    for b, u in pairs:
        if u not in seen:
            seen.add(u)
            uniq.append((b, u))
    base = _find_base_dt(node)
    epochs = [(_url_epoch(u), b, u) for b, u in uniq]
    if base and any(e[0] for e in epochs):
        PKT = timedelta(hours=5)
        for ep, b, u in epochs:
            if ep:
                up_local = datetime.utcfromtimestamp(ep) + PKT   # upload wall-clock (PKT)
                delta = (up_local - base).total_seconds()
                bucket = "before" if -3600 <= delta <= 300 else "after"
            else:
                bucket = b if b in ("before", "after") else "other"
            groups[bucket].append(u)
        for k in ("before", "after"):
            groups[k].sort(key=lambda u: _url_epoch(u) or 0)   # ✅ chronological order
        return groups
    # ---- Fallback: PENALTY LOGS order/time ----
    logs = _find_logs(node)
    if logs:
        entries = []
        for lg in logs:
            urls = []
            _collect_flat(lg, urls)
            if urls:
                entries.append((_log_dt(lg), _log_seq(lg), urls))
        if entries and all(e[1] is not None for e in entries):
            entries.sort(key=lambda e: e[1])
        elif entries and all(e[0] is not None for e in entries):
            entries.sort(key=lambda e: e[0])
        seen2 = set()
        for i, (t, sq, urls) in enumerate(entries):
            b = "before" if (base and t and (t - base).total_seconds() <= 300) else ("before" if i == 0 else "after")
            for u in urls:
                if u in seen2:
                    continue
                seen2.add(u)
                groups[b].append(u)
        for b, u in uniq:
            if u not in seen2:
                groups.setdefault(b, []).append(u)
        return groups
    # ---- Fallback: key-name buckets / original order ----
    for b, u in uniq:
        groups.setdefault(b, []).append(u)
    return groups
def extract_attachments(node):
    g = extract_attachments_grouped(node)
    return g["before"] + g["after"] + g["other"]

def att_urls(att):
    """✅ DB value (grouped object YA legacy flat list) se flat URL list."""
    if isinstance(att, dict):
        out = []
        for k in ("before", "after", "other"):
            out.extend([u for u in (att.get(k) or []) if isinstance(u, str)])
        return out
    if isinstance(att, list):
        return [u for u in att if isinstance(u, str)]
    return []

DETAIL_PATHS = [
    "/autoform/get-item-detail",
    "/autoform/get-item",
    "/autoform/get-detail",
    "/penalty-management/get-penalty-detail",
    "/penalty-management/get-penalty",
]

def fetch_penalty_detail(token, office_id, designation_id, penalty_id):
    """Portal se single penalty detail (attachments ke liye) — auto-sync mein EK dafa call hoti hai."""
    for path in DETAIL_PATHS:
        url = PC.API_URL + path
        for payload in (
            {"slug": "contractor-penalties", "id": str(penalty_id), "module_id": 145},
            {"slug": "contractor-penalties", "id": str(penalty_id)},
            {"id": str(penalty_id)},
        ):
            body = json.dumps(payload, separators=(",", ":"))
            h = PC.base_headers()
            h["Referer"] = "https://suthra.punjab.gov.pk/penalty-management/view-penalty/" + str(penalty_id)
            h["Authorization"] = "Bearer " + token
            h["Active-Office-Id"] = str(office_id)
            h["Active-Designation-Id"] = str(designation_id)
            h.update(PC.sign_headers("POST", url, body, token))
            try:
                r = requests.post(url, data=body, headers=h, timeout=30)
                if r.status_code != 200:
                    continue
                d = r.json()
                if isinstance(d, (dict, list)) and _extract_attachments(d, [], 0):
                    return d
            except Exception:
                continue
    return None

# ✅ custom_date added
def _payload(page, with_date, custom_date=None):
    target_date = custom_date if custom_date else datetime.now().strftime("%Y-%m-%d")
    filters = {
        "division_id": 1,
        "district_id": 2,
        "tehsil_id": TEHSIL_HAROONABAD,
        "penalty_type_id": "",
        "status": "",
    }
    if with_date:
        filters["penalty_date"] = [target_date, target_date]
    return {
        "slug": "contractor-penalties",
        "id": "0",
        "page": page,
        "search_keyword": "",
        "displayedColumnsAll": COLS,
        "filters_data": filters,
        "module_id": 145,
        "plateform": "web",
        "requesting_url": "/penalty-management/view/contractor-penalties",
        "size": 250,
        "sorting": "",
        "user_type": "contractor",
    }

LAST_RAW = {"text": ""}

# ✅ custom_date added
def _fetch_page(token, office_id, designation_id, page, with_date, custom_date=None):
    body = json.dumps(_payload(page, with_date, custom_date), separators=(",", ":"))
    h = PC.base_headers()
    h["Referer"] = REFERER
    h["Authorization"] = "Bearer " + token
    h["Active-Office-Id"] = str(office_id)
    h["Active-Designation-Id"] = str(designation_id)
    h.update(PC.sign_headers("POST", LISTING_URL, body, token))
    r = requests.post(LISTING_URL, data=body, headers=h, timeout=30)
    r.raise_for_status()
    LAST_RAW["text"] = r.text
    return extract_records(r.json())

# ✅ target_date support added
def _is_target_date(rec, target_date=None):
    v = ""
    for k in rec.keys():
        kl = str(k).strip().lower()
        if kl in ("penalty_date", "date", "created_date", "penalty_datetime"):
            v = str(rec[k] or "")
            break
    if not v:
        return True
    
    # ✅ Agar target_date diya gaya hai to usay use karo, warna aaj ka din
    check_date = datetime.strptime(target_date, "%Y-%m-%d") if target_date else datetime.now()
    
    vv = v.strip()
    cands = [
        check_date.strftime("%Y-%m-%d"),
        check_date.strftime("%b %d, %Y"),
        check_date.strftime("%d-%b-%Y"),
        check_date.strftime("%b %d %Y"),
        check_date.strftime("%d/%m/%Y"),
    ]
    for c in cands:
        if vv.startswith(c) or c in vv:
            return True
    return False

# ✅ custom_date added
def fetch_penalties_report(token, office_id, designation_id, custom_date=None):
    out = []
    used_date = None
    
    for with_date in (True, False):
        out = []
        page = 1
        try:
            while page <= 10:
                recs = _fetch_page(token, office_id, designation_id, page, with_date, custom_date)
                if page == 1 and not recs:
                    break
                out.extend(recs)
                if len(recs) < 250:
                    break
                page += 1
                time.sleep(0.3)
        except Exception:
            out = []
        if out:
            used_date = with_date
            break
    
    if not out:
        print("RAW RESPONSE (first 1500 chars):", LAST_RAW["text"][:1500])
        return []
    
    total = len(out)
    # ✅ Filter karte waqt custom_date pass karo
    out = [r for r in out if _is_target_date(r, custom_date)]
    date_label = custom_date if custom_date else "today"
    print(f"Fetched {total} penalties (date_filter={used_date}) -> {date_label}: {len(out)} (Tehsil Haroonabad)")
    return out

def _g(rec, *names):
    for n in names:
        for k in rec.keys():
            if str(k).strip().lower() == n.lower():
                v = rec[k]
                return "" if v is None else str(v).strip()
    return ""

def _num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0

def map_records(recs):
    out = []
    now = datetime.now().isoformat()
    for rec in recs:
        uid = _g(rec, "unique_id") or str(_g(rec, "id"))
        
        coords = _g(rec, "coordinates")
        lat = lon = 0.0
        if coords and "," in coords:
            parts = coords.split(",")
            try:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
            except Exception:
                lat = lon = 0.0
        
        grev_remarks = _g(rec, "grevience_remarks")
        grev_time = _g(rec, "grevience_date_time")
        in_grev = "Yes" if (grev_remarks or grev_time) else "No"
        
        out.append({
            "id": uid,
            "sr_no": _g(rec, "sr_no"),
            "penalty_type": _g(rec, "penalty_types.penalty_type_id.title", "penalty_type"),
            "penalty_sub_type": _g(rec, "penalty_types.penalty_sub_type_id.title", "penalty_sub_type"),
            "penalty_amount": _num(_g(rec, "penalty_amount")),
            "penalty_date": _g(rec, "penalty_date"),
            "status": _g(rec, "status"),
            "penalty_imposed": _g(rec, "penalty_imposed", "imposed", "fine_imposed"),
            "tm_imposed": _g(rec, "final_penalty_imposed"),
            "contractor": _g(rec, "users.contractor_user_id.first_name", "contractor"),
            "tat": _g(rec, "tat"),
            "added_by": _g(rec, "users.user_id.first_name", "added_by"),
            "division_name": _g(rec, "divisions.division_id.name"),
            "district_name": _g(rec, "districts.district_id.name"),
            "tehsil_name": _g(rec, "tehsils.tehsil_id.name"),
            "office_name": _g(rec, "new_offices.office_id.name"),
            "uc_ward": _g(rec, "sw_areas.uc_ward_id.name"),
            "lat_long": coords,
            "lat": lat,
            "lon": lon,
            "created_at": _g(rec, "created_at"),
            "updated_at": _g(rec, "updated_at"),
            "remarks": _g(rec, "remarks"),
            "urban_rural": _g(rec, "urban_rural"),
            "in_grevience": in_grev,
            "grevience_remarks": grev_remarks,
            "grevience_decisions": _g(rec, "finalized_grevience_remarks"),
            "final_action_time": _g(rec, "final_date_time") or _g(rec, "finalized_grevience_date_time"),
            "can_auto_imposed": _g(rec, "is_auto_imposed"),
            "attachments": extract_attachments_grouped(rec),
            "raw": rec,
            "fetched_at": now,
        })
    return out