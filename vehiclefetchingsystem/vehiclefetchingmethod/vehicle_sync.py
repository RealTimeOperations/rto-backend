"""
Vehicle Sync — portal se vehicles fetch kar ke Supabase mein upsert.
Manual trigger only (terminal YA backend API /vehicles/sync se) — koi auto-sync nahi.
"""
import os
import sys
import time
from datetime import datetime

# Backend root + method dir ko sys.path mein add karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vehicle_portal import fetch_all_vehicles
from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
from supabase import create_client

SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
TABLE_NAME = "vehiclesdata"


def sync_to_supabase():
    """✅ Portal → Supabase sync. Returns dict {ok, total, assigned, unassigned, inactive, message}."""
    print("\n" + "=" * 80)
    print("🚀 VEHICLE SYNC - MANUAL TRIGGER")
    print("=" * 80)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    t0 = time.time()

    mapped = fetch_all_vehicles()
    if not mapped:
        print("⚠️ No vehicles fetched from portal. Sync aborted.")
        return {"ok": False, "total": 0, "assigned": 0, "unassigned": 0, "inactive": 0,
                "message": "No vehicles fetched from portal"}

    # ✅ 'id' = portal ka unique raw id (portal_id) — registration_number duplicate ho sakta hai
    for m in mapped:
        pid = str(m.get("portal_id") or "").strip()
        reg_num = str(m.get("registration_number") or "").strip().upper()
        m["id"] = pid if pid else f"{m['category']}::{reg_num or 'UNKNOWN'}"
        m.pop("portal_id", None)   # portal_id column DB mein nahi hai

    print(f"\n💾 Upserting {len(mapped)} vehicles to Supabase table '{TABLE_NAME}'...")
    try:
        for i in range(0, len(mapped), 100):
            SB.table(TABLE_NAME).upsert(mapped[i:i + 100], on_conflict="id").execute()

        # ✅ STALE CLEANUP: jo rows portal se ghayab hain unhe DB se remove
        try:
            existing = SB.table(TABLE_NAME).select("id").execute()
            new_ids = {m["id"] for m in mapped}
            stale = [r["id"] for r in (existing.data or []) if r["id"] not in new_ids]
            for i in range(0, len(stale), 500):
                SB.table(TABLE_NAME).delete().in_("id", stale[i:i + 500]).execute()
            if stale:
                print(f"🧹 Stale cleanup: {len(stale)} purani rows DB se remove")
        except Exception as e:
            print(f"⚠️ Stale cleanup failed: {e}")

        a_cnt = sum(1 for m in mapped if m["category"] == "assigned")
        u_cnt = sum(1 for m in mapped if m["category"] == "unassigned")
        i_cnt = sum(1 for m in mapped if m["category"] == "inactive")
        print(f"✅ Successfully synced {len(mapped)} vehicles in {time.time() - t0:.1f}s!")
        print(f"   📊 Assigned: {a_cnt} | Un-Assigned: {u_cnt} | In-Active: {i_cnt}")
        print("=" * 80)
        return {"ok": True, "total": len(mapped), "assigned": a_cnt, "unassigned": u_cnt,
                "inactive": i_cnt,
                "message": f"Updated: {len(mapped)} vehicles (A:{a_cnt} U:{u_cnt} I:{i_cnt})"}
    except Exception as e:
        print(f"❌ Supabase upsert failed: {e}")
        import traceback
        traceback.print_exc()
        return {"ok": False, "total": 0, "assigned": 0, "unassigned": 0, "inactive": 0,
                "message": f"Supabase upsert failed: {e}"}


if __name__ == "__main__":
    result = sync_to_supabase()
    print("\n" + "=" * 80)
    if result["ok"]:
        print(f"✅ Sync finished! Total: {result['total']}")
    else:
        print(f"❌ Sync failed: {result['message']}")
    print("=" * 80)