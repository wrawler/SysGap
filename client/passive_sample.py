"""Optional short passive readings; never creates or stresses a workload."""

from __future__ import annotations

import statistics
import time
from typing import Any

import psutil


def _gpu_readings(notes: list[str]) -> list[dict[str, Any]]:
    try:
        import pynvml
    except ImportError:
        notes.append("NVIDIA sample unavailable: install optional pynvml package.")
        return []

    initialized = False
    try:
        pynvml.nvmlInit()
        initialized = True
        readings = []
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            entry: dict[str, Any] = {"device_index": index, "name": str(name)}
            try:
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                entry["gpu_utilization_percent"] = int(utilization.gpu)
                entry["memory_controller_utilization_percent"] = int(utilization.memory)
            except Exception:
                entry["gpu_utilization_percent"] = None
            try:
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                entry["dedicated_memory_total_gib"] = round(memory.total / 1024**3, 2)
                entry["dedicated_memory_used_gib"] = round(memory.used / 1024**3, 2)
            except Exception:
                entry["dedicated_memory_total_gib"] = None
                entry["dedicated_memory_used_gib"] = None
            readings.append(entry)
        return readings
    except Exception as error:
        notes.append(f"NVIDIA sample unavailable ({type(error).__name__}).")
        return []
    finally:
        if initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


def collect_passive_sample(duration_seconds: int) -> dict[str, Any]:
    """Sample ordinary system activity for a bounded interval, without a test load."""
    if not 1 <= duration_seconds <= 30:
        raise ValueError("Passive sample duration must be between 1 and 30 seconds.")

    notes: list[str] = []
    cpu_samples: list[list[float]] = []
    disk_start = psutil.disk_io_counters()
    if disk_start is None:
        notes.append("Disk I/O counters are unavailable.")

    start = time.monotonic()
    while time.monotonic() - start < duration_seconds:
        remaining = duration_seconds - (time.monotonic() - start)
        interval = min(1.0, remaining)
        cpu_samples.append(psutil.cpu_percent(interval=interval, percpu=True))

    elapsed = max(time.monotonic() - start, 0.001)
    disk_end = psutil.disk_io_counters()
    disk_rates = None
    if disk_start is not None and disk_end is not None:
        disk_rates = {
            "read_bytes_per_second": round(max(0, disk_end.read_bytes - disk_start.read_bytes) / elapsed, 1),
            "write_bytes_per_second": round(max(0, disk_end.write_bytes - disk_start.write_bytes) / elapsed, 1),
        }

    columns = list(zip(*cpu_samples)) if cpu_samples else []
    cpu_summary = {
        "average_total_percent": round(
            statistics.mean(statistics.mean(sample) for sample in cpu_samples), 1
        ) if cpu_samples else None,
        "average_per_logical_processor_percent": [
            round(statistics.mean(column), 1) for column in columns
        ],
        "sample_count": len(cpu_samples),
    }
    try:
        memory = psutil.virtual_memory()
        memory_summary = {
            "used_percent": round(memory.percent, 1),
            "available_gib": round(memory.available / 1024**3, 2),
        }
    except (OSError, RuntimeError) as error:
        memory_summary = None
        notes.append(f"Memory sample unavailable ({type(error).__name__}).")

    return {
        "kind": "passive_ambient_snapshot",
        "duration_seconds": round(elapsed, 2),
        "cpu": cpu_summary,
        "memory": memory_summary,
        "disk_io": disk_rates,
        "nvidia_gpus": _gpu_readings(notes),
        "collection_notes": notes,
        "interpretation": (
            "This is a short observation of whatever the PC was doing during collection. "
            "No workload was started. It is not representative proof of application performance "
            "or a diagnosis unless the relevant workload happened to be running."
        ),
    }
