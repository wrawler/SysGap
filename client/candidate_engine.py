"""Capacity-based candidate shortlisting from a local OpenDB JSON snapshot."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from profiles import PROFILES, resolve_requirements

CATALOG_DIRS = {
    "cpu": "CPU",
    "gpu": "GPU",
    "ram": "RAM",
    "storage": "Storage",
    "motherboard": "Motherboard",
}

GB_TO_GIB = 1_000_000_000 / (1024 ** 3)

CAPACITY_REQUIREMENTS = {
    "cpu": ("min_cpu_cores", "core_count"),
    "gpu": ("min_vram_gib", "memory"),
    "ram": ("min_ram_gib", "capacity"),
    "storage": ("min_free_storage_gib", "capacity"),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def _nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def _installed_capacity(
    report: dict[str, Any],
    component: str,
) -> tuple[float | None, str, str | None]:
    hardware = report.get("hardware") or {}
    if component == "ram":
        installed = _number(
            ((hardware.get("memory") or {}).get("summary") or {}).get("total_gib")
        )
        return installed, "known" if installed is not None else "unknown", None
    if component == "gpu":
        gpus = hardware.get("gpus") or []
        selected_name = (
            ((report.get("questionnaire") or {}).get("context") or {}).get(
                "gpu_used_by_workload"
            )
        )
        if selected_name:
            normalized = str(selected_name).casefold()
            matches = [
                gpu for gpu in gpus
                if isinstance(gpu, dict)
                and (
                    normalized in str(gpu.get("name") or "").casefold()
                    or str(gpu.get("name") or "").casefold() in normalized
                )
            ]
            selected = matches[0] if len(matches) == 1 else None
            ambiguous = len(matches) != 1
        else:
            selected = gpus[0] if len(gpus) == 1 and isinstance(gpus[0], dict) else None
            ambiguous = len(gpus) > 1
        if ambiguous:
            return None, "unknown", (
                "Installed GPU capacity is not compared because the adapter used by the workload is ambiguous."
            )
        installed = _number(selected.get("dedicated_memory_gib")) if selected else None
        return installed, "known" if installed is not None else "unknown", None
    if component == "storage":
        volumes = ((hardware.get("storage") or {}).get("volumes") or [])
        known_free = [
            _nonnegative_number(volume.get("free_gib_at_scan"))
            for volume in volumes if isinstance(volume, dict)
        ]
        known_free = [value for value in known_free if value is not None]
        if not known_free:
            return None, "unknown", None
        return max(known_free), "known", (
            "Available free space on any one detected volume is compared as a best case; target volume is unknown."
        )
    if component == "cpu":
        physical_cores = _number(
            ((hardware.get("cpu") or {}).get("physical_cores"))
        )
        return physical_cores, "known" if physical_cores is not None else "unknown", None
    return None, "unknown", None


def _manufacturer_url(record: dict[str, Any]) -> str | None:
    general = record.get("general_product_information")
    if not isinstance(general, dict):
        return None
    url = general.get("manufacturer_url")
    return url if isinstance(url, str) and url.startswith("https://") else None


def _gb_to_gib(value: Any) -> float | None:
    value_gb = _number(value)
    return value_gb * GB_TO_GIB if value_gb is not None else None


def _candidate(component: str, record: dict[str, Any]) -> dict[str, Any] | None:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        return None
    opendb_id = record.get("opendb_id")
    model = metadata.get("name")
    manufacturer = metadata.get("manufacturer")
    if not isinstance(opendb_id, str) or not isinstance(model, str):
        return None

    details: dict[str, Any]
    capacity: float | None = None
    if component == "cpu":
        cores = record.get("cores")
        clocks = record.get("clocks")
        performance_clocks = clocks.get("performance") if isinstance(clocks, dict) else {}
        specifications = record.get("specifications")
        details = {
            "socket": record.get("socket"),
            "core_count": cores.get("total") if isinstance(cores, dict) else None,
            "thread_count": cores.get("threads") if isinstance(cores, dict) else None,
            "base_clock_ghz": performance_clocks.get("base") if isinstance(performance_clocks, dict) else None,
            "boost_clock_ghz": performance_clocks.get("boost") if isinstance(performance_clocks, dict) else None,
            "tdp_watts": specifications.get("tdp") if isinstance(specifications, dict) else None,
        }
    elif component == "gpu":
        details = {
            "chipset": record.get("chipset"),
            "dedicated_memory_gib": _gb_to_gib(record.get("memory")),
            "catalog_memory_gb": record.get("memory"),
            "memory_type": record.get("memory_type"),
            "length_mm": record.get("length"),
            "tdp_watts": record.get("tdp"),
            "power_connectors": record.get("power_connectors"),
        }
        capacity = _gb_to_gib(record.get("memory"))
    elif component == "ram":
        modules = record.get("modules")
        details = {
            "capacity_gib": _gb_to_gib(record.get("capacity")),
            "catalog_capacity_gb": record.get("capacity"),
            "ram_type": record.get("ram_type"),
            "form_factor": record.get("form_factor"),
            "module_count": modules.get("quantity") if isinstance(modules, dict) else None,
            "speed_mhz": record.get("speed"),
        }
        capacity = _gb_to_gib(record.get("capacity"))
    elif component == "storage":
        details = {
            "capacity_gib": _gb_to_gib(record.get("capacity")),
            "catalog_capacity_gb": record.get("capacity"),
            "storage_type": record.get("storage_type") or record.get("type"),
            "form_factor": record.get("form_factor"),
            "interface": record.get("interface"),
            "nvme": record.get("nvme"),
        }
        capacity = _gb_to_gib(record.get("capacity"))
    else:
        memory = record.get("memory")
        details = {
            "socket": record.get("socket"),
            "form_factor": record.get("form_factor"),
            "chipset": record.get("chipset"),
            "ram_type": memory.get("ram_type") if isinstance(memory, dict) else None,
            "maximum_memory_gib": memory.get("max") if isinstance(memory, dict) else None,
            "memory_slots": memory.get("slots") if isinstance(memory, dict) else None,
        }

    return {
        "candidate_id": opendb_id,
        "component": component,
        "manufacturer": manufacturer if isinstance(manufacturer, str) else None,
        "model": model,
        "catalog_source": "BuildCores OpenDB local snapshot",
        "manufacturer_source_url": _manufacturer_url(record),
        "details": details,
        "_capacity": capacity,
    }


def _compatibility_notes(component: str) -> list[str]:
    common = [
        "This is a documented capacity shortlist, not a performance ranking.",
        "A compatible physical installation has not been established by this inventory.",
    ]
    if component == "gpu":
        return common + [
            "PSU capacity/connectors, case clearance, and motherboard slot availability are unknown.",
        ]
    if component == "ram":
        return common + [
            "Motherboard memory generation, form-factor support, free slots, and maximum capacity are unknown.",
            "The listed capacity is the kit capacity, not the system's guaranteed post-upgrade total.",
        ]
    if component == "storage":
        return common + [
            "Available motherboard drive slots, supported form factor/interface, and intended drive replacement/addition are unknown.",
        ]
    if component == "cpu":
        return common + [
            "CPU candidates are not ranked: this inventory lacks a verified motherboard socket/BIOS compatibility match and workload benchmark.",
        ]
    return common + [
        "Motherboard replacement candidates are not ranked: case fit and the rest of the platform compatibility are unknown.",
    ]


def _form_factor_notes(form_factor: Any) -> list[str]:
    if form_factor == "laptop":
        return [
            "This device is a laptop. Catalog results are specification matches only; laptop components are often soldered or model-specific, so do not treat a match as replaceable or compatible without checking the exact laptop service manual.",
        ]
    if form_factor != "desktop":
        return [
            "The device form factor is unknown. Catalog results are specification matches only; verify whether the part is replaceable and compatible with the exact system before considering an upgrade.",
        ]
    return []


def select_candidates(
    report: dict[str, Any],
    catalog_root: Path,
    component: str,
    limit: int = 2,
) -> dict[str, Any]:
    if component not in CATALOG_DIRS:
        raise ValueError(f"Unsupported component: {component}")
    if not 1 <= limit <= 2:
        raise ValueError("Candidate limit must be between 1 and 2.")

    hardware = report.get("hardware") or {}
    computer = hardware.get("computer") or {}
    form_factor = computer.get("form_factor")
    base = {
        "schema_version": 1,
        "component": component,
        "catalog_source": "BuildCores OpenDB local snapshot",
        "ranking_method": "not ranked",
        "performance_ranking": False,
        "candidates": [],
        "notes": _form_factor_notes(form_factor) + _compatibility_notes(component),
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
    requirement_mapping = CAPACITY_REQUIREMENTS.get(component)
    if requirement_mapping is None:
        base["status"] = "not_ranked"
        base["notes"].insert(0, "No structured minimum requirement exists for this component in v1.")
        return base

    requirement_key, _ = requirement_mapping
    minimum = _number(requirements.get(requirement_key))
    base_clock_floor = _number(requirements.get("min_cpu_base_clock_ghz")) if component == "cpu" else None
    if component == "cpu" and minimum is None and base_clock_floor is not None:
        base["status"] = "comparison_unknown"
        base["notes"].insert(
            0,
            "Installed performance-core base clock is not available in a comparable form; no CPU upgrade candidates are suggested from base clock alone.",
        )
        return base
    if minimum is None and base_clock_floor is None:
        base["status"] = "not_ranked"
        base["notes"].insert(
            0,
            f"No effective positive {requirement_key} floor is available; candidates are not ranked.",
        )
        return base

    base["ranking_method"] = (
        "closest candidate to all effective CPU floors; not a performance ranking"
        if component == "cpu"
        else "closest documented capacity at or above the selected floor; decimal GB converted to GiB; not a performance ranking"
    )
    if minimum is None:
        minimum = base_clock_floor
    installed, installed_status, comparison_note = _installed_capacity(report, component)
    base["installed_comparison"] = {
        "status": (
            "requirement_already_met" if installed_status == "known" and installed >= minimum
            else "requirement_gap" if installed_status == "known"
            else "comparison_unknown"
        ),
        "installed_value_gib": installed,
        "required_value_gib": minimum if component != "cpu" else None,
    }
    if comparison_note:
        base["notes"].append(comparison_note)
    if installed_status == "known" and component != "cpu" and installed >= minimum:
        base["status"] = "requirement_already_met"
        base["notes"].insert(
            0,
            f"Detected {component} capacity ({installed:g} GiB) already meets the effective floor ({minimum:g} GiB); no capacity-upgrade shortlist is suggested.",
        )
        return base
    if installed_status == "known" and component == "cpu" and minimum is not None and installed >= minimum:
        if base_clock_floor is None:
            base["status"] = "requirement_already_met"
            base["notes"].insert(
                0,
                f"Detected physical CPU core count ({installed:g}) already meets the selected floor ({minimum:g}); no core-count upgrade shortlist is suggested.",
            )
            return base
        base["status"] = "comparison_unknown"
        base["notes"].insert(
            0,
            "Detected physical core count meets its floor, but installed performance-core base clock cannot be compared; no CPU upgrade candidates are suggested.",
        )
        return base
    if installed_status != "known":
        base["status"] = "comparison_unknown"
        base["notes"].insert(
            0,
            "Installed component capacity could not be established; no upgrade candidates are suggested.",
        )
        return base
    directory = catalog_root / CATALOG_DIRS[component]
    if not directory.is_dir():
        raise FileNotFoundError(f"Catalog directory does not exist: {directory}")
    matches = []
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read catalog record {path}: {error}") from error
        if not isinstance(record, dict):
            continue
        candidate = _candidate(component, record)
        if candidate is None:
            continue
        if component == "cpu":
            values = []
            floors = []
            if requirements.get("min_cpu_cores") is not None:
                values.append(_number(candidate["details"].get("core_count")))
                floors.append(_number(requirements.get("min_cpu_cores")))
            if requirements.get("min_cpu_base_clock_ghz") is not None:
                values.append(_number(candidate["details"].get("base_clock_ghz")))
                floors.append(base_clock_floor)
            if not values or any(
                value is None or floor is None or value < floor
                for value, floor in zip(values, floors)
            ):
                continue
            candidate["match_status"] = "meets_effective_floors"
            candidate["closest_match_score"] = [
                (value - floor) / floor for value, floor in zip(values, floors)
            ]
            candidate["compatibility_status"] = "unknown"
            candidate["price_status"] = "unavailable"
            candidate["price"] = None
            candidate["comparison_to_installed"] = "relative_performance_unknown"
            candidate["why_shown"] = (
                "Meets the effective CPU core/base-clock floors; relative workload performance and motherboard/BIOS compatibility are unknown."
            )
            candidate["notes"] = [candidate["why_shown"]]
            matches.append(candidate)
            continue
        capacity = candidate.pop("_capacity")
        if capacity is None or capacity < minimum:
            continue
        candidate["capacity_value_gib"] = capacity
        candidate["capacity_requirement_gib"] = minimum
        candidate["capacity_fit"] = "meets_effective_minimum"
        candidate["capacity_requirement_source"] = requirement_sources.get(
            requirement_key,
            "not_set",
        )
        candidate["compatibility_status"] = "unknown"
        candidate["price_status"] = "unavailable"
        candidate["price"] = None
        if component == "storage":
            comparison = "not_comparable"
            why_shown = (
                "Meets the effective free-space floor by total catalog drive capacity; "
                "drive capacity and current free space are not directly comparable."
            )
        elif installed is None:
            comparison = "installed_comparison_unknown"
            why_shown = "Meets the effective capacity floor; installed capacity could not be established."
        elif capacity > installed:
            comparison = "higher_reported_capacity"
            why_shown = (
                f"Catalog capacity ({capacity:g} GiB) exceeds detected capacity "
                f"({installed:g} GiB); this is not a performance claim."
            )
            if component == "ram":
                why_shown += " Kit installation/replacement and resulting system total are unknown."
        else:
            comparison = "not_higher_capacity"
            why_shown = (
                f"Catalog capacity ({capacity:g} GiB) is not higher than detected capacity "
                f"({installed:g} GiB)."
            )
        candidate["comparison_to_installed"] = comparison
        candidate["why_shown"] = why_shown
        candidate["match_status"] = "meets_effective_floors"
        candidate["closest_match_score"] = [(capacity - minimum) / minimum]
        if component == "storage":
            candidate["notes"] = [
                "The catalog value is total drive capacity; installed free space is a separate point-in-time value and the target volume is unknown.",
            ]
        else:
            candidate["notes"] = [why_shown]
        matches.append(candidate)

    matches.sort(key=lambda item: (
        sum(item["closest_match_score"]),
        max(item["closest_match_score"], default=0),
        item["model"].casefold(),
        item["candidate_id"],
    ))
    base["status"] = "candidates_found" if matches else "no_capacity_match"
    if component != "cpu":
        base["effective_minimum_gib"] = minimum
        if requirement_sources.get(requirement_key) == "user_supplied":
            base["user_supplied_minimum_gib"] = minimum
    base["requirement_field"] = (
        "min_cpu_cores and/or min_cpu_base_clock_ghz"
        if component == "cpu"
        else requirement_key
    )
    base["requirement_source"] = requirement_sources.get(requirement_key, "not_set")
    base["candidates"] = matches[:limit]
    if not matches:
        base["notes"].insert(0, "No catalog item with a verified capacity meets the supplied minimum.")
    return base
