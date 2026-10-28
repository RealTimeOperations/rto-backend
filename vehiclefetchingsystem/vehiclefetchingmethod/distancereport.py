"""
Distance Report Fetcher — Tracking World portal se vehicle mileage/distance reports.
APIs: getlist (vehicle unit IDs) + distance/preview (mileage data)
Terminal test ke liye — abhi koi DB write NAHI.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Backend root ko sys.path mein add karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ✅ Tracking World Portal Configuration
BASE_URL = os.getenv("TRACKING_PORTAL_URL", "http://wmc.trackingworld.com.pk")
TOKEN_URL = f"{BASE_URL}/api/generate-token"
VEHICLE_LIST_URL = f"{BASE_URL}/api/vehicle/getlist"
DISTANCE_PREVIEW_URL = f"{BASE_URL}/api/report/distance/preview"

# ✅ Credentials from .env
TRACKING_USERNAME = os.getenv("TRACKING_USERNAME")
TRACKING_PASSWORD = os.getenv("TRACKING_PASSWORD")


def login():
    """Tracking World portal se bearer token hasil karein."""
    print("\n🔐 Logging into Tracking World portal...")
    
    if not TRACKING_USERNAME or not TRACKING_PASSWORD:
        print("❌ TRACKING_USERNAME ya TRACKING_PASSWORD .env mein set nahi hai!")
        return None
    
    payload = {
        "username": TRACKING_USERNAME,
        "password": TRACKING_PASSWORD
    }
    
    try:
        resp = requests.post(TOKEN_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        print(f"   🔍 Response type: {type(data).__name__}")
        if isinstance(data, dict):
            print(f"   📄 Response keys: {list(data.keys())}")
            print(f"   📄 succeeded: {data.get('succeeded')}")
            
            # Agar login fail hua to ruk jao
            if not data.get('succeeded'):
                print(f"   ❌ Login failed! API returned: {data}")
                return None
        
        token = None
        
        if isinstance(data, dict):
            data_val = data.get("data")
            
            # ✅ FIX: Agar data ek list hai, to token index 1 par hota hai
            if isinstance(data_val, list) and len(data_val) >= 2:
                token = data_val[1]
                
            # Fallback: direct root level par token check karein
            if not token:
                token = data.get("token") or data.get("access_token")
                
        if token:
            print(f"✅ Login OK | Token obtained")
            return token
        else:
            print(f"❌ Login failed: No token found in response")
            print(f"   Full response: {data}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Login request failed: {e}")
        return None


def fetch_vehicle_unit_list(token):
    """Sab vehicles ki list fetch karein with unitIDs (distance report ke liye zaroori)."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    payload = {}
    
    try:
        print("\n📋 Fetching vehicle unit list...")
        resp = requests.post(VEHICLE_LIST_URL, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract vehicles from response
        vehicles = data.get("data", [])
        
        print(f"✅ Fetched {len(vehicles)} vehicles")
        
        # Terminal preview
        if vehicles:
            print(f"\n   🔑 Raw keys (first record): {list(vehicles[0].keys())[:15]}")
            print("\n   📝 First 5 vehicles preview:")
            print(f"   {'Sr#':<4} {'Unit ID':<10} {'Reg No':<12} {'Vehicle Type':<20}")
            print("   " + "-" * 50)
            
            for idx, v in enumerate(vehicles[:5], 1):
                unit_id = v.get("unitID", "N/A")
                reg_no = v.get("regNo", "N/A")
                vtype = v.get("vehicleType", "N/A")
                print(f"   {idx:<4} {unit_id:<10} {reg_no:<12} {vtype:<20}")
        
        return vehicles
        
    except Exception as e:
        print(f" Error fetching vehicle list: {e}")
        return []


def fetch_distance_report(token, unit_ids, from_date, to_date):
    """
    Distance/mileage report fetch karein specific vehicles ke liye.
    
    Args:
        token: Bearer token
        unit_ids: List of vehicle unit IDs
        from_date: Start date (YYYY-MM-DD format)
        to_date: End date (YYYY-MM-DD format)
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    payload = {
        "UnitIDs": unit_ids,
        "FromDate": from_date,
        "ToDate": to_date
    }
    
    try:
        print(f"\n📊 Fetching distance report ({from_date} to {to_date})...")
        print(f"   Vehicles: {len(unit_ids)}")
        
        resp = requests.post(DISTANCE_PREVIEW_URL, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract summary from response
        summary = data.get("data", {}).get("summary", [])
        
        print(f"✅ Fetched {len(summary)} vehicle records")
        
        # Terminal preview
        if summary:
            print(f"\n   🔑 Raw keys (first record): {list(summary[0].keys())[:15]}")
            print("\n   📝 First 5 vehicles preview:")
            print(f"   {'Sr#':<4} {'Reg No':<12} {'Type':<15} {'Mileage':<10} {'IG Time':<12}")
            print("   " + "-" * 60)
            
            for idx, v in enumerate(summary[:5], 1):
                reg_no = v.get("vehicleRegNumber", "N/A")
                vtype = v.get("vehType", "N/A")
                mileage = v.get("mileage", "N/A")
                ig_time = v.get("igONTime", "N/A")
                print(f"   {idx:<4} {reg_no:<12} {vtype:<15} {mileage:<10} {ig_time:<12}")
        
        return summary
        
    except Exception as e:
        print(f" Error fetching distance report: {e}")
        return []


def map_distance_report(summary_list):
    """Raw portal data ko simplified format mein convert karein."""
    mapped = []
    
    for v in summary_list:
        mapped.append({
            "vehicleRegNumber": v.get("vehicleRegNumber", ""),
            "vehType": v.get("vehType", ""),
            "town": v.get("town", ""),
            "mileage": v.get("mileage", 0),
            "igONTime": v.get("igONTime", ""),
            "fuelAllocated": v.get("fuelAllocated", 0),
            "fetched_at": datetime.now().isoformat(),
        })
    
    return mapped


def fetch_all_distance_report(days_back=1):
    """
    Main function — login + vehicle list + distance report fetch.
    
    Args:
        days_back: Kitne din pehle se report chahiye (default: 1 = kal se aaj tak)
    """
    print("=" * 100)
    print("📊 DISTANCE REPORT FETCH — Tracking World Portal")
    print("=" * 100)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Login
    token = login()
    if not token:
        print("\n Login failed! Aborting...")
        return None, None
    
    # Fetch vehicle unit list
    vehicles = fetch_vehicle_unit_list(token)
    
    if not vehicles:
        print("\n No vehicles found! Aborting...")
        return None, None
    
    # Extract unit IDs
    unit_ids = [str(v.get("unitID")) for v in vehicles if v.get("unitID")]
    
    if not unit_ids:
        print("\n❌ No unit IDs found! Aborting...")
        return None, None
    
    # ✅ Portal window semantics: [FromDate 00:00 → ToDate 00:00) — ToDate EXCLUSIVE hota hai!
    #    days_back=0 → FromDate=AAJ, ToDate=KAL → AAJ ka LIVE mileage milta hai.
    #    (Pehle From=To=same din tha → window EMPTY → sab 0.00 aa raha tha)
    from_date = datetime.now() - timedelta(days=days_back)
    to_date = from_date + timedelta(days=1)

    from_date_str = from_date.strftime("%Y-%m-%d")
    to_date_str = to_date.strftime("%Y-%m-%d")
    
    time.sleep(0.5)
    
    # Fetch distance report
    summary = fetch_distance_report(token, unit_ids, from_date_str, to_date_str)
    
    # Map data
    mapped_report = map_distance_report(summary)
    
    print("\n" + "=" * 100)
    print("✅ Distance report fetch completed!")
    print("=" * 100)
    
    return {
        "from_date": from_date_str,
        "to_date": to_date_str,
        "vehicle_count": len(unit_ids)
    }, mapped_report


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch distance report from Tracking World portal")
    parser.add_argument("--days", type=int, default=1, help="Number of days back for report (default: 1)")
    args = parser.parse_args()
    
    meta, report = fetch_all_distance_report(days_back=args.days)
    
    if report:
        print(f"\n Total records ready: {len(report)}")
        print(f"📅 Date range: {meta['from_date']} to {meta['to_date']}")
        print("\n Next step: Supabase sync banayenge")
    else:
        print("\n❌ No data fetched!")