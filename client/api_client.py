"""Explicit-consent report upload to a configured API endpoint."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    local_http = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.username or parsed.password:
        raise ValueError("Do not embed credentials in the API URL.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local_http):
        raise ValueError("API requests require HTTPS; HTTP is allowed only for localhost.")
    if not parsed.netloc or parsed.fragment:
        raise ValueError("API URL must be an absolute URL.")


def _minimal_upload_payload(report: dict[str, Any]) -> dict[str, Any]:
    hardware = report.get("hardware") or {}
    cpu = hardware.get("cpu") or {}
    memory = hardware.get("memory") or {}
    memory_summary = memory.get("summary") or {}
    gpus = hardware.get("gpus") or []
    storage = hardware.get("storage") or {}
    volumes = storage.get("volumes") or []
    questionnaire = report.get("questionnaire") or {}
    assessment = report.get("assessment") or {}
    findings = assessment.get("findings") or []
    return {
        "schema_version": report["schema_version"],
        "task": questionnaire.get("purpose"),
        "hardware": {
            "cpu_physical_cores": cpu.get("physical_cores"),
            "cpu_logical_processors": cpu.get("logical_processors"),
            "ram_total_gib": memory_summary.get("total_gib"),
            "gpu_count": len(gpus),
            "gpu_dedicated_memory_gib": [
                gpu.get("dedicated_memory_gib") for gpu in gpus
            ],
            "free_storage_gib": [
                volume.get("free_gib_at_scan") for volume in volumes
            ],
        },
        "telemetry": {
            "kind": "inventory_assessment",
            "questionnaire": {
                key: questionnaire.get(key)
                for key in (
                    "purpose",
                    "symptom",
                    "preset_id",
                    "preset_data_version",
                    "context",
                    "effective_requirements",
                    "requirement_sources",
                )
                if questionnaire.get(key) is not None
            },
            "assessment": {
                "overall_status": assessment.get("overall_status"),
                "summary": assessment.get("summary"),
                "findings": [
                    {
                        key: finding.get(key)
                        for key in ("status", "title", "area", "confidence", "next_step")
                        if finding.get(key) is not None
                    }
                    for finding in findings
                    if isinstance(finding, dict)
                ],
            },
            "recommendations": report.get("recommendations", []),
        },
    }


def _full_upload_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "task": report["questionnaire"]["purpose"],
        "hardware": report["hardware"],
        "telemetry": {
            "kind": "inventory_assessment",
            "questionnaire": report["questionnaire"],
            "assessment": report["assessment"],
            "ambient_sample": report.get("ambient_sample"),
            "recommendations": report.get("recommendations", []),
        },
    }


def upload_report(
    url: str,
    report: dict[str, Any],
    timeout: float = 8.0,
    *,
    advanced_sharing: bool = False,
) -> dict[str, Any]:
    _validate_url(url)
    payload = (
        _full_upload_payload(report)
        if advanced_sharing
        else _minimal_upload_payload(report)
    )
    encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded_payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Report is too large to upload safely.")
    request = urllib.request.Request(
        url,
        data=encoded_payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise RuntimeError("API response is too large to process safely.")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"API returned HTTP {response.status}.")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"API rejected the report with HTTP {error.code}.") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the report API: {error.reason}") from error
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("API response was not valid JSON.") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("API response must be a JSON object.")
    report_url = decoded.get("report_url")
    if isinstance(report_url, str):
        decoded["report_url"] = urllib.parse.urljoin(url, report_url)
    return decoded
