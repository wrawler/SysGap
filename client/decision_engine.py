"""Evidence-bound rule evaluation for hardware suitability assessments."""

from __future__ import annotations

import math
from typing import Any

ENGINE_VERSION = "0.1.0"
STATUSES = {"meets", "potential_concern", "unknown", "not_assessed"}


def _finding(
    area: str,
    status: str,
    title: str,
    evidence: list[str],
    caveats: list[str],
    confidence: str,
    next_step: str,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"Unsupported finding status: {status}")
    return {
        "area": area,
        "status": status,
        "title": title,
        "evidence": evidence,
        "caveats": caveats,
        "confidence": confidence,
        "next_step": next_step,
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _positive_requirement(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def evaluate_assessment(
    questionnaire: dict[str, Any],
    inventory: dict[str, Any],
    collection_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Compare detectable inventory only with requirements supplied by the user.

    No generic CPU/GPU performance equivalency or invented workload threshold is
    applied. A passing capacity check is not a claim of adequate performance.
    """
    requirements = questionnaire.get("user_supplied_requirements") or {}
    findings: list[dict[str, Any]] = []

    memory = inventory.get("memory") or {}
    memory_summary = memory.get("summary") or {}
    installed_ram = _number(memory_summary.get("total_gib"))
    required_ram = _positive_requirement(requirements.get("min_ram_gib"))
    if required_ram is None:
        findings.append(_finding(
            "memory",
            "unknown",
            "Application memory requirement not provided",
            [f"Detected installed RAM: {installed_ram:g} GiB." if installed_ram is not None
             else "Installed RAM could not be detected."],
            ["Point-in-time available memory is not evidence of how much the application needs."],
            "low",
            "Check the application's official requirements if you want a capacity comparison.",
        ))
    elif installed_ram is None:
        findings.append(_finding(
            "memory", "unknown", "RAM comparison unavailable",
            [f"User supplied minimum: {required_ram:g} GiB; installed RAM was not detected."],
            ["The collector did not substitute an estimate."],
            "low", "Check the installed memory in Windows system settings.",
        ))
    elif installed_ram >= required_ram:
        findings.append(_finding(
            "memory", "meets", "Detected RAM meets the supplied minimum",
            [f"Detected {installed_ram:g} GiB; user-supplied minimum is {required_ram:g} GiB."],
            ["Meeting a minimum capacity does not establish smooth performance or rule out memory pressure."],
            "high for reported capacity comparison",
            "Compare with the application's recommended requirements for additional context.",
        ))
    else:
        findings.append(_finding(
            "memory", "potential_concern", "Detected RAM is below the supplied minimum",
            [f"Detected {installed_ram:g} GiB; user-supplied minimum is {required_ram:g} GiB."],
            ["This is a capacity mismatch, not proof that it caused the reported symptom."],
            "high for reported capacity comparison",
            "Verify the requirement against the application's official documentation.",
        ))

    gpus = inventory.get("gpus") or []
    gpu_used = (questionnaire.get("context") or {}).get("gpu_used_by_workload")
    usable_gpus = [
        gpu for gpu in gpus
        if _positive_requirement(gpu.get("dedicated_memory_gib")) is not None
    ]
    selected_gpu = None
    gpu_selection_ambiguous = False
    if gpu_used:
        normalized_name = str(gpu_used).casefold()
        matches = [
            gpu for gpu in usable_gpus
            if normalized_name in str(gpu.get("name") or "").casefold()
            or str(gpu.get("name") or "").casefold() in normalized_name
        ]
        if len(matches) == 1:
            selected_gpu = matches[0]
        else:
            gpu_selection_ambiguous = True
    elif len(usable_gpus) == 1:
        selected_gpu = usable_gpus[0]
    elif len(usable_gpus) > 1:
        gpu_selection_ambiguous = True

    available_vram = [
        value for value in (_positive_requirement(gpu.get("dedicated_memory_gib")) for gpu in gpus)
        if value is not None
    ]
    detected_vram = (
        _positive_requirement(selected_gpu.get("dedicated_memory_gib"))
        if selected_gpu else None
    )
    required_vram = _positive_requirement(requirements.get("min_vram_gib"))
    if required_vram is None:
        findings.append(_finding(
            "graphics_memory", "unknown", "Dedicated VRAM requirement not provided",
            [f"Detected dedicated VRAM values: {available_vram} GiB." if available_vram
             else "Dedicated VRAM was unavailable or not reported by the operating system."],
            ["Shared/system GPU memory is not treated as dedicated VRAM."],
            "low", "Check the workload's official GPU-memory requirement if one is published.",
        ))
    elif gpu_selection_ambiguous:
        selection_message = (
            f"User selected GPU: {gpu_used}; no unique matching adapter was detected."
            if gpu_used else "No unique GPU was selected for this workload."
        )
        findings.append(_finding(
            "graphics_memory", "unknown", "GPU used by the workload is ambiguous",
            [
                f"User supplied minimum: {required_vram:g} GiB.",
                f"Detected adapters with valid dedicated-memory readings: "
                f"{[gpu.get('name') for gpu in usable_gpus]}.",
                selection_message,
            ],
            ["The operating system inventory does not prove which adapter runs this application."],
            "low",
            "Select the adapter used by the workload or check it in the application's graphics settings.",
        ))
    elif detected_vram is None:
        findings.append(_finding(
            "graphics_memory", "unknown", "VRAM comparison unavailable",
            [f"User supplied minimum: {required_vram:g} GiB; dedicated VRAM could not be verified."],
            ["Invalid or unavailable OS readings are not inferred."],
            "low", "Check the GPU model and dedicated-memory specification.",
        ))
    elif detected_vram >= required_vram:
        findings.append(_finding(
            "graphics_memory", "meets", "Detected dedicated VRAM meets the supplied minimum",
            [f"Highest detected dedicated VRAM: {detected_vram:g} GiB; user-supplied minimum: {required_vram:g} GiB."],
            ["Capacity alone does not measure GPU speed or active VRAM pressure."],
            "high for reported capacity comparison",
            "Check the workload's recommended GPU requirements for additional context.",
        ))
    else:
        findings.append(_finding(
            "graphics_memory", "potential_concern", "Detected dedicated VRAM is below the supplied minimum",
            [f"Highest detected dedicated VRAM: {detected_vram:g} GiB; user-supplied minimum: {required_vram:g} GiB."],
            ["This does not establish runtime memory exhaustion or prove the cause of a symptom."],
            "high for reported capacity comparison",
            "Verify the requirement and confirm the selected GPU is the one used by the workload.",
        ))

    volumes = (inventory.get("storage") or {}).get("volumes") or []
    known_free = [
        _number(volume.get("free_gib_at_scan"))
        for volume in volumes
        if _number(volume.get("free_gib_at_scan")) is not None
    ]
    required_free = _positive_requirement(requirements.get("min_free_storage_gib"))
    if required_free is None:
        findings.append(_finding(
            "storage_capacity", "unknown", "Workspace storage requirement not provided",
            [f"Free space observed at scan: {known_free} GiB across detected volumes." if known_free
             else "Free space was not available."],
            ["Free space is a point-in-time capacity measure, not storage speed or I/O performance."],
            "low", "Provide the application's stated workspace requirement for a comparison.",
        ))
    elif not known_free:
        findings.append(_finding(
            "storage_capacity", "unknown", "Storage comparison unavailable",
            [f"User supplied minimum: {required_free:g} GiB; free space could not be read."],
            ["No storage value was inferred."],
            "low", "Check free space on the drive used for the application and project files.",
        ))
    elif max(known_free) >= required_free:
        findings.append(_finding(
            "storage_capacity", "meets", "At least one detected volume meets the supplied free-space minimum",
            [f"Maximum free space at scan: {max(known_free):g} GiB; user-supplied minimum: {required_free:g} GiB."],
            ["This does not verify that the application uses that volume."],
            "high for detected free-space comparison",
            "Confirm that the application and its workspace can use the volume with available space.",
        ))
    else:
        findings.append(_finding(
            "storage_capacity", "potential_concern", "No detected volume meets the supplied free-space minimum",
            [f"Maximum free space at scan: {max(known_free):g} GiB; user-supplied minimum: {required_free:g} GiB."],
            ["Free-space limits can change and this does not measure storage performance."],
            "high for detected free-space comparison",
            "Verify the requirement and check whether temporary/workspace files can use another drive.",
        ))

    cpu_requirement = requirements.get("cpu_requirement_text")
    cpu = inventory.get("cpu") or {}
    findings.append(_finding(
        "processor",
        "not_assessed" if cpu_requirement else "unknown",
        "CPU model detected; performance equivalency not evaluated",
        [
            f"Detected CPU: {cpu.get('name')}." if cpu.get("name") else "CPU model was not detected.",
            f"User supplied CPU requirement: {cpu_requirement}." if cpu_requirement else
            "No CPU requirement was supplied.",
        ],
        ["A text model name cannot be safely compared to another CPU without a curated compatibility/performance data source."],
        "low",
        "Compare the exact CPU requirement with the application's official documentation; do not infer equivalency from core count or clock alone.",
    ))

    symptom_label = questionnaire.get("symptom_label", "Not provided")
    findings.append(_finding(
        "reported_symptom",
        "unknown",
        "Reported symptom recorded; cause not diagnosed",
        [f"User reports: {symptom_label}."],
        ["No workload was observed. This report cannot attribute the symptom to a specific component."],
        "low",
        "For cause analysis, optionally collect passive metrics while the normal workload is running.",
    ))

    return {
        "engine_version": ENGINE_VERSION,
        "assessment_type": "hardware_suitability_from_detected_inventory_and_user_supplied_requirements",
        "overall_status": _overall_status(findings),
        "summary": (
            "This assessment compares detectable hardware capacities with requirements supplied by the user. "
            "It does not prove a live performance bottleneck."
        ),
        "findings": findings,
        "assumptions": [
            "User-entered requirements have not been independently verified.",
            "Inventory and volume readings are a point-in-time snapshot.",
            "No benchmark, stress test, or application workload was run.",
            "No synthetic telemetry or universal CPU/GPU score ratio was used.",
        ],
        "requirement_source_reference": requirements.get("source_reference"),
        "collection_notes": collection_notes or [],
    }


def _overall_status(findings: list[dict[str, Any]]) -> str:
    statuses = {finding["status"] for finding in findings}
    if "potential_concern" in statuses:
        return "potential_concern"
    if "meets" in statuses and statuses <= {"meets", "unknown", "not_assessed"}:
        return "no_supplied_capacity_floor_failed"
    return "insufficient_information"
