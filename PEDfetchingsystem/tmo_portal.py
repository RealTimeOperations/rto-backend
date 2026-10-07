# -*- coding: utf-8 -*-
"""
TMO Score — Suthra Portal client (autoform/get-item-listing)
✅ date=""  → pichle ~6 months ka data (147 rows)
✅ date="YYYY-MM-DD" → sirf us din ka data
✅ reversed-base64 `data` decoder (PED jaisa)
"""
import os
import sys
import json
import base64
import datetime
import requests

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from attendancefetchingsystem.attendancefetchingmethod import portal_client as PC

TMO_URL = PC.API_URL.rstrip("/") + "/autoform/get-item-listing"
OFFICE_ID = int(os.getenv("PED_OFFICE_ID", "9827"))

# ✅ View Columns Editor se columns (portal inhi keys se data return karta hai)
DISPLAYED_COLUMNS_ALL = [
    {"key": "sr_no", "column": True, "value": "Sr#"},
    {"key": "division_id", "column": True, "value": "Division"},
    {"key": "district_id", "column": True, "value": "District"},
    {"key": "office_id", "column": True, "value": "Office"},
    {"key": "date", "column": True, "value": "Date"},
    {"key": "door_to_door_waste_collection_percentage", "column": True, "value": "Door to Door Waste Collection (Percentage %)"},
    {"key": "door_to_door_waste_collection_remarks", "column": True, "value": "Door to Door Waste Collection Remarks"},
    {"key": "environment_friendly_percentage", "column": True, "value": "Environment friendly (Percentage %)"},
    {"key": "environment_friendly_remarks", "column": True, "value": "Environment friendly Remarks"},
    {"key": "approved_door_to_door_waste_collection", "column": True, "value": "Approved Door to Door Waste Collection"},
    {"key": "manual_sweeping_remarks", "column": True, "value": "Manual Sweeping Remarks"},
    {"key": "approved_environment_friendly", "column": True, "value": "Approved Environment friendly"},
    {"key": "manual_sweeping_percentage", "column": True, "value": "Manual Sweeping (Percentage %)"},
    {"key": "approved_manual_sweeping", "column": True, "value": "Approved Manual Sweeping"},
    {"key": "street_sweeping_commercial_percentage", "column": True, "value": "Street Sweeping (Commercial) (Percentage %)"},
    {"key": "street_sweeping_commercial_remarks", "column": True, "value": "Street Sweeping (Commercial) Remarks"},
    {"key": "approved_street_sweeping_commercial", "column": True, "value": "Approved Street Sweeping (Commercial)"},
    {"key": "created_date_time", "column": True, "value": "Created Date&Time"},
    {"key": "added_by", "column": True, "value": "Added By"},
    {"key": "approved_by_name", "column": True, "value": "Approved By Name"},
    {"key": "approved_by_designation", "column": True, "value": "Approved By Designation"},
    {"key": "approved_date_time", "column": True, "value": "Approved Date&Time"},
    {"key": "status", "column": True, "value": "Status"},
]


# =========================================================
# Decoder (PED jaisa reversed-base64)
# =========================================================
def decode(s):
    if isinstance(s, (dict, list)):
        return s
    s = (s or "").strip()
    if not s:
        return None
    rev = s[::-1]
    rev += "=" * ((-len(rev)) % 4)
    return json.loads(base64.b64decode(rev).decode("utf-8", errors="replace"))


def _num(v):
    if v is None:
        return 0.0
    s = str(v).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_date(v):
    s = str(v if v is not None else "").strip()
    if len(s) >= 10 and s[:4].isdigit():
        return s[:10]
    return ""


