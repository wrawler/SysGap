"""Best-effort Windows hardware inventory with explicit unavailable values."""

from __future__ import annotations

import datetime as dt
import math
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psutil

from platform_provider import InventoryProvider

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


def _chassis_category(values: Any) -> str:
    try:
        codes = {int(value) for value in values}
    except (TypeError, ValueError):
        return "unknown"
    desktop_codes = {3, 4, 5, 6, 7, 13, 15, 16, 17, 23, 24}
    laptop_codes = {8, 9, 10, 11, 14, 30, 31, 32}
    is_desktop = bool(codes & desktop_codes)
    is_laptop = bool(codes & laptop_codes)
    if is_desktop == is_laptop:
        return "unknown"
    return "desktop" if is_desktop else "laptop"


class _WindowsInventoryProvider:
    name = "windows-wmi"

    def collect(self, notes: list[str]) -> dict[str, Any]:
        return _windows_inventory(notes)


class _CommonInventoryProvider:
    name = "common-psutil"

    def collect(self, notes: list[str]) -> dict[str, Any]:
        result = {
            "computer": None,
            "cpu": {
                "name": _clean(platform.processor()),
                "manufacturer": None,
                "physical_cores": _number(psutil.cpu_count(logical=False)),
                "logical_processors": _number(psutil.cpu_count(logical=True)),
                "max_clock_mhz": None,
                "socket_designation": None,
            },
            "gpus": [],
            "memory_modules": [],
            "physical_disks": [],
            "motherboard": None,
            "bios": None,
        }
        if not result["cpu"]["name"] and os.name != "nt":
            result["cpu"]["name"] = _linux_cpu_name()
        if not result["cpu"]["name"]:
            notes.append("CPU model name was not available from the common platform APIs.")
        if platform.system() == "Linux":
            result["gpus"] = _linux_gpu_names(notes)
        notes.append(
            "Detailed motherboard, BIOS, memory-module, physical-disk, and GPU-memory "
            "inventory is not available from the common provider."
        )
        return result


def _linux_cpu_name() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                _, _, value = line.partition(":")
                return _clean(value)
    except (OSError, UnicodeError):
        return None
    return None


def _linux_gpu_names(notes: list[str]) -> list[dict[str, Any]]:
    command = shutil.which("lspci")
    if not command:
        notes.append("Linux GPU names unavailable: lspci was not found.")
        return []
    try:
        completed = subprocess.run(
            [command, "-mm", "-nn"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        notes.append("Linux GPU names unavailable: lspci could not be queried.")
        return []
    if completed.returncode != 0:
        notes.append("Linux GPU names unavailable: lspci returned an error.")
        return []
    gpus = []
    for line in completed.stdout.splitlines():
        if not re.search(
            r'"(?:VGA compatible controller|3D controller|Display controller)\s*\[',
            line,
        ):
            continue
        fields = re.findall(r'"([^"]*)"', line)
        name = fields[2] if len(fields) >= 3 else None
        gpus.append({
            "name": _clean(name),
            "manufacturer": None,
            "dedicated_memory_gib": None,
            "driver_version": None,
            "status": None,
        })
    if not gpus:
        notes.append("Linux GPU names were not reported by lspci.")
    return gpus


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
        enclosure = next(iter(_query(connection, "Win32_SystemEnclosure", notes)), None)
        chassis_types = getattr(enclosure, "ChassisTypes", None) if enclosure is not None else None
        result["computer"] = {
            "manufacturer": _clean(getattr(system, "Manufacturer", None)),
            "model": _clean(getattr(system, "Model", None)),
            "total_memory_gib": _gib(getattr(system, "TotalPhysicalMemory", None)),
            "system_type": _clean(getattr(system, "SystemType", None)),
            "chassis_types": [_number(value) for value in chassis_types] if chassis_types else [],
            "form_factor": _chassis_category(chassis_types),
        }

    bios = next(iter(_query(connection, "Win32_BIOS", notes)), None)
    if bios is not None:
        result["bios"] = {
            "manufacturer": _clean(getattr(bios, "Manufacturer", None)),
            "version": _clean(getattr(bios, "SMBIOSBIOSVersion", None)),
        }
    return result


def _platform_provider() -> InventoryProvider:
    if os.name == "nt":
        return _WindowsInventoryProvider()
    return _CommonInventoryProvider()


def collect_inventory() -> tuple[dict[str, Any], list[str]]:
    """Collect inventory only; this does not start a workload or stress test."""
    notes: list[str] = []
    provider = _platform_provider()
    platform_inventory = provider.collect(notes)

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

    if not platform_inventory["physical_disks"]:
        notes.append("Physical disk models/types were not detected; volume data alone cannot identify drive type.")
    if any(gpu["dedicated_memory_gib"] is None for gpu in platform_inventory["gpus"]):
        notes.append("Dedicated GPU memory was unavailable for at least one adapter; no value was inferred.")

    memory_modules = platform_inventory.pop("memory_modules", [])
    physical_disks = platform_inventory.pop("physical_disks", [])
    inventory = {
        "operating_system": {
            "name": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        **platform_inventory,
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
        "collection_provider": provider.name,
        "collection_capabilities": {
            "platform_specific_hardware": provider.name != "common-psutil",
            "memory_totals": memory_summary is not None,
            "volume_capacity": bool(volumes),
        },
    }
    return inventory, notes
