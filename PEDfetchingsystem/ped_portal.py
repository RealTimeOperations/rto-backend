# -*- coding: utf-8 -*-
"""
PED Monthly Report — Suthra Portal client (HARDENED multi-variant fetch)
✅ Har month ke liye multiple payload formats + multiple row-keys try karta hai
✅ Console par print hota hai ke kaunsa variant/key kaam kiya
"""
import os
import sys
import json
import base64
import re
import time
import calendar
import requests

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from attendancefetchingsystem.attendancefetchingmethod import portal_client as PC

PED_URL = PC.API_URL.rstrip("/") + "/ped/get-monthly-ped-wise-report"
OFFICE_ID = int(os.getenv("PED_OFFICE_ID", "9827"))

_MONTH_NAMES = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}


# =========================================================
# DECODER
# =========================================================
def decode_ped_data(s):
    if isinstance(s, (dict, list)):
        return s
    s = (s or "").strip()
    if not s:
        return None
    rev = s[::-1]
    rev += "=" * ((-len(rev)) % 4)
    raw = base64.b64decode(rev)
    return json.loads(raw.decode("utf-8", errors="replace"))


# =========================================================
# Helpers
# =========================================================
def _num(v):
    if v is None:
        return 0.0
    s = str(v).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _pick(d: dict, *pats):
    for k, v in (d or {}).items():
        kl = str(k).lower()
        for p in pats:
            if p in kl:
                return v
    return None


def _last_day(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _parse_date(v):
    """Har common date format ko YYYY-MM-DD mein badlo"""
    s = str(v if v is not None else "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]{3,9})[-/ ](\d{4})", s)
    if m:
        mo = _MONTH_NAMES.get(m.group(2)[:3].lower(), 0)
        if mo:
            return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(1)):02d}"
    m = re.match(r"^([A-Za-z]{3,9}) (\d{1,2}),? (\d{4})", s)
    if m:
        mo = _MONTH_NAMES.get(m.group(1)[:3].lower(), 0)
        if mo:
            return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d, mo = (a, b) if a > 12 or b <= 12 else (b, a)
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


# =========================================================
# Payload variants — portal kis format se month pick kare
# =========================================================
def _payload_variants(month: str):
    y, m = month.split("-")
    yi, mi = int(y), int(m)
    ld = _last_day(yi, mi)
    d1 = f"{month}-01T12:00:00.000Z"
    d15 = f"{month}-15T12:00:00.000Z"
    dend = f"{month}-{ld:02d}T12:00:00.000Z"
    return [
        {"office_id": OFFICE_ID, "date_from": d1},
        {"office_id": OFFICE_ID, "date_from": d1, "month": mi, "year": yi},
        {"office_id": OFFICE_ID, "date_from": d15},
        {"office_id": OFFICE_ID, "date_from": d1, "date_to": dend},
        {"office_id": OFFICE_ID, "month": mi, "year": yi},
        {"office_id": OFFICE_ID, "date_from": f"{month}-01"},
    ]


# =========================================================
# Header + rows extraction (har possible key cover)
# =========================================================
def _extract_header(decoded):
    div = decoded.get("division") or {}
    dist = decoded.get("district") or {}
    tehsil = decoded.get("tehsil") or {}
    contractor = decoded.get("contractor") or {}
    return {
        "division": div.get("name", "") if isinstance(div, dict) else str(div),
        "district": dist.get("name", "") if isinstance(dist, dict) else str(dist),
        "tehsil": tehsil.get("name", "") if isinstance(tehsil, dict) else str(tehsil),
        "office": tehsil.get("tehsil_shortcode", "") if isinstance(tehsil, dict) else "",
        "contractor": contractor.get("firm_name", "") if isinstance(contractor, dict) else str(contractor),
        "ped_date": decoded.get("ped_date", ""),
        "soe_years": decoded.get("soe_years"),
    }


