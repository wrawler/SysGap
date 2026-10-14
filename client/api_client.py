"""Explicit-consent report upload to a configured API endpoint."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


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


def upload_report(url: str, report: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    _validate_url(url)
    payload = {
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
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(1024 * 1024)
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
