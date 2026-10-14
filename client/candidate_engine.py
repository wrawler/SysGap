"""Capacity-based candidate shortlisting from a local OpenDB JSON snapshot."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

CATALOG_DIRS = {
    "cpu": "CPU",
    "gpu": "GPU",
    "ram": "RAM",
    "storage": "Storage",
    "motherboard": "Motherboard",
}

GB_TO_GIB = 1_000_000_000 / (1024 ** 3)

CAPACITY_REQUIREMENTS = {
    "gpu": ("min_vram_gib", "memory"),
    "ram": ("min_ram_gib", "capacity"),
    "storage": ("min_free_storage_gib", "capacity"),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


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
    limit: int = 5,
) -> dict[str, Any]:
    if component not in CATALOG_DIRS:
        raise ValueError(f"Unsupported component: {component}")
    if not 1 <= limit <= 5:
        raise ValueError("Candidate limit must be between 1 and 5.")

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

    requirements = ((report.get("questionnaire") or {}).get("user_supplied_requirements") or {})
    requirement_mapping = CAPACITY_REQUIREMENTS.get(component)
    if requirement_mapping is None:
        base["status"] = "not_ranked"
        base["notes"].insert(0, "No structured minimum requirement exists for this component in v1.")
        return base

    requirement_key, _ = requirement_mapping
    minimum = _number(requirements.get(requirement_key))
    if minimum is None:
        base["status"] = "not_ranked"
        base["notes"].insert(
            0,
            f"No positive user-supplied {requirement_key} was provided; candidates are not ranked.",
        )
        return base

    base["ranking_method"] = (
        "closest documented capacity at or above user-supplied minimum; "
        "decimal GB converted to GiB; ties by model name then catalog ID"
    )
    inventory = report.get("hardware") or {}
    if component == "ram":
        installed = _number(((inventory.get("memory") or {}).get("summary") or {}).get("total_gib"))
        if installed is not None and installed >= minimum:
            base["status"] = "capacity_requirement_already_met"
            base["notes"].insert(
                0,
                f"Detected installed RAM ({installed:g} GiB) already meets the supplied minimum ({minimum:g} GiB); no capacity-based RAM upgrade is suggested.",
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
        capacity = candidate.pop("_capacity")
        if capacity is None or capacity < minimum:
            continue
        candidate["capacity_value_gib"] = capacity
        candidate["capacity_requirement_gib"] = minimum
        candidate["capacity_fit"] = "meets_user_supplied_minimum"
        candidate["compatibility_status"] = "unknown"
        if component == "storage":
            candidate["notes"] = [
                "The target workspace volume is unspecified; current free space on other volumes was not used to declare this requirement met or unmet.",
            ]
        else:
            candidate["notes"] = [
                "This capacity match is not verified to be an upgrade over the installed part.",
            ]
        matches.append(candidate)

    matches.sort(key=lambda item: (
        item["capacity_value_gib"] - minimum,
        item["model"].casefold(),
        item["candidate_id"],
    ))
    base["status"] = "candidates_found" if matches else "no_capacity_match"
    base["user_supplied_minimum_gib"] = minimum
    base["requirement_field"] = requirement_key
    base["candidates"] = matches[:limit]
    if not matches:
        base["notes"].insert(0, "No catalog item with a verified capacity meets the supplied minimum.")
    return base
