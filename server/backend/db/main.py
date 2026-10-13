# server/backend/main.py
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
import uuid
from pathlib import Path
from typing import Any

from shared.rules_engine import evaluate_gaming_telemetry
from db.storage import create_report_store, utc_now
from db.catalog_pipeline import SUPPORTED_TYPES

app = FastAPI(title="PriceRig API", version="1.0.0")
ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "catalog.json"
REPORT_STORE = create_report_store(ROOT / "runtime" / "reports")

class TelemetryPayload(BaseModel):
    task: str = Field(min_length=1, max_length=80)
    hardware: dict[str, Any]
    telemetry: dict[str, Any]

def load_catalog() -> dict[str, list[dict[str, Any]]]:
    if not CATALOG_PATH.exists():
        raise RuntimeError("catalog artifact is missing; run the catalog pipeline before starting the API")
    import json
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness() -> dict[str, str]:
    load_catalog()
    return {"status": "ready"}


@app.get("/api/v1/catalog/candidates")
def get_candidates(
    component: str,
    offset: int = Query(0, ge=0, le=1000),
    limit: int = Query(25, ge=1, le=100),
    max_tdp: int | None = Query(None, ge=0, le=2000),
) -> dict[str, Any]:
    component_type = component.strip().lower()
    aliases = {"cpu": "CPU", "gpu": "GPU", "ram": "RAM", "motherboard": "Motherboard", "storage": "Storage"}
    if component_type not in aliases:
        raise HTTPException(status_code=400, detail=f"component must be one of {', '.join(SUPPORTED_TYPES)}")
    records = load_catalog()[aliases[component_type]]
    if max_tdp is not None:
        records = [
            record
            for record in records
            if int(
                record.get(
                    "tdp",
                    record.get("tdp_watts", record.get("specifications", {}).get("tdp", 0)),
                )
                or 0
            )
            <= max_tdp
        ]
    return {"component": aliases[component_type], "offset": offset, "limit": limit, "total": len(records), "items": records[offset:offset + limit]}

@app.post("/api/v1/reports")
def submit_report(payload: TelemetryPayload):
    """Store a diagnosis and return its stable lookup URL."""
    report_id = str(uuid.uuid4())[:8] # Short UUID for easy sharing
    diagnosis = evaluate_gaming_telemetry(payload.telemetry)
    report = {
        "report_id": report_id,
        "created_at": utc_now(),
        "task": payload.task,
        "hardware": payload.hardware,
        "telemetry": payload.telemetry,
        "diagnosis": diagnosis,
    }
    try:
        REPORT_STORE.save(report_id, report)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="report storage is unavailable") from exc
    return {"report_id": report_id, "report_url": f"/api/v1/reports/{report_id}"}


@app.get("/api/v1/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    if len(report_id) != 8 or not report_id.isalnum():
        raise HTTPException(status_code=400, detail="invalid report id")
    try:
        report = REPORT_STORE.get(report_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="report storage is unavailable") from exc
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report