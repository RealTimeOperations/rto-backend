# -*- coding: utf-8 -*-
"""PED old-month diagnosis — 8 payload variants try karo aur portal ka asal response dikhao"""
import os, sys, json, base64, requests

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from attendancefetchingsystem.attendancefetchingmethod import portal_client as PC

PED_URL = PC.API_URL.rstrip("/") + "/ped/get-monthly-ped-wise-report"
OFFICE_ID = int(os.getenv("PED_OFFICE_ID", "9827"))

def decode(s):
    if isinstance(s, (dict, list)):
        return s
    s = (s or "").strip()
    if not s:
        return None
    rev = s[::-1]
    rev += "=" * ((-len(rev)) % 4)
    return json.loads(base64.b64decode(rev).decode("utf-8", errors="replace"))

MONTH = sys.argv[1] if len(sys.argv) > 1 else "2026-07"
y, m = MONTH.split("-")
print(f"🔍 Diagnosing month: {MONTH}\n")
token, office_id, designation_id = PC.login()

d1 = f"{MONTH}-01T12:00:00.000Z"
variants = {
    "A  date_from only (current code)": {"office_id": OFFICE_ID, "date_from": d1},
    "B  + month/year ints":             {"office_id": OFFICE_ID, "date_from": d1, "month": int(m), "year": int(y)},
    "C  mid-month date_from":           {"office_id": OFFICE_ID, "date_from": f"{MONTH}-15T12:00:00.000Z"},
    "D  date_from + date_to":           {"office_id": OFFICE_ID, "date_from": f"{MONTH}-01T00:00:00.000Z", "date_to": f"{MONTH}-28T23:59:59.000Z"},
    "E  month/year only":               {"office_id": OFFICE_ID, "month": int(m), "year": int(y)},
    "F  report_month key":              {"office_id": OFFICE_ID, "report_month": MONTH},
    "G  soe_year 2026-A":               {"office_id": OFFICE_ID, "date_from": d1, "soe_year": "2026-A"},
    "H  soe_year 2025-A":               {"office_id": OFFICE_ID, "date_from": d1, "soe_year": "2025-A"},
}

for name, payload in variants.items():
    body = json.dumps(payload, separators=(",", ":"))
    h = PC.base_headers()
    h["Referer"] = "https://suthra.punjab.gov.pk/ped/ped-monthly-report"
    h["Authorization"] = "Bearer " + token
    h["Active-Office-Id"] = str(OFFICE_ID)
    h["Active-Designation-Id"] = str(designation_id)
    h.update(PC.sign_headers("POST", PED_URL, body, token))
    try:
        r = requests.post(PED_URL, data=body.encode("utf-8"), headers=h, timeout=60)
        j = r.json()
        dec = decode(j.get("data"))
        info = f"success={j.get('success')} msg={str(j.get('message'))[:50]}"
        if isinstance(dec, dict):
            rd = dec.get("report_data")
            info += f" | ped_date={dec.get('ped_date')} | report_data={len(rd) if isinstance(rd, list) else 'MISSING'}"
            if isinstance(rd, list) and rd:
                info += f" | first_row_date={rd[0].get('report_date')}"
            if not (isinstance(rd, list) and rd):
                lists = {k: len(v) for k, v in dec.items() if isinstance(v, list) and v}
                info += f" | non-empty lists={lists} | keys={list(dec.keys())[:14]}"
        elif isinstance(dec, list):
            info += f" | TOP-LIST rows={len(dec)}"
        else:
            info += f" | data={'EMPTY' if dec is None else type(dec).__name__}"
        print(f"{name}\n   → HTTP {r.status_code} | {info}\n")
    except Exception as e:
        print(f"{name}\n   → ERROR {e}\n")