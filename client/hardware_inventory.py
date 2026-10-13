"""Best-effort Windows hardware inventory with explicit unavailable values."""

from __future__ import annotations

import datetime as dt
import math
import os
import platform
from typing import Any

import psutil

GIB = 1024**3


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number) if number.is_integer() else number


def _gib(value: Any) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return round(number / GIB, 2)


def _query(connection: Any, method: str, notes: list[str]) -> list[Any]:
    try:
        return list(getattr(connection, method)())
    except Exception as error:
        notes.append(f"{method} inventory unavailable ({type(error).__name__}).")
        return []


def _windows_inventory(notes: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "computer": None,
        "cpu": None,
        "gpus": [],
        "memory_modules": [],
        "physical_disks": [],
        "motherboard": None,
        "bios": None,
    }
    if os.name != "nt":
        notes.append("Detailed hardware inventory currently supports Windows only.")
        return result
    try:
        import wmi
    except ImportError:
        notes.append("Install the optional 'wmi' package to collect detailed Windows hardware inventory.")
        return result

    try:
        connection = wmi.WMI()
    except Exception as error:
        notes.append(f"Windows Management Instrumentation unavailable ({type(error).__name__}).")
        return result

    cpu = next(iter(_query(connection, "Win32_Processor", notes)), None)
    if cpu is not None:
        result["cpu"] = {
            "name": _clean(getattr(cpu, "Name", None)),
            "manufacturer": _clean(getattr(cpu, "Manufacturer", None)),
            "physical_cores": _number(getattr(cpu, "NumberOfCores", None)),
            "logical_processors": _number(getattr(cpu, "NumberOfLogicalProcessors", None)),
            "max_clock_mhz": _number(getattr(cpu, "MaxClockSpeed", None)),
            "socket_designation": _clean(getattr(cpu, "SocketDesignation", None)),
        }

    for gpu in _query(connection, "Win32_VideoController", notes):
        result["gpus"].append({
            "name": _clean(getattr(gpu, "Name", None)),
            "manufacturer": _clean(getattr(gpu, "AdapterCompatibility", None)),
            "dedicated_memory_gib": _gib(getattr(gpu, "AdapterRAM", None)),
            "driver_version": _clean(getattr(gpu, "DriverVersion", None)),
            "status": _clean(getattr(gpu, "Status", None)),
        })

    for module in _query(connection, "Win32_PhysicalMemory", notes):
        result["memory_modules"].append({
            "capacity_gib": _gib(getattr(module, "Capacity", None)),
            "speed_mhz": _number(getattr(module, "ConfiguredClockSpeed", None))
                or _number(getattr(module, "Speed", None)),
            "manufacturer": _clean(getattr(module, "Manufacturer", None)),
            "part_number": _clean(getattr(module, "PartNumber", None)),
        })

    for disk in _query(connection, "Win32_DiskDrive", notes):
        result["physical_disks"].append({
            "model": _clean(getattr(disk, "Model", None)),
            "capacity_gib": _gib(getattr(disk, "Size", None)),
            "interface_type": _clean(getattr(disk, "InterfaceType", None)),
            "media_type": _clean(getattr(disk, "MediaType", None)),
            "status": _clean(getattr(disk, "Status", None)),
        })

    board = next(iter(_query(connection, "Win32_BaseBoard", notes)), None)
    if board is not None:
        result["motherboard"] = {
            "manufacturer": _clean(getattr(board, "Manufacturer", None)),
            "product": _clean(getattr(board, "Product", None)),
            "version": _clean(getattr(board, "Version", None)),
        }

    system = next(iter(_query(connection, "Win32_ComputerSystem", notes)), None)
    if system is not None:
        result["computer"] = {
            "manufacturer": _clean(getattr(system, "Manufacturer", None)),
            "model": _clean(getattr(system, "Model", None)),
            "total_memory_gib": _gib(getattr(system, "TotalPhysicalMemory", None)),
            "system_type": _clean(getattr(system, "SystemType", None)),
        }

    bios = next(iter(_query(connection, "Win32_BIOS", notes)), None)
    if bios is not None:
        result["bios"] = {
            "manufacturer": _clean(getattr(bios, "Manufacturer", None)),
            "version": _clean(getattr(bios, "SMBIOSBIOSVersion", None)),
        }
    return result


def collect_inventory() -> tuple[dict[str, Any], list[str]]:
    """Collect inventory only; this does not start a workload or stress test."""
    notes: list[str] = []
    windows = _windows_inventory(notes)

    try:
        memory = psutil.virtual_memory()
        memory_summary = {
            "total_gib": _gib(memory.total),
            "available_gib_at_scan_gib": _gib(memory.available),
            "used_percent_at_scan": _number(memory.percent),
            "note": "Available memory and usage are point-in-time values, not workload measurements.",
        }
    except (OSError, RuntimeError) as error:
        memory_summary = None
        notes.append(f"Current memory totals unavailable ({type(error).__name__}).")

    volumes = []
    try:
        for partition in psutil.disk_partitions(all=False):
            if os.name == "nt" and not (
                len(partition.mountpoint) >= 2 and partition.mountpoint[1] == ":"
            ):
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (OSError, PermissionError):
                continue
            volumes.append({
                "mountpoint": partition.mountpoint,
                "filesystem": partition.fstype or None,
                "total_gib": _gib(usage.total),
                "free_gib_at_scan": _gib(usage.free),
                "used_percent_at_scan": _number(usage.percent),
            })
    except (OSError, RuntimeError) as error:
        notes.append(f"Storage volumes unavailable ({type(error).__name__}).")

    if not windows["physical_disks"]:
        notes.append("Physical disk models/types were not detected; volume data alone cannot identify drive type.")
    if any(gpu["dedicated_memory_gib"] is None for gpu in windows["gpus"]):
        notes.append("Windows did not provide valid dedicated-memory data for every GPU; no value was inferred.")

    memory_modules = windows.pop("memory_modules", [])
    physical_disks = windows.pop("physical_disks", [])
    inventory = {
        "operating_system": {
            "name": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        **windows,
        "memory": {
            "summary": memory_summary,
            "modules": memory_modules,
        },
        "storage": {
            "physical_disks": physical_disks,
            "volumes": volumes,
        },
        "collected_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "collection_mode": "one-time inventory; no benchmark or stress test",
    }
    return inventory, notes
