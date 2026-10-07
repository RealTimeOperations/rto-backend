# -*- coding: utf-8 -*-
"""
PED Monthly Report — FastAPI router (TRIGGER based, koi auto-fetch nahi)
Endpoints:
POST /ped/sync        → month fetch kar ke DB mein save (frontend button isi ko call karega)
GET  /ped/months      → DB mein mojood months ki list (old data dekhne ke liye)
GET  /ped/data        → ek month ka meta + rows
GET  /ped/status      → health + last sync time
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from . import ped_sync
from .ped_sync import sb

router = APIRouter(tags=["PED"])

class SyncReq(BaseModel):
    month: Optional[str] = None   # 'YYYY-MM' — na ho to current month

@router.post("/ped/sync")
def ped_trigger_sync(req: Optional[SyncReq] = None):
    """✅ Manual trigger — frontend ka 'Update' button isi ko marega"""
    month = req.month if req else None
    try:
        result = ped_sync.sync_month(month)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PED sync failed: {e}")
    return result

@router.get("/ped/months")
def ped_months():
    """✅ DB mein mojood sab months (nayi → purani)"""
    try:
        # ✅ FIX: Supabase Python uses `desc=True` instead of `ascending=False`
        r = sb.table("pedmonthlymeta").select("month, rows_count, fetched_at, total_invoice").order("month", desc=True).execute()
        return {"months": r.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ped/data")
def ped_data(month: str):
    """✅ Ek month ka poora data (meta + daily rows)"""
    try:
        # ✅ FIX: maybe_single() khali result par PGRST116 error raise karta hai (500 crash) —
        #    is liye limit(1) use karo: month na mile to meta = None, crash nahi hota
        meta_q = sb.table("pedmonthlymeta").select("*").eq("month", month).limit(1).execute()
        meta = meta_q.data[0] if meta_q.data else None
        rows = sb.table("pedmonthlydata").select("*").eq("month", month).order("row_date", desc=False).execute()
        return {"meta": meta, "rows": rows.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ped/status")
def ped_status():
    try:
        # ✅ FIX: Supabase Python uses `desc=True` instead of `ascending=False`
        r = sb.table("pedmonthlymeta").select("fetched_at").order("fetched_at", desc=True).limit(1).execute()
        last = (r.data or [{}])[0].get("fetched_at")
        return {"ok": True, "service": "ped", "last_sync": last}
    except Exception as e:
        return {"ok": False, "service": "ped", "error": str(e)}