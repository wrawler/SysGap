# server/backend/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
import uuid
import json
import sys
import os

# Ensure the shared folder is accessible for importing the rules engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.rules_engine import evaluate_gaming_telemetry

app = FastAPI(title="Bottleneck Remove API")

def get_db():
    # Using local SQLite for development
    conn = sqlite3.connect("bottleneck.db")
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for performance
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

# --- Pydantic Models for incoming JSON ---
class TelemetryPayload(BaseModel):
    task: str
    hardware: dict
    telemetry: dict

# --- API Endpoints ---
@app.get("/api/v1/catalog/candidates")
def get_candidates(component: str, max_tdp: int = 500):
    """Client utility calls this to get lightweight upgrade options."""
    conn = get_db()
    if component == "gpu":
        # Example query enforcing a power supply limit
        gpus = conn.execute(
            "SELECT model, perf_score_gaming, tdp_watts FROM gpus WHERE tdp_watts <= ? ORDER BY perf_score_gaming DESC LIMIT 3", 
            (max_tdp,)
        ).fetchall()
        return [dict(row) for row in gpus]
    return {"error": "Component not supported yet"}

@app.post("/api/v1/reports")
def submit_report(payload: TelemetryPayload):
    """Client utility posts the final diagnosis here to generate a web link."""
    conn = get_db()
    report_id = str(uuid.uuid4())[:8] # Short UUID for easy sharing
    
    # Run the diagnosis through the shared engine
    diagnosis = evaluate_gaming_telemetry(payload.telemetry)
    
    conn.execute(
        "INSERT INTO reports (report_id, system_summary, telemetry, diagnosis) VALUES (?, ?, ?, ?)",
        (report_id, json.dumps(payload.hardware), json.dumps(payload.telemetry), json.dumps(diagnosis))
    )
    conn.commit()
    
    return {"report_url": f"http://localhost:8000/report/{report_id}"}