"""Query the SysGap catalog using only explicit, structured requirements."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from api_client import _NoRedirectHandler, _validate_url

DEFAULT_API_BASE_URL = (
    "https://sysgap-api.greenisland-25c48125.eastasia.azurecontainerapps.io"
)
QUERY_LIMIT = 5
DECIMAL_GB_PER_GIB = (1024 ** 3) / 1_000_000_000

QUERY_FIELDS = {
    "cpu": [
        "opendb_id",
        "metadata",
        "cores.total",
        "clocks.performance.base",
        "clocks.performance.boost",
        "socket",
        "specifications.tdp",
    ],
    "gpu": [
        "opendb_id",
        "metadata",
        "memory",
        "memory_type",
        "chipset",
        "tdp",
        "length",
        "interface",
    ],
    "ram": [
        "opendb_id",
        "metadata",
        "capacity",
        "modules.quantity",
        "modules.capacity_gb",
        "ram_type",
        "form_factor",
        "speed",
    ],
    "storage": [
        "opendb_id",
        "metadata",
        "capacity",
        "type",
        "storage_type",
        "form_factor",
        "interface",
        "nvme",
    ],
}


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _positive_integer(value: Any) -> int | None:
    number = _positive_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _requirement_floor(
    requirements: dict[str, Any],
    key: str,
    *,
    integer: bool = False,
) -> float | int | None:
    value = requirements.get(key)
    if value is None:
        return None
    number = _positive_integer(value) if integer else _positive_number(value)
    if number is None:
        expected = "a positive whole number" if integer else "a positive finite number"
        raise ValueError(f"Questionnaire field {key} must be {expected}.")
    return number


def build_catalog_query(
    report: dict[str, Any],
    component: str,
    limit: int = QUERY_LIMIT,
) -> tuple[dict[str, Any], list[str]] | None:
    """Return an API query and caveats, or None when there is no usable floor."""
    if not 1 <= limit <= 5:
        raise ValueError("Catalog query limit must be between 1 and 5.")
    questionnaire = report.get("questionnaire") or {}
    if not isinstance(questionnaire, dict):
        raise ValueError("Assessment questionnaire must be an object.")
    requirements = questionnaire.get("user_supplied_requirements") or {}
    if not isinstance(requirements, dict):
        raise ValueError("Assessment requirements must be an object.")
    if component == "cpu":
        cores = _requirement_floor(requirements, "min_cpu_cores", integer=True)
        base_clock = _requirement_floor(requirements, "min_cpu_base_clock_ghz")
        filters = []
        if cores is not None:
            filters.append({"field": "cores.total", "min": cores})
        if base_clock is not None:
            filters.append({"field": "clocks.performance.base", "min": base_clock})
        if not filters:
            return None
        sort = (
            {"field": "clocks.performance.base", "direction": "desc"}
            if base_clock is not None
            else {"field": "cores.total", "direction": "desc"}
        )
        notes = [
            "CPU filters match only the supplied core-count/base-clock floors; they do not establish workload performance or motherboard/BIOS compatibility."
        ]
    elif component == "gpu":
        minimum = _requirement_floor(requirements, "min_vram_gib")
        if minimum is None:
            return None
        filters = [{"field": "memory", "min": minimum}]
        sort = {"field": "memory", "direction": "asc"}
        notes = [
            "GPU catalog memory is matched to the supplied VRAM floor; benchmark performance, workload adapter selection, PSU, connectors, and case clearance are not verified."
        ]
    elif component == "ram":
        minimum = _requirement_floor(requirements, "min_ram_gib")
        if minimum is None:
            return None
        filters = [{"field": "capacity", "min": minimum}]
        sort = {"field": "capacity", "direction": "asc"}
        notes = [
            "RAM catalog kit capacity is matched to the supplied floor; motherboard generation, slot availability, maximum capacity, and compatibility are not verified."
        ]
    elif component == "storage":
        minimum = _requirement_floor(requirements, "min_free_storage_gib")
        if minimum is None:
            return None
        filters = [{
            "field": "capacity",
            "min": minimum * DECIMAL_GB_PER_GIB,
        }]
        sort = {"field": "capacity", "direction": "asc"}
        notes = [
            "The GiB workspace floor is converted to decimal GB for the catalog capacity query. Disk capacity is only a lower-bound shortlist; usable free space, target volume, form-factor/interface support, and whether a drive should be added or replaced are unknown."
        ]
    elif component == "motherboard":
        return None
    else:
        raise ValueError(f"Unsupported catalog component: {component}")

    return {
        "component": component,
        "filters": filters,
        "sort": sort,
        "fields": QUERY_FIELDS[component],
        "offset": 0,
        "limit": limit,
    }, notes


def query_catalog(
    api_base_url: str,
    query: dict[str, Any],
    timeout: float = 20.0,
) -> dict[str, Any]:
    """POST a bounded catalog query and validate the response envelope."""
    _validate_url(api_base_url)
    endpoint = urllib.parse.urljoin(
        api_base_url.rstrip("/") + "/",
        "api/v1/catalog/query",
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(query, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(1024 * 1024)
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Catalog API returned HTTP {response.status}.")
    except urllib.error.HTTPError as error:
        detail = error.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Catalog API rejected the query with HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the catalog API: {error.reason}") from error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Catalog API response was not valid JSON.") from error
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("items"), list)
        or isinstance(payload.get("total"), bool)
        or not isinstance(payload.get("total"), int)
        or not all(isinstance(item, dict) for item in payload["items"])
    ):
        raise RuntimeError("Catalog API response has an invalid query-result shape.")
    return payload


def select_remote_candidates(
    report: dict[str, Any],
    component: str,
    api_base_url: str,
    limit: int = QUERY_LIMIT,
) -> dict[str, Any]:
    plan = build_catalog_query(report, component, limit)
    base = {
        "schema_version": 1,
        "component": component,
        "catalog_source": "SysGap remote catalog API",
        "ranking_method": "no performance ranking; filtered by explicit user-supplied requirements",
        "performance_ranking": False,
        "candidates": [],
        "notes": [],
    }
    computer = ((report.get("hardware") or {}).get("computer") or {})
    form_factor = computer.get("form_factor")
    if form_factor == "laptop":
        base["notes"].append(
            "This device is a laptop. Catalog results are specification matches only; laptop components are often soldered or model-specific, so do not treat a match as replaceable or compatible without checking the exact laptop service manual."
        )
    elif form_factor != "desktop":
        base["notes"].append(
            "The device form factor is unknown. Catalog results are specification matches only; verify whether the part is replaceable and compatible with the exact system before considering an upgrade."
        )
    if plan is None:
        base["status"] = "not_ranked"
        base["notes"].append(
            "No structured positive minimum was supplied for this component; no catalog query was made."
        )
        return base

    query, notes = plan
    response = query_catalog(api_base_url, query)
    items = response["items"]
    candidates = []
    for item in items:
        metadata = item.get("metadata")
        candidate_id = item.get("opendb_id")
        if not isinstance(metadata, dict) or not isinstance(candidate_id, str):
            continue
        model = metadata.get("name")
        if not isinstance(model, str) or not model:
            continue
        candidates.append({
            "candidate_id": candidate_id,
            "component": component,
            "manufacturer": metadata.get("manufacturer"),
            "model": model,
            "catalog_source": "SysGap remote catalog API",
            "details": {
                key: value
                for key, value in item.items()
                if key not in {"opendb_id", "metadata"}
            },
            "catalog_record": item,
            "compatibility_status": "unknown",
            "performance_ranking": False,
        })
    base["status"] = "candidates_found" if candidates else "no_catalog_match"
    base["notes"].extend(notes)
    base["query"] = query
    base["match_count"] = response["total"]
    base["candidates"] = candidates
    if not candidates:
        base["notes"].append("The remote catalog returned no records matching these filters.")
    elif response["total"] > len(candidates):
        base["notes"].append(
            f"Showing {len(candidates)} of {response['total']} matches; the API limit is {limit}."
        )
    return base
