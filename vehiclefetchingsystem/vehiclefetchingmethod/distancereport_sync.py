"""
Distance Report Sync — Tracking World portal se daily mileage report fetch kar ke Supabase mein upsert karta hai.
"""
import os
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Backend root ko sys.path mein add karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from distancereport import fetch_all_distance_report
from attendancefetchingsystem.attendancefetchingmethod import attendance_sync as ATT
from supabase import create_client

SB = create_client(ATT.SUPABASE_URL, ATT.SUPABASE_KEY)
TABLE_NAME = "vehicle_distance_reports"

def sync_to_supabase(days_back=0):
    print("\n" + "=" * 80)
    print("🚀 DISTANCE REPORT SYNC — Tracking World to Supabase")
    print("=" * 80)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    t0 = time.time()

    # 1. Fetch data from portal
    meta, report = fetch_all_distance_report(days_back=0)   # ✅ AAJ ki live report
    if not report:
        print("⚠️ No distance report fetched from portal. Sync aborted.")
        return

    # 2. Map data for Supabase (id = vehicleRegNumber)
    mapped = []
    report_date = meta["from_date"] # Report kis date ki hai
    
    for v in report:
        reg_no = str(v.get("vehicleRegNumber") or "").strip().upper()
        if not reg_no:
            continue
            
        mapped.append({
            "id": reg_no,
            "unit_id": str(v.get("unitID", "")),
            "vehicle_reg_number": reg_no,
            "veh_type": v.get("vehType", ""),
            "town": v.get("town", ""),
            "mileage": float(v.get("mileage", 0) or 0),
            "ig_on_time": v.get("igONTime", ""),
            "fuel_allocated": float(v.get("fuelAllocated", 0) or 0),
            "report_date": report_date,
            "fetched_at": datetime.now().isoformat(),
        })

    print(f"\n💾 Upserting {len(mapped)} distance records to Supabase table '{TABLE_NAME}'...")
    
    try:
        # Batch upsert (100 records at a time)
        for i in range(0, len(mapped), 100):
            batch = mapped[i:i + 100]
            SB.table(TABLE_NAME).upsert(batch, on_conflict="id").execute()
            
        print(f"✅ Successfully synced {len(mapped)} distance records in {time.time() - t0:.1f}s!")
        
    except Exception as e:
        print(f"❌ Supabase upsert failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("✅ Sync process finished! Ab aap Supabase table check kar sakte hain.")
    print("=" * 80)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync distance report to Supabase")
    parser.add_argument("--days", type=int, default=0, help="Number of days back for report (default: 0 = today)")
    args = parser.parse_args()
    
    sync_to_supabase(days_back=args.days)