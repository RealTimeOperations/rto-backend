#!/usr/bin/env python3
"""
Vehicle Data Fetch Trigger — terminal se manual test.
Usage: python vehicle_fetch_trigger.py
"""
import sys
import os

# ✅ Apna hi folder path mein add karo (chahe kahin se bhi run karo)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vehicle_portal import fetch_all_vehicles


def main():
    print("\n" + "=" * 130)
    print("🚀 VEHICLE MONITORING - MANUAL TRIGGER")
    print("=" * 130)
    print("\nPortal se Assigned / Un-Assigned / In-Active vehicles fetch honge (Tehsil Haroonabad).")
    print("Press Ctrl+C to cancel...\n")

    try:
        input("Press ENTER to start fetching...")
        vehicles = fetch_all_vehicles()

        if vehicles:
            print("\n✅ SUCCESS!")
            print(f"   • Total vehicles fetched: {len(vehicles)}")
            print("\n💡 Data verify ho gaya? Agla step: Supabase sync (vehicle_sync.py) banayenge.")
        else:
            print("\n❌ No data fetched!")

    except KeyboardInterrupt:
        print("\n\n⚠️  Fetch cancelled by user!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()