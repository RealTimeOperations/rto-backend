"""
FastAPI Backend — Manual sync endpoints
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import attendance_sync
import employees_sync

app = FastAPI(title="RTO Attendance & HR Sync API")

# CORS (frontend se call kar sakein)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "message": "RTO Attendance & HR Sync API",
        "endpoints": {
            "/sync/attendance": "POST - Fetch attendance logs from portal & sync to Supabase",
            "/sync/employees": "POST - Fetch assigned employees from portal & sync to Supabase",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "rto-sync"}

@app.post("/sync/attendance")
def sync_attendance():
    """Manual trigger: Attendance logs fetch + Supabase upload"""
    try:
        attendance_sync.main()
        return {"success": True, "message": "Attendance sync completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sync/employees")
def sync_employees():
    """Manual trigger: Assigned employees fetch + Supabase upload"""
    try:
        employees_sync.main()
        return {"success": True, "message": "Employees sync completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)