"""
Penalties Portal Fetcher — Suthra portal se contractor-penalties listing.
Sirf TEHSIL HAROONABAD (tehsil_id=4) + sirf CURRENT DATE ki penalties.
"""
import os
import sys
import json
import time
import requests
from collections import deque
from datetime import datetime

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
    {"key": "created_date_time", "column": True, "value": "Created Date&Time"},
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
    """Poore response mein records ki list dhoondho (BFS) —
    'data' mein user profile ho ya records kahin bhi hon, list of dicts milay gi."""
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


def _is_target_date(rec, target_date=None):
    """Record ki penalty_date target date ki hai ya nahi (flexible formats)."""
    v = ""
    for k in rec.keys():
        kl = str(k).strip().lower()
        if kl in ("penalty_date", "date", "created_date", "penalty_datetime"):
            v = str(rec[k] or "")
            break
    if not v:
        return True
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
        # Lat/Lon "coordinates" string se: "29.4780955,73.0225572"
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
            "raw": rec,
            "fetched_at": now,
        })
    return out