"""Cached, validated query access to the generated hardware catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from db.catalog_pipeline import SUPPORTED_TYPES

ALIASES = {
    "cpu": "CPU",
    "gpu": "GPU",
    "ram": "RAM",
    "motherboard": "Motherboard",
    "storage": "Storage",
}

FILTER_FIELDS = {
    "CPU": {
        "cores.total", "cores.threads", "clocks.performance.base",
        "clocks.performance.boost", "specifications.tdp", "socket",
        "series", "microarchitecture",
    },
    "GPU": {
        "memory", "memory_type", "core_base_clock", "core_boost_clock",
        "effective_memory_clock", "length", "tdp", "total_slot_width",
        "chipset", "interface",
    },
    "RAM": {
        "modules.quantity", "modules.capacity_gb", "speed", "ram_type",
        "form_factor", "capacity", "cas_latency", "ecc", "registered",
    },
    "Motherboard": {
        "memory.max", "memory.ram_type", "memory.slots", "socket",
        "form_factor", "chipset", "ecc_support", "raid_support",
        "wireless_networking",
    },
    "Storage": {
        "capacity", "type", "form_factor", "interface", "nvme", "storage_type",
    },
}


class CatalogFilter(BaseModel):
    field: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.]+$")
    eq: Any | None = None
    min: float | None = None
    max: float | None = None
    in_: list[Any] | None = Field(default=None, alias="in", min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_one_operator(self) -> "CatalogFilter":
        if sum(value is not None for value in (self.eq, self.min, self.max, self.in_)) != 1:
            raise ValueError("a filter must specify exactly one of eq, min, max, or in")
        if self.min is not None and self.max is not None:
            raise ValueError("use separate filters for min and max")
        return self


class CatalogSort(BaseModel):
    field: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.]+$")
    direction: str = Field(default="asc", pattern=r"^(asc|desc)$")


class CatalogQuery(BaseModel):
    component: str = Field(min_length=1, max_length=30)
    filters: list[CatalogFilter] = Field(default_factory=list, max_length=20)
    sort: CatalogSort | None = None
    fields: list[str] | None = Field(default=None, max_length=30)
    offset: int = Field(default=0, ge=0, le=1000)
    limit: int = Field(default=25, ge=1, le=100)


def normalize_component(component: str) -> str:
    normalized = ALIASES.get(component.strip().lower())
    if normalized is None:
        raise ValueError(f"component must be one of: {', '.join(SUPPORTED_TYPES)}")
    return normalized


def _get_path(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _numeric(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"field '{field}' requires a numeric value")
    return float(value)


def _matches(record: dict[str, Any], item: CatalogFilter) -> bool:
    value = _get_path(record, item.field)
    if value is None:
        return False
    if item.eq is not None:
        return value == item.eq
    if item.in_ is not None:
        return value in item.in_
    number = _numeric(value, item.field)
    if item.min is not None:
        return number >= item.min
    if item.max is not None:
        return number <= item.max
    return False


def _project(record: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return record
    projected: dict[str, Any] = {}
    for field in fields:
        value = _get_path(record, field)
        if value is None:
            continue
        target = projected
        parts = field.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return projected


def _sort_key(record: dict[str, Any], field: str) -> tuple[bool, Any]:
    value = _get_path(record, field)
    if value is None:
        return True, ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return False, value
    return False, str(value)


class CatalogService:
    def __init__(self, path: Path) -> None:
        self.path = path

    @lru_cache(maxsize=1)
    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            raise RuntimeError("catalog artifact is missing; run the catalog pipeline before starting the API")
        try:
            catalog = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("catalog artifact is invalid") from exc
        if not isinstance(catalog, dict) or any(
            not isinstance(catalog.get(component), list) for component in SUPPORTED_TYPES
        ):
            raise RuntimeError("catalog artifact has an invalid shape")
        return catalog

    def metadata(self) -> dict[str, Any]:
        catalog = self._load()
        return {
            "components": {
                component: {"count": len(catalog[component]), "filter_fields": sorted(FILTER_FIELDS[component])}
                for component in SUPPORTED_TYPES
            }
        }

    def query(self, request: CatalogQuery) -> dict[str, Any]:
        component = normalize_component(request.component)
        allowed = FILTER_FIELDS[component]
        for item in request.filters:
            if item.field not in allowed:
                raise ValueError(f"field '{item.field}' is not queryable for {component}")
        if request.sort and request.sort.field not in allowed:
            raise ValueError(f"field '{request.sort.field}' is not queryable for {component}")
        if request.fields:
            invalid = set(request.fields) - allowed - {"opendb_id", "metadata"}
            if invalid:
                raise ValueError(f"fields are not queryable: {', '.join(sorted(invalid))}")

        records = self._load()[component]
        for item in request.filters:
            records = [record for record in records if _matches(record, item)]
        if request.sort:
            reverse = request.sort.direction == "desc"
            records = sorted(
                records,
                key=lambda record: _sort_key(record, request.sort.field),
                reverse=reverse,
            )
        total = len(records)
        items = [_project(record, request.fields) for record in records[request.offset:request.offset + request.limit]]
        return {
            "component": component,
            "offset": request.offset,
            "limit": request.limit,
            "total": total,
            "items": items,
        }
