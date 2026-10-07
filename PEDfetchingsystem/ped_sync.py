# -*- coding: utf-8 -*-
"""
PED Monthly Report → Supabase sync (month-wise, historical data preserved)
✅ Trigger-based: sirf jab API/button call kare
"""
import os
import datetime

from supabase import create_client

from . import ped_portal

# ✅ Supabase client (baqi sync scripts jaisa)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
)
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def current_month() -> str:
    return datetime.datetime.now().strftime("%Y-%m")


def sync_month(month: str = None):
    """
    Ek month ki portal report fetch kar ke Supabase mein upsert karo.
    Purana data replace hota hai usi month ka — baqi months mehfooz rehte hain.
    """
    month = month or current_month()
    header, rows, _raw = ped_portal.fetch_month(month)

    if not rows:
        return {"status": "empty", "month": month, "rows": 0}

    now = datetime.datetime.now().isoformat()

    # ✅ Daily rows upsert (unique: month + row_date)
    db_rows = []
    for r in rows:
        db_rows.append({
            "month": month,
            "row_date": r["row_date"],
            "sr": r["sr"],
            "rfp_amount": r["rfp_amount"],
            "ped_amount": r["ped_amount"],
            "ped_score": r["ped_score"],
            "final_invoice_score": r["final_invoice_score"],
            "penalty_amount": r["penalty_amount"],
            "escalation_amount": r["escalation_amount"],
            "deduction_surplus": r["deduction_surplus"],
            "total_invoice": r["total_invoice"],
            "finalized": r["finalized"],
            "fetched_at": now,
        })
    sb.table("pedmonthlydata").upsert(db_rows, on_conflict="month,row_date").execute()

    # ✅ Month meta (header info + totals) upsert
    tot = {
        "rfp": sum(r["rfp_amount"] for r in rows),
        "ped": sum(r["ped_amount"] for r in rows),
        "penalty": sum(r["penalty_amount"] for r in rows),
        "escalation": sum(r["escalation_amount"] for r in rows),
        "deduction": sum(r["deduction_surplus"] for r in rows),
        "invoice": sum(r["total_invoice"] for r in rows),
    }
    meta = {
        "month": month,
        "district": str(ped_portal._pick(header, "district") or ""),
        "tehsil": str(ped_portal._pick(header, "tehsil") or ""),
        "office": str(ped_portal._pick(header, "office") or ""),
        "contractor": str(ped_portal._pick(header, "contractor") or ""),
        "print_date_time": str(ped_portal._pick(header, "print") or ""),
        "total_rfp": tot["rfp"],
        "total_ped": tot["ped"],
        "total_penalty": tot["penalty"],
        "total_escalation": tot["escalation"],
        "total_deduction": tot["deduction"],
        "total_invoice": tot["invoice"],
        "rows_count": len(rows),
        "soe_years": header.get("soe_years"),
        "fetched_at": now,
    }
    sb.table("pedmonthlymeta").upsert(meta, on_conflict="month").execute()

    return {"status": "updated", "month": month, "rows": len(rows), "totals": tot}


if __name__ == "__main__":
    import sys
    m = sys.argv[1] if len(sys.argv) > 1 else None
    print(sync_month(m))