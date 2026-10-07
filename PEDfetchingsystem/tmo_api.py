# -*- coding: utf-8 -*-
"""
TMO Score — FastAPI router (TRIGGER based)
POST /tmo/sync   → range fetch kar ke DB rewrite
GET  /tmo/data   → stored meta + rows
GET  /tmo/status → health
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from . import tmo_sync
from .tmo_sync import sb

router = APIRouter(tags=["TMO"])


class TmoSyncReq(BaseModel):
    date_from: Optional[str] = None   # 'YYYY-MM-DD'
    date_to: Optional[str] = None     # 'YYYY-MM-DD'


@router.post("/tmo/sync")
def tmo_trigger_sync(req: Optional[TmoSyncReq] = None):
    df = req.date_from if req else None
    dt = req.date_to if req else None
    try:
        return tmo_sync.sync_range(df, dt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TMO sync failed: {e}")


@router.get("/tmo/data")
def tmo_data():
    try:
        meta_q = sb.table("tmoscoremeta").select("*").order("fetched_at", desc=True).limit(1).execute()
        rows = sb.table("tmoscoredata").select("*").order("report_date", desc=False).order("sr_no", desc=False).execute()
        return {"meta": meta_q.data[0] if meta_q.data else None, "rows": rows.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tmo/status")
def tmo_status():
    try:
        m = sb.table("tmoscoremeta").select("*").order("fetched_at", desc=True).limit(1).execute()
        last = m.data[0] if m.data else None
        return {"ok": True, "service": "tmo", "last_sync": last}
    except Exception as e:
        return {"ok": False, "service": "tmo", "error": str(e)}