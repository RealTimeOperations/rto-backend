"""
Containers Portal Fetcher — Suthra portal se container service daily report.
Login + signature logic attendance wale portal_client se reuse hoti hai.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime

# Backend root ko sys.path mein add karo (script mode mein bhi imports chalein)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from attendancefetchingsystem.attendancefetchingmethod import portal_client as PC

REPORT_URL = PC.API_URL + "/ped/get-container-service-daily-report"


def login():
    """Reuse the shared attendance portal client login (same credentials + signature)."""
    return PC.login()


def extract_records(d):
    """Portal response mein records list dhoondho (flexible nesting)."""
    node = d
    for _ in range(4):
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            node = node.get("data", node.get("rows", node.get("records", node.get("result"))))
        else:
            break
    return node if isinstance(node, list) else []


def fetch_container_report(token, office_id, designation_id):
    """Paginated fetch of the container service daily report (today)."""
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    page = 1
    while page <= 10:
        body = json.dumps({
            "date_from": today,
            "division_id": 1,
            "district_id": 2,
            "office_id": office_id,
            "container_service": None,
            "app_serviced": None,
            "stop_point_serviced": None,
            "page": page,
            "per_page": 500,
        }, separators=(',', ':'))
        h = PC.base_headers()
        h["Referer"] = "https://suthra.punjab.gov.pk/solid-waste/container-service-daily-report"
        h["Authorization"] = "Bearer " + token
        h["Active-Office-Id"] = str(office_id)
        h["Active-Designation-Id"] = str(designation_id)
        h.update(PC.sign_headers("POST", REPORT_URL, body, token))
        r = requests.post(REPORT_URL, data=body, headers=h, timeout=30)
        r.raise_for_status()
        recs = extract_records(r.json())
        out.extend(recs)
        if len(recs) < 500:
            break
        page += 1
        time.sleep(0.3)
    print(f"Fetched {len(out)} container records")
    return out


def norm_yesno(v):
    s = str(v if v is not None else "").strip().lower()
    return "YES" if s in ("yes", "true", "1", "y") else "NO"


def map_records(recs):
    """Portal raw fields -> portal_data table columns (old app jaisi mapping)."""
    mapped = []
    for rec in recs:
        site = str(rec.get("primary_site_name") or "").strip()
        if not site or site.lower() == "nan":
            continue
        mapped.append({
            "site": site,
            "container_serviced": norm_yesno(rec.get("both_matched")),
            "serviced_on_app": norm_yesno(rec.get("app_serviced")),
            "serviced_by_tracker": norm_yesno(rec.get("stop_point_serviced")),
            "app_vehicle": str(rec.get("app_vehicle") or rec.get("stop_point_vehicle") or "").strip(),
            "app_date_time": str(rec.get("app_datetime") or rec.get("stop_point_datetime") or "").strip(),
        })
    return mapped