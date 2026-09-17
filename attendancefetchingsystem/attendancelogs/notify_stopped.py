"""
Writes the STOP line to the attendance log and updates the heartbeat.
Lives in attendancelogs/ and writes to the same folder it sits in.
"""
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))       # .../attendancelogs
ROOT_DIR = os.path.dirname(os.path.dirname(LOGS_DIR))       # .../backend
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from supabase import create_client

LOG_FILE = os.path.join(LOGS_DIR, "auto_attendance.log")
REASON = sys.argv[1] if len(sys.argv) > 1 else "PC shutdown / logoff"

# 1) Rewrite the log with the STOP line (only the latest line is kept)
try:
    line = "[" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "] PROCESS STOPPED - " + REASON
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(line + "\n")
except Exception:
    pass

# 2) Update heartbeat so the frontend goes RED instantly
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY', '')
try:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    sb.table("system_heartbeat").upsert(
        {"id": 1, "status": "stopped", "message": "Process stopped - " + REASON,
         "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="id",
    ).execute()
except Exception:
    pass