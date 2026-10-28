"""
Vehicle Status Fetcher — Tracking World portal se real-time vehicle status.
APIs: getstatuscount (counts) + getstatus (detailed list)
Terminal test ke liye — abhi koi DB write NAHI.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Backend root ko sys.path mein add karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ✅ Tracking World Portal Configuration
BASE_URL = os.getenv("TRACKING_PORTAL_URL", "http://wmc.trackingworld.com.pk")
TOKEN_URL = f"{BASE_URL}/api/generate-token"
STATUS_COUNT_URL = f"{BASE_URL}/api/vehicle/getstatuscount"
STATUS_LIST_URL = f"{BASE_URL}/api/vehicle/getstatus"

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
    except Exception as e:
        print(f"❌ Login error: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_vehicle_status_count(token):
    """Vehicle status counts fetch karein (Total, Reporting, Moving, Parked, etc.)"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    payload = {}  # Empty body for all vehicles
    
    try:
        resp = requests.post(STATUS_COUNT_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract counts from response
        counts_data = data.get("data", {})
        
        print(f"\n📊 Vehicle Status Counts:")
        print(f"   Total: {counts_data.get('totalVehicles', 'N/A')}")
        print(f"   Reporting: {counts_data.get('reporting', 'N/A')}")
        print(f"   Not Reporting: {counts_data.get('notReporting', 'N/A')}")
        print(f"   Moving: {counts_data.get('moving', 'N/A')}")
        print(f"   Parked: {counts_data.get('parked', 'N/A')}")
        print(f"   Idle: {counts_data.get('idle', 'N/A')}")
        print(f"   Battery Issue: {counts_data.get('batteryIssue', 'N/A')}")
        print(f"   Wiring Issue: {counts_data.get('wiringIssue', 'N/A')}")
        
        return counts_data
        
    except Exception as e:
        print(f"❌ Error fetching status counts: {e}")
        return {}


def fetch_vehicle_status_list(token):
    """Detailed vehicle status list fetch karein (har vehicle ki detail)."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    payload = {}  # Empty body for all vehicles
    
    try:
        print("\n📋 Fetching detailed vehicle status list...")
        resp = requests.post(STATUS_LIST_URL, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract vehicle statuses from response
        vehicles_data = data.get("data", {}).get("vehicleStatuses", [])
        
        print(f"✅ Fetched {len(vehicles_data)} vehicles")
        
        # Terminal preview (first 5 vehicles)
        if vehicles_data:
            print(f"\n   🔑 Raw keys (first record): {list(vehicles_data[0].keys())[:20]}")
            print("\n   📝 First 5 vehicles preview:")
            print(f"   {'Sr#':<4} {'Reg No':<12} {'Region':<15} {'Status':<12} {'Location':<40}")
            print("   " + "-" * 90)
            
            for idx, v in enumerate(vehicles_data[:5], 1):
                reg_no = v.get("regNo", "N/A")
                region = v.get("region", "N/A")
                status = v.get("reportingStatus", "N/A")
                location = v.get("location", "N/A")[:38]
                print(f"   {idx:<4} {reg_no:<12} {region:<15} {status:<12} {location:<40}")
        
        return vehicles_data
        
    except Exception as e:
        print(f"❌ Error fetching vehicle status list: {e}")
        return []


def map_vehicle_status(vehicles_list):
    """Raw portal data ko simplified format mein convert karein."""
    mapped = []
    
    for v in vehicles_list:
        mapped.append({
            "regNo": v.get("regNo", ""),
            "region": v.get("region", ""),
            "reportingDateTime": v.get("reportingDateTime", ""),
            "location": v.get("location", ""),
            "reportingStatus": v.get("reportingStatus", ""),
            "statusText": v.get("statusText", ""),  # Moving/Parked/Idle
            "batteryStatus": v.get("batteryStatus", ""),
            "wiringStatus": v.get("wirringStatus", ""),  # Note: API mein 'wirringStatus' hai
            "fetched_at": datetime.now().isoformat(),
        })
    
    return mapped


def fetch_all_vehicle_status():
    """Main function — login + counts + detailed list fetch."""
    print("=" * 100)
    print("🚗 VEHICLE STATUS FETCH — Tracking World Portal")
    print("=" * 100)
    print(f" Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Login
    token = login()
    if not token:
        print("\n❌ Login failed! Aborting...")
        return None, None
    
    # Fetch counts
    counts = fetch_vehicle_status_count(token)
    time.sleep(0.5)
    
    # Fetch detailed list
    vehicles_list = fetch_vehicle_status_list(token)
    
    # Map data
    mapped_vehicles = map_vehicle_status(vehicles_list)
    
    print("\n" + "=" * 100)
    print("✅ Vehicle status fetch completed!")
    print("=" * 100)
    
    return counts, mapped_vehicles


if __name__ == "__main__":
    counts, vehicles = fetch_all_vehicle_status()
    
    if vehicles:
        print(f"\n Total records ready: {len(vehicles)}")
        print("\n💡 Next step: Supabase sync banayenge")
    else:
        print("\n❌ No data fetched!")