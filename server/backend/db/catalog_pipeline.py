"""Build a compact, specification-deduplicated hardware catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SUPPORTED_TYPES = ("CPU", "GPU", "RAM", "Motherboard", "Storage")
DEFAULT_TARGET = 200
MIN_TARGET = 150
MAX_TARGET = 200

_FIELDS = {
    "CPU": (
        "cores", "clocks", "cache", "specifications", "series",
        "microarchitecture", "coreFamily", "socket",
    ),
    "GPU": (
        "power_connectors", "video_outputs", "chipset_manufacturer",
        "chipset", "memory", "memory_type", "core_base_clock",
        "core_boost_clock", "effective_memory_clock", "memory_bus",
        "interface", "length", "tdp", "total_slot_width", "cooling",
    ),
    "RAM": (
        "modules", "speed", "ram_type", "form_factor", "capacity",
        "cas_latency", "voltage", "ecc", "registered", "heat_spreader",
        "rgb", "profile_support",
    ),
    "Motherboard": (
        "memory", "storage_devices", "usb_headers", "fan_headers",
        "rgb_headers", "power_connectors", "audio", "socket",
        "form_factor", "chipset", "pcie_slots", "m2_slots",
        "onboard_ethernet", "ecc_support", "raid_support",
        "wireless_networking",
    ),
    "Storage": (
        "capacity", "type", "form_factor", "interface", "nvme",
        "storage_type",
    ),
}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def specification(record: dict[str, Any], component_type: str) -> dict[str, Any]:
    """Return only fields that describe component capability, not provenance."""
    return {
        field: _canonical(record.get(field))
        for field in _FIELDS[component_type]
        if field in record
    }


def fingerprint(record: dict[str, Any], component_type: str) -> str:
    payload = json.dumps(
        specification(record, component_type),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rank(record: dict[str, Any], component_type: str) -> tuple[float, str]:
    """Prefer useful higher-capacity/performance records, then be deterministic."""
    if component_type == "CPU":
        value = float(record.get("cores", {}).get("total", 0))
        value *= float(record.get("clocks", {}).get("performance", {}).get("boost", 0))
    elif component_type == "GPU":
        value = float(record.get("memory", 0)) * float(record.get("core_boost_clock", 0))
    elif component_type == "RAM":
        value = float(record.get("capacity", 0)) * float(record.get("speed", 0))
    elif component_type == "Motherboard":
        value = float(record.get("memory", {}).get("max", 0))
    else:
        value = float(record.get("capacity", 0))
    return value, str(record.get("opendb_id", ""))


def build_catalog(source_root: Path, target: int = DEFAULT_TARGET) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if not MIN_TARGET <= target <= MAX_TARGET:
        raise ValueError(f"target must be between {MIN_TARGET} and {MAX_TARGET}")

    catalog: dict[str, list[dict[str, Any]]] = {}
    manifest: dict[str, Any] = {"target": target, "categories": {}}
    for component_type in SUPPORTED_TYPES:
        source_dir = source_root / component_type
        records: list[dict[str, Any]] = []
        for path in sorted(source_dir.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Unable to read {path}: {exc}") from exc
            if not isinstance(record, dict):
                continue
            records.append(record)

        representatives: dict[str, dict[str, Any]] = {}
        for record in records:
            key = fingerprint(record, component_type)
            current = representatives.get(key)
            if current is None or _rank(record, component_type) > _rank(current, component_type):
                representatives[key] = record
        selected = sorted(
            representatives.values(),
            key=lambda item: _rank(item, component_type),
            reverse=True,
        )[:target]
        catalog[component_type] = selected
        manifest["categories"][component_type] = {
            "source_count": len(records),
            "unique_specifications": len(representatives),
            "retained_count": len(selected),
            "duplicate_count": len(records) - len(representatives),
        }
    return catalog, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("open-db"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    args = parser.parse_args()

    catalog, manifest = build_catalog(args.source, args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