# =========================================================
# Single listing call
# =========================================================
def fetch_listing(date_str="", page=1, size=500):
    token, office_id, designation_id = PC.login()
    payload = {
        "slug": "ped-tmo-score",
        "id": "0",
        "page": page,
        "search_keyword": "",
        "displayedColumnsAll": DISPLAYED_COLUMNS_ALL,
        "filters_data": {"division_id": 1, "district_id": 2, "office_id": OFFICE_ID, "date": date_str},
        "module_id": 264,
        "plateform": "web",
        "requesting_url": "/ped/view/ped-tmo-score",
        "size": size,
        "sorting": "",
        "user_type": "contractor",
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    headers = PC.base_headers()
    headers["Referer"] = "https://suthra.punjab.gov.pk/ped/view/ped-tmo-score"
    headers["Authorization"] = "Bearer " + token
    headers["Active-Office-Id"] = str(OFFICE_ID)
    headers["Active-Designation-Id"] = str(designation_id)
    headers.update(PC.sign_headers("POST", TMO_URL, body_str, token))
    resp = requests.post(TMO_URL, data=body_str.encode("utf-8"), headers=headers, timeout=120)
    resp.raise_for_status()
    j = resp.json()
    if not j.get("success"):
        raise RuntimeError(f"Portal error: {j.get('message', 'unknown')}")
    return decode(j.get("data"))


# =========================================================
# Decoded → rows list [{report_date, sr_no, row}]
# =========================================================
def normalize_rows(decoded):
    lst = []
    if isinstance(decoded, list):
        lst = decoded
    elif isinstance(decoded, dict):
        for k in ("data", "rows", "items", "list", "records", "result"):
            v = decoded.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                lst = v
                break
        if not lst:
            for k, v in decoded.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    lst = v
                    break
    out = []
    for r in lst:
        if not isinstance(r, dict):
            continue
        date = _parse_date(r.get("date") or r.get("report_date") or r.get("day"))
        if not date:
            continue
        out.append({
            "report_date": date,
            "sr_no": int(_num(r.get("sr_no") or r.get("sr"))),
            "row": r,   # ✅ POORA raw row (all columns)
        })
    return out


def fetch_all_rows(date_str=""):
    """Pagination-safe: pages loop karo jab tak rows milte rahen"""
    rows, page = [], 1
    while page <= 10:
        batch = normalize_rows(fetch_listing(date_str=date_str, page=page, size=500))
        if not batch:
            break
        rows += batch
        if len(batch) < 500:
            break
        page += 1
    return rows


# =========================================================
# RANGE fetch: blank window + missing days day-by-day
# =========================================================
def fetch_range(date_from: str, date_to: str):
    # 1) Blank fetch — pichle ~6 months ka window (1 call)
    all_rows = fetch_all_rows(date_str="")
    sel = [r for r in all_rows if date_from <= r["report_date"] <= date_to]
    covered = {r["report_date"] for r in sel}

    # 2) Jo din window mein nahi mile → day-by-day fetch
    d = date_from
    while d <= date_to:
        if d not in covered:
            try:
                day_rows = fetch_all_rows(date_str=d)
                sel += [r for r in day_rows if date_from <= r["report_date"] <= date_to]
            except Exception as e:
                print(f"⚠️ day fetch {d} failed: {e}")
        d = (datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat()

    # 3) Dedupe + sort
    seen, final = set(), []
    for r in sorted(sel, key=lambda x: (x["report_date"], x["sr_no"])):
        key = (r["report_date"], r["sr_no"])
        if key not in seen:
            seen.add(key)
            final.append(r)
    return final


if __name__ == "__main__":
    today = datetime.date.today()
    df = sys.argv[1] if len(sys.argv) > 1 else today.replace(day=1).isoformat()
    dt = sys.argv[2] if len(sys.argv) > 2 else today.isoformat()
    print(f"🚀 Fetching TMO range: {df} → {dt}")
    rows = fetch_range(df, dt)
    print(f"✅ ROWS: {len(rows)}")
    if rows:
        print("🔑 First row keys:", list(rows[0]["row"].keys()))
        print("📄 Sample:", json.dumps(rows[0]["row"], ensure_ascii=False)[:600])