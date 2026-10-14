# server/backend/main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uuid
import os
from pathlib import Path
from typing import Any

from shared.rules_engine import evaluate_gaming_telemetry
from db.storage import create_report_store, utc_now
from db.catalog import CatalogQuery, CatalogService, normalize_component

app = FastAPI(title="PriceRig API", version="1.0.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv("PRICERIG_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "catalog.json"
CATALOG = CatalogService(CATALOG_PATH)
REPORT_STORE = create_report_store(ROOT / "runtime" / "reports")

class TelemetryPayload(BaseModel):
    task: str = Field(min_length=1, max_length=80)
    hardware: dict[str, Any]
    telemetry: dict[str, Any]


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness() -> dict[str, str]:
    try:
        CATALOG.metadata()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ready"}


@app.get("/api/v1/catalog")
def get_catalog_metadata() -> dict[str, Any]:
    try:
        return CATALOG.metadata()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/catalog/query")
def query_catalog(request: CatalogQuery) -> dict[str, Any]:
    try:
        return CATALOG.query(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/catalog/candidates")
def get_candidates(
    component: str,
    offset: int = Query(0, ge=0, le=1000),
    limit: int = Query(25, ge=1, le=100),
    max_tdp: int | None = Query(None, ge=0, le=2000),
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if max_tdp is not None:
        try:
            component_type = normalize_component(component)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if component_type not in {"CPU", "GPU"}:
            raise HTTPException(status_code=400, detail="max_tdp is supported for CPU and GPU queries")
        tdp_field = "specifications.tdp" if component_type == "CPU" else "tdp"
        filters.append({"field": tdp_field, "max": max_tdp})
    try:
        return CATALOG.query(CatalogQuery(component=component, filters=filters, offset=offset, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/catalog/{component}")
def get_component(
    component: str,
    offset: int = Query(0, ge=0, le=1000),
    limit: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    try:
        return CATALOG.query(CatalogQuery(component=component, offset=offset, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/reports")
def submit_report(payload: TelemetryPayload):
    """Store a diagnosis and return its stable lookup URL."""
    report_id = str(uuid.uuid4())[:8]
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