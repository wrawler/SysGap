"""Query the SysGap catalog using only explicit, structured requirements."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from api_client import _NoRedirectHandler, _validate_url
from profiles import PROFILES, resolve_requirements

DEFAULT_API_BASE_URL = (
    "https://sysgap-api.greenisland-25c48125.eastasia.azurecontainerapps.io"
)
QUERY_LIMIT = 2
API_PAGE_SIZE = 100
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


def _nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


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


def _path_value(record: dict[str, Any], dotted_path: str) -> Any:
    value: Any = record
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _workload_gpu(report: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    inventory = report.get("hardware") or {}
    gpus = inventory.get("gpus") or []
    if not isinstance(gpus, list):
        return None, True
    named_gpu = ((report.get("questionnaire") or {}).get("context") or {}).get(
        "gpu_used_by_workload"
    )
    if named_gpu:
        normalized_name = str(named_gpu).casefold()
        matches = [
            gpu for gpu in gpus
            if isinstance(gpu, dict)
            and (
                normalized_name in str(gpu.get("name") or "").casefold()
                or str(gpu.get("name") or "").casefold() in normalized_name
            )
        ]
        return (matches[0], False) if len(matches) == 1 else (None, True)
    usable = [
        gpu for gpu in gpus
        if isinstance(gpu, dict) and _positive_number(gpu.get("dedicated_memory_gib")) is not None
    ]
    if len(gpus) == 1 and len(usable) == 1:
        return usable[0], False
    if len(gpus) > 1 or len(usable) > 1:
        return None, True
    return None, False


def _comparison_state(
    report: dict[str, Any],
    component: str,
    requirements: dict[str, Any],
) -> tuple[str, float | None, float | None, list[str]]:
    """Compare available installed capacity against effective profile/user floors."""
    notes: list[str] = []
    if component == "ram":
        required = _positive_number(requirements.get("min_ram_gib"))
        installed = _positive_number(
            (((report.get("hardware") or {}).get("memory") or {}).get("summary") or {}).get(
                "total_gib"
            )
        )
        return _capacity_state(installed, required), installed, required, notes
    if component == "gpu":
        required = _positive_number(requirements.get("min_vram_gib"))
        gpu, ambiguous = _workload_gpu(report)
        installed = (
            _positive_number(gpu.get("dedicated_memory_gib"))
            if gpu is not None else None
        )
        if ambiguous:
            notes.append(
                "Detected adapters do not identify one GPU used by the workload; installed VRAM comparison is unknown."
            )
            return "comparison_unknown", None, required, notes
        return _capacity_state(installed, required), installed, required, notes
    if component == "storage":
        required = _positive_number(requirements.get("min_free_storage_gib"))
        volumes = (((report.get("hardware") or {}).get("storage") or {}).get("volumes") or [])
        free_values = [
            _nonnegative_number(volume.get("free_gib_at_scan"))
            for volume in volumes if isinstance(volume, dict)
        ]
        known_free = [value for value in free_values if value is not None]
        if not known_free:
            return "comparison_unknown", None, required, notes
        installed_free = max(known_free)
        notes.append(
            "Available free space on any one detected volume is used as the best-case workspace comparison; the workload's target volume is unknown."
        )
        return _capacity_state(installed_free, required), installed_free, required, notes
    if component == "cpu":
        required_cores = _positive_integer(requirements.get("min_cpu_cores"))
        cpu = (report.get("hardware") or {}).get("cpu") or {}
        detected_cores = _positive_integer(cpu.get("physical_cores"))
        base_required = _positive_number(requirements.get("min_cpu_base_clock_ghz"))
        if required_cores is None and base_required is None:
            return "not_evaluated", None, None, notes
        if required_cores is not None and detected_cores is not None:
            if detected_cores < required_cores:
                notes.append(
                    f"Detected physical core count ({detected_cores}) is below the effective floor ({required_cores})."
                )
                if base_required is not None:
                    notes.append(
                        "Installed performance-core base clock remains unverified; the core-count gap does not establish overall CPU suitability."
                    )
                return "requirement_gap", float(detected_cores), float(required_cores), notes
        elif required_cores is not None:
            notes.append("Installed physical core count was not detected.")
            return "comparison_unknown", None, float(required_cores), notes
        if base_required is not None:
            maximum_clock_mhz = _positive_number(cpu.get("max_clock_mhz"))
            if maximum_clock_mhz is not None:
                notes.append(
                    f"Windows reported maximum clock {maximum_clock_mhz:g} MHz, which is not the catalog's performance-core base-clock metric."
                )
            else:
                notes.append(
                    "Installed performance-core base clock was not detected in a comparable form."
                )
            return "comparison_unknown", (
                float(detected_cores) if detected_cores is not None else None
            ), base_required, notes
        return "requirement_already_met", float(detected_cores), float(required_cores), notes
    return "not_evaluated", None, None, notes


def _capacity_state(installed: float | None, required: float | None) -> str:
    if required is None or installed is None:
        return "comparison_unknown"
    return "requirement_gap" if installed < required else "requirement_already_met"


def _catalog_items(
    api_base_url: str,
    query: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    first_page = query_catalog(api_base_url, query)
    items = list(first_page["items"])
    total = first_page["total"]
    if len(items) > total:
        raise RuntimeError("Catalog API returned more items than its reported total.")
    offset = len(items)
    while offset < total:
        if offset > 1000:
            raise RuntimeError("Catalog API result exceeds the supported pagination range.")
        page_query = {**query, "offset": offset}
        page = query_catalog(api_base_url, page_query)
        if page["total"] != total:
            raise RuntimeError("Catalog API result total changed while paging.")
        if not page["items"]:
            raise RuntimeError("Catalog API returned an empty page before the reported total.")
        items.extend(page["items"])
        offset += len(page["items"])
    return items, total


def _candidate_floor_values(
    item: dict[str, Any],
    component: str,
    requirements: dict[str, Any],
) -> tuple[list[float], list[float]] | None:
    if component == "cpu":
        floors = []
        values = []
        for key, path in (
            ("min_cpu_cores", "cores.total"),
            ("min_cpu_base_clock_ghz", "clocks.performance.base"),
        ):
            floor = _positive_number(requirements.get(key))
            if floor is None:
                continue
            value = _positive_number(_path_value(item, path))
            if value is None or value < floor:
                return None
            floors.append(floor)
            values.append(value)
        return (values, floors) if floors else None

    requirement_key, field = {
        "gpu": ("min_vram_gib", "memory"),
        "ram": ("min_ram_gib", "capacity"),
        "storage": ("min_free_storage_gib", "capacity"),
    }[component]
    floor_gib = _positive_number(requirements.get(requirement_key))
    catalog_gb = _positive_number(item.get(field))
    if floor_gib is None or catalog_gb is None:
        return None
    value_gib = catalog_gb / DECIMAL_GB_PER_GIB
    if value_gib + 1e-9 < floor_gib:
        return None
    return [value_gib], [floor_gib]


def _candidate_comparison(
    component: str,
    values: list[float],
    floors: list[float],
    installed: float | None,
) -> tuple[str, str]:
    if component == "cpu":
        return (
            "relative_performance_unknown",
            "Meets the effective CPU catalog floors; relative workload performance is unknown.",
        )
    if component == "storage":
        return (
            "not_comparable",
            "The catalog value is total drive capacity, while the device reading is free workspace space; these are not directly comparable.",
        )
    if installed is None:
        return (
            "installed_comparison_unknown",
            "Meets the effective capacity floor; installed component capacity could not be established.",
        )
    if values[0] > installed:
        label = "higher_reported_capacity"
        explanation = f"Catalog capacity ({values[0]:g} GiB) is higher than the detected capacity ({installed:g} GiB); this is not a performance claim."
        if component == "ram":
            explanation += " Kit installation/replacement and resulting system total are unknown."
        return label, explanation
    return (
        "not_higher_capacity",
        f"Catalog capacity ({values[0]:g} GiB) is not higher than the detected capacity ({installed:g} GiB).",
    )


def build_catalog_query(
    report: dict[str, Any],
    component: str,
    limit: int = QUERY_LIMIT,
) -> tuple[dict[str, Any], list[str]] | None:
    """Return an API query and caveats, or None when there is no usable floor."""
    if not 1 <= limit <= 2:
        raise ValueError("Catalog result limit must be between 1 and 2.")
    questionnaire = report.get("questionnaire") or {}
    if not isinstance(questionnaire, dict):
        raise ValueError("Assessment questionnaire must be an object.")
    requirements, _ = resolve_requirements(questionnaire)
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
        sort = {
            "field": "cores.total" if cores is not None else "clocks.performance.base",
            "direction": "asc",
        }
        notes = [
            "CPU filters match effective core-count/base-clock floors; they do not establish workload performance or motherboard/BIOS compatibility."
        ]
    elif component == "gpu":
        minimum = _requirement_floor(requirements, "min_vram_gib")
        if minimum is None:
            return None
        filters = [{"field": "memory", "min": minimum * DECIMAL_GB_PER_GIB}]
        sort = {"field": "memory", "direction": "asc"}
        notes = [
            "The effective GiB VRAM floor is converted to decimal GB for the catalog query. This matches capacity only; benchmark performance, PSU, connectors, and case clearance are not verified."
        ]
    elif component == "ram":
        minimum = _requirement_floor(requirements, "min_ram_gib")
        if minimum is None:
            return None
        filters = [{"field": "capacity", "min": minimum * DECIMAL_GB_PER_GIB}]
        sort = {"field": "capacity", "direction": "asc"}
        notes = [
            "The effective GiB RAM floor is converted to decimal GB for the catalog query. Kit capacity does not establish post-upgrade system total; motherboard generation, slot availability, maximum capacity, and compatibility are not verified."
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
            "The effective GiB workspace floor is converted to decimal GB for the catalog capacity query. Disk capacity is only a lower-bound shortlist; usable free space, target volume, form-factor/interface support, and whether a drive should be added or replaced are unknown."
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
        "limit": API_PAGE_SIZE,
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
        "ranking_method": "no performance ranking; filtered by explicitly supplied or purpose-profile floors",
        "performance_ranking": False,
        "candidates": [],
        "notes": [],
    }
    questionnaire = report.get("questionnaire") or {}
    requirements, requirement_sources = resolve_requirements(questionnaire)
    profile = PROFILES.get(questionnaire.get("purpose"))
    if profile:
        base["profile_id"] = questionnaire.get("purpose")
        base["profile_label"] = profile["label"]
        base["notes"].append(
            f"Blank numeric answers use the {profile['label']} planning profile where a floor is defined; explicit questionnaire values override it. Profile floors are heuristic defaults, not official workload requirements."
        )
    decision, installed, required, comparison_notes = _comparison_state(
        report,
        component,
        requirements,
    )
    base["installed_comparison"] = {
        "status": decision,
        "installed_value_gib": installed if component in {"gpu", "ram", "storage"} else None,
        "required_value_gib": required if component in {"gpu", "ram", "storage"} else None,
        "requirement_source": requirement_sources.get({
            "gpu": "min_vram_gib",
            "ram": "min_ram_gib",
            "storage": "min_free_storage_gib",
            "cpu": "min_cpu_cores",
        }.get(component, ""), "not_set"),
    }
    base["notes"].extend(comparison_notes)
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
            "No effective positive floor was supplied or defined by a purpose profile; no catalog query was made."
        )
        return base
    if decision == "requirement_already_met" and component in {"gpu", "ram", "storage", "cpu"}:
        base["status"] = "requirement_already_met"
        base["ranking_method"] = "no shortlist: detected comparable requirement already meets the effective floor"
        base["notes"].append(
            "No capacity-upgrade shortlist was queried because detected hardware already meets the effective comparable requirement."
        )
        return base
    if decision in {"comparison_unknown", "not_evaluated"}:
        base["status"] = decision
        base["notes"].append(
            "No upgrade candidates are suggested because the installed component could not be compared with a known profile/user floor."
        )
        return base

    query, notes = plan
    items, total = _catalog_items(api_base_url, query)
    candidates = []
    for item in items:
        metadata = item.get("metadata")
        candidate_id = item.get("opendb_id")
        if not isinstance(metadata, dict) or not isinstance(candidate_id, str):
            continue
        model = metadata.get("name")
        if not isinstance(model, str) or not model:
            continue
        floor_values = _candidate_floor_values(item, component, requirements)
        if floor_values is None:
            continue
        values, floors = floor_values
        capacity_gib = values[0] if component in {"gpu", "ram", "storage"} else None
        comparison, comparison_text = _candidate_comparison(
            component,
            values,
            floors,
            installed,
        )
        candidate = {
            "candidate_id": candidate_id,
            "component": component,
            "manufacturer": metadata.get("manufacturer"),
            "model": model,
            "catalog_source": "SysGap remote catalog API",
            "capacity_value_gib": capacity_gib,
            "match_status": "meets_effective_floors",
            "comparison_to_installed": comparison,
            "why_shown": comparison_text,
            "closest_match_score": [
                (value - floor) / floor for value, floor in zip(values, floors)
            ],
            "details": {
                key: value
                for key, value in item.items()
                if key not in {"opendb_id", "metadata"}
            },
            "catalog_record": item,
            "compatibility_status": "unknown",
            "performance_ranking": False,
            "price_status": "unavailable",
            "price": None,
        }
        candidates.append(candidate)
    candidates.sort(
        key=lambda candidate: (
            sum(candidate["closest_match_score"]),
            max(candidate["closest_match_score"], default=0),
            str(candidate["model"]).casefold(),
            candidate["candidate_id"],
        )
    )
    candidates = candidates[:limit]
    base["status"] = "candidates_found" if candidates else "no_catalog_match"
    base["notes"].extend(notes)
    base["query"] = query
    base["match_count"] = total
    base["candidates"] = candidates
    base["ranking_method"] = (
        "closest passing candidates by summed relative excess across effective floors; "
        "not a performance, price/value, or compatibility ranking"
    )
    if not candidates:
        base["notes"].append(
            "The remote catalog returned no usable records meeting all effective numeric floors."
        )
    elif total > len(candidates):
        base["notes"].append(
            f"Showing the {len(candidates)} closest floor matches of {total} API matches. "
            "Price/value and compatibility are unavailable; this ordering is not a performance ranking."
        )
    return base
