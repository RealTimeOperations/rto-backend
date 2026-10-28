"""
Vehicle Status Sync — Tracking World portal se data fetch kar ke Supabase mein upsert karta hai.
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Backend root ko sys.path mein add karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from vehiclestatus import fetch_all_vehicle_status
    from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
    from supabase import create_client
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
TABLE_NAME = "vehicle_tracking_status"


def sync_to_supabase():
    print("\n" + "=" * 80)
    print(" VEHICLE STATUS SYNC — Tracking World to Supabase")
    print("=" * 80)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    t0 = time.time()

    # 1. Fetch data from portal
    counts, vehicles = fetch_all_vehicle_status()
    if not vehicles:
        print("⚠️ No vehicles fetched from portal. Sync aborted.")
        return

    # 2. Map data for Supabase (id = regNo)
    mapped = []
    for v in vehicles:
        reg_no = str(v.get("regNo") or "").strip().upper()
        if not reg_no:
            continue

        mapped.append({
            "id": reg_no,
            "region": v.get("region", ""),
            "reporting_datetime": v.get("reportingDateTime") if v.get("reportingDateTime") else None,
            "location": v.get("location", ""),
            "reporting_status": v.get("reportingStatus", ""),
            "status_text": v.get("statusText", ""),
            "battery_status": v.get("batteryStatus", ""),
            "wiring_status": v.get("wiringStatus", ""),
            "fetched_at": datetime.now().isoformat(),
        })

    print(f"\n💾 Upserting {len(mapped)} vehicles to Supabase table '{TABLE_NAME}'...")

    try:
        # Batch upsert (100 records at a time)
        for i in range(0, len(mapped), 100):
            batch = mapped[i:i + 100]
            SB.table(TABLE_NAME).upsert(batch, on_conflict="id").execute()

        print(f"✅ Successfully synced {len(mapped)} vehicle statuses in {time.time() - t0:.1f}s!")

        # Summary
        reporting = sum(1 for m in mapped if m["reporting_status"] == "Reporting")
        not_reporting = sum(1 for m in mapped if m["reporting_status"] != "Reporting")
        print(f"   📊 Reporting: {reporting} | Not Reporting: {not_reporting}")

    except Exception as e:
        print(f"❌ Supabase upsert failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("✅ Sync process finished! Ab aap Supabase table check kar sakte hain.")
    print("=" * 80)


if __name__ == "__main__":
    sync_to_supabase()