def _rows_from_list(lst):
    out = []
    for r in lst:
        if not isinstance(r, dict):
            continue
        date = ""
        for k in ("report_date", "date", "day", "ped_date", "report_day"):
            date = _parse_date(r.get(k))
            if date:
                break
        if not date:
            for k in r.keys():
                if "date" in str(k).lower():
                    date = _parse_date(r.get(k))
                    if date:
                        break
        if not date:
            continue
        per_day_invoice = _num(r.get('per_day_invoice') or _pick(r, "rfp"))
        total_invoice_amount = _num(r.get('total_invoice_amount') or r.get('ped_amount'))
        # ✅ FIX: row_grand_total_amount DIRECT .get() se — _pick("total_invoice") pehle
        #    'total_invoice_amount' (PED Amount) se match kar ke GALAT value return karta tha
        row_grand_total = _num(r.get('row_grand_total_amount') or r.get('row_grand_total') or r.get('grand_total'))
        total_score = _num(r.get('total_score') or r.get('ped_score'))
        final_invoice_score = _num(r.get('final_invoice_score'))
        if final_invoice_score == 0.0 and per_day_invoice > 0 and row_grand_total > 0:
            final_invoice_score = round(row_grand_total / per_day_invoice * 100, 2)
        out.append({
            "row_date": date,
            "sr": int(_num(_pick(r, "sr", "serial"))),
            "rfp_amount": per_day_invoice,
            "ped_amount": total_invoice_amount,
            "ped_score": total_score,
            "final_invoice_score": round(final_invoice_score, 2),
            "penalty_amount": _num(_pick(r, "total_penalty_amount", "penalty")),
            "escalation_amount": _num(_pick(r, "escalation")),
            "deduction_surplus": _num(_pick(r, "deduction", "surplus")),
            "total_invoice": row_grand_total,
            "finalized": "Yes" if str(_pick(r, "is_finalized", "finalized", "final") or "No").lower() in ("1", "true", "yes") else "No",
        })
    return out


def _row_candidates(decoded):
    """Rows wali lists ko priority order mein yield karo"""
    if isinstance(decoded, list):
        yield ("root", decoded)
        return
    if not isinstance(decoded, dict):
        return
    prio = ["report_data", "report_data_finalized_detail", "finalized_report_data",
            "monthly_report_data", "ped_report_data", "ped_monthly_data",
            "data", "rows", "records", "items", "list", "results", "details", "report"]
    seen = set()
    for k in prio:
        v = decoded.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict) and k not in seen:
            seen.add(k)
            yield (k, v)
    # Phir wo lists jin ke items mein date-key ho
    for k, v in decoded.items():
        if k in seen:
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if any("date" in str(kk).lower() or str(kk).lower() == "day" for kk in v[0].keys()):
                seen.add(k)
                yield (k, v)
    # Aakhri mein: koi bhi list of dicts
    for k, v in decoded.items():
        if k in seen:
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            seen.add(k)
            yield (k, v)


def normalize(decoded):
    header, rows = {}, []
    if isinstance(decoded, list):
        rows = [r for r in decoded if isinstance(r, dict)]
    elif isinstance(decoded, dict):
        div = decoded.get('division') or {}
        dist = decoded.get('district') or {}
        tehsil = decoded.get('tehsil') or {}
        contractor = decoded.get('contractor') or {}
        header = {
            'division': div.get('name', ''),
            'district': dist.get('name', ''),
            'tehsil': tehsil.get('name', ''),
            'office': tehsil.get('tehsil_shortcode', ''),
            'contractor': contractor.get('firm_name', ''),
            'ped_date': decoded.get('ped_date', ''),
        }
        rows = decoded.get('report_data', [])
        if not rows:
            for _k, v in decoded.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    rows = v
                    break
    out = []
    for r in rows:
        date = str(r.get('report_date') or '').strip()
        if len(date) < 10 or date[:4].isdigit() is False:
            date = str(r.get('date') or r.get('day') or '').strip()
            if len(date) < 10 or date[:4].isdigit() is False:
                continue
        per_day_invoice = _num(r.get('per_day_invoice') or r.get('rfp'))
        total_invoice_amount = _num(r.get('total_invoice_amount') or r.get('ped_amount'))
        # ✅ FIX: DIRECT .get() — _pick() mein "total_invoice" pattern
        #    'total_invoice_amount' (PED Amount) se pehle match kar jata tha!
        row_grand_total = _num(r.get('row_grand_total_amount'))
        if row_grand_total == 0.0:
            row_grand_total = _num(r.get('row_grand_total') or r.get('grand_total'))
        total_score = _num(r.get('total_score') or r.get('ped_score'))
        final_invoice_score = _num(r.get('final_invoice_score'))
        if final_invoice_score == 0.0 and per_day_invoice > 0 and row_grand_total > 0:
            final_invoice_score = round(row_grand_total / per_day_invoice * 100, 2)
        out.append({
            "row_date": date[:10],
            "sr": int(_num(_pick(r, "sr", "serial"))),
            "rfp_amount": per_day_invoice,
            "ped_amount": total_invoice_amount,
            "ped_score": total_score,
            "final_invoice_score": round(final_invoice_score, 2),
            "penalty_amount": _num(r.get('total_penalty_amount') or r.get('penalty_amount')),
            "escalation_amount": _num(r.get('escalation_amount')),
            "deduction_surplus": _num(r.get('deduction_surplus')),
            "total_invoice": row_grand_total,
            "finalized": "Yes" if r.get('is_finalized') in (1, '1', True) or str(r.get('finalized', '')).lower() == 'yes' else "No",
        })
    return header, out


# =========================================================
# FETCH — multi-variant
# =========================================================
def fetch_month(month: str):
    """
    month = 'YYYY-MM' (e.g. '2026-05')
    Returns: (header_dict, rows_list, raw_decoded)
    """
    # ✅ 1. Login karo (token, office_id, designation_id return karta hai)
    token, office_id, designation_id = PC.login()
    
    # ✅ 2. Payload banao (month aur year explicitly bhejna zaroori hai old data ke liye)
    y, m = month.split('-')
    date_from = f"{month}-01T12:00:00.000Z"
    
    payload_dict = {
        "office_id": OFFICE_ID, 
        "date_from": date_from,
        "month": int(m),   # ✅ Portal ko integer month chahiye
        "year": int(y)     # ✅ Portal ko integer year chahiye
    }
    
    body_str = json.dumps(payload_dict, separators=(',', ':'))
    body_bytes = body_str.encode("utf-8")
    
    # ✅ 3. Headers correctly build karo
    headers = PC.base_headers()
    headers["Referer"] = "https://suthra.punjab.gov.pk/ped/ped-monthly-report"
    headers["Authorization"] = "Bearer " + token
    headers["Active-Office-Id"] = str(OFFICE_ID)
    headers["Active-Designation-Id"] = str(designation_id)
    headers.update(PC.sign_headers("POST", PED_URL, body_str, token))
    
    # ✅ 4. Request bhejo
    print(f"🚀 Fetching PED payload: {payload_dict}") # Debugging ke liye
    resp = requests.post(PED_URL, data=body_bytes, headers=headers, timeout=90)
    resp.raise_for_status()
    j = resp.json()
    
    if not j.get("success"):
        raise RuntimeError(f"Portal error: {j.get('message', 'unknown')}")
        
    # ✅ 5. Decode aur normalize karo
    decoded = decode_ped_data(j.get("data"))
    if decoded is None:
        raise RuntimeError("Empty data from portal")
        
    header, rows = normalize(decoded)
    
    # ✅ Portal ke extra fields header mein merge
    if isinstance(j, dict):
        header.setdefault("soe_years", j.get("SOE_YEAR"))
        
    return header, rows, decoded


if __name__ == "__main__":
    import datetime
    m = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime("%Y-%m")
    print(f"🚀 Fetching PED data for month: {m} ...")
    try:
        h, r, _ = fetch_month(m)
        print("✅ HEADER:", json.dumps(h, ensure_ascii=False)[:500])
        print(f"✅ ROWS: {len(r)} records found")
        for x in r[:3]:
            print("  -", x)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()