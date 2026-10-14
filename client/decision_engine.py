"""Evidence-bound rule evaluation for hardware suitability assessments."""

from __future__ import annotations

import math
from typing import Any

from profiles import (
    METRIC_DEFINITIONS,
    PROFILE_SCORING_FEATURES,
    PROFILES,
    resolve_requirements,
)

ENGINE_VERSION = "0.1.0"
STATUSES = {"meets", "potential_concern", "unknown", "not_assessed"}
PRESET_RAM_HEADROOM = 0.05


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


def _positive_integer(value: Any) -> int | None:
    number = _positive_requirement(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _nonnegative(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _requirement_label(source: str) -> str:
    if source == "workload_preset":
        return "selected workload preset"
    return "selected purpose-profile floor" if source == "purpose_profile" else "user-supplied minimum"


def _ram_floor_meets(
    observed: float,
    target: float,
    source: str,
) -> bool:
    """Allow small OS/hardware-reserved RAM differences for heuristic floors."""
    if source == "user_supplied":
        return observed >= target
    return observed >= target * (1 - PRESET_RAM_HEADROOM)


def _profile_comparison(
    questionnaire: dict[str, Any],
    requirements: dict[str, Any],
    sources: dict[str, str],
    *,
    installed_ram: float | None,
    installed_vram: float | None,
    physical_cores: int | None,
    free_storage: float | None,
) -> dict[str, Any]:
    metrics = {
        "min_ram_gib": installed_ram,
        "min_vram_gib": installed_vram,
        "min_cpu_cores": float(physical_cores) if physical_cores is not None else None,
        "min_cpu_base_clock_ghz": None,
        "min_free_storage_gib": free_storage,
    }
    comparisons = []
    for key, (metric_id, label, unit) in METRIC_DEFINITIONS.items():
        target = _positive_requirement(requirements.get(key))
        if target is None:
            continue
        observed = metrics[key]
        if observed is None:
            attainment = None
            shortfall = None
            status = "unknown"
        else:
            attainment = min(observed / target * 100, 100)
            shortfall = max(100 - attainment, 0)
            meets_floor = (
                _ram_floor_meets(observed, target, sources.get(key, "not_set"))
                if key == "min_ram_gib"
                else observed >= target
            )
            attainment = 100 if meets_floor else attainment
            shortfall = 0 if meets_floor else shortfall
            status = "meets_floor" if meets_floor else "below_floor"
        comparisons.append({
            "metric": metric_id,
            "label": label,
            "observed": observed,
            "target": target,
            "unit": unit,
            "requirement_source": sources.get(key, "not_set"),
            "target_attainment_percent": round(attainment, 1) if attainment is not None else None,
            "target_shortfall_percent": round(shortfall, 1) if shortfall is not None else None,
            "status": status,
        })
    purpose = questionnaire.get("purpose")
    profile = PROFILES.get(purpose)
    scores = {}
    for component in ("cpu", "gpu", "ram", "storage"):
        component_metrics = [
            item for item in comparisons
            if item["metric"] == PROFILE_SCORING_FEATURES[component]["metric"]
        ]
        if component_metrics:
            metric = component_metrics[0]
            scores[component] = {
                "score": metric["target_attainment_percent"],
                "status": metric["status"],
                "basis": metric["label"],
                "target": metric["target"],
                "observed": metric["observed"],
                "unit": metric["unit"],
                "requirement_source": metric["requirement_source"],
                "limits": PROFILE_SCORING_FEATURES[component]["limits"],
            }
    return {
        "profile_id": purpose if profile else None,
        "profile_label": profile["label"] if profile else None,
        "description": profile["description"] if profile else None,
        "assumptions": profile["assumptions"] if profile else [],
        "method": "per-metric target attainment = observed capacity / selected floor, capped at 100%; not a performance score or bottleneck diagnosis",
        "metrics": comparisons,
        "component_scores": scores,
    }


def evaluate_assessment(
    questionnaire: dict[str, Any],
    inventory: dict[str, Any],
    collection_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Compare detectable inventory with explicit or purpose-profile floors.

    No generic CPU/GPU performance equivalency or invented workload threshold is
    applied. Profile floors are planning defaults, not official requirements.
    """
    requirements, requirement_sources = resolve_requirements(questionnaire)
    findings: list[dict[str, Any]] = []

    memory = inventory.get("memory") or {}
    memory_summary = memory.get("summary") or {}
    installed_ram = _number(memory_summary.get("total_gib"))
    required_ram = _positive_requirement(requirements.get("min_ram_gib"))
    ram_requirement_label = _requirement_label(requirement_sources["min_ram_gib"])
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
            [f"{ram_requirement_label.capitalize()}: {required_ram:g} GiB; installed RAM was not detected."],
            ["The collector did not substitute an estimate."],
            "low", "Check the installed memory in Windows system settings.",
        ))
    elif _ram_floor_meets(
        installed_ram,
        required_ram,
        requirement_sources["min_ram_gib"],
    ):
        allowance = (
            " This is within the 5% hardware-reserved-memory allowance for "
            "preset/profile planning floors."
            if installed_ram < required_ram
            else ""
        )
        findings.append(_finding(
            "memory", "meets", "Detected RAM meets the supplied minimum",
            [f"Detected {installed_ram:g} GiB; {ram_requirement_label} is {required_ram:g} GiB.{allowance}"],
            ["Meeting a minimum capacity does not establish smooth performance or rule out memory pressure."],
            "high for reported capacity comparison",
            "Compare with the application's recommended requirements for additional context.",
        ))
    else:
        findings.append(_finding(
            "memory", "potential_concern", "Detected RAM is below the supplied minimum",
            [f"Detected {installed_ram:g} GiB; {ram_requirement_label} is {required_ram:g} GiB."],
            ["This is a capacity mismatch, not proof that it caused the reported symptom."],
            "high for reported capacity comparison",
            "Verify the requirement against the application's official documentation.",
        ))

    gpus = inventory.get("gpus") or []
    gpu_used = (questionnaire.get("context") or {}).get("gpu_used_by_workload")
    usable_gpus = [gpu for gpu in gpus if _positive_requirement(gpu.get("dedicated_memory_gib")) is not None]
    selected_gpu = None
    gpu_selection_ambiguous = False
    if gpu_used:
        normalized_name = str(gpu_used).casefold()
        matches = [
            gpu for gpu in gpus
            if normalized_name in str(gpu.get("name") or "").casefold()
            or str(gpu.get("name") or "").casefold() in normalized_name
        ]
        if len(matches) == 1:
            selected_gpu = matches[0]
        else:
            gpu_selection_ambiguous = True
    elif len(usable_gpus) == 1:
        if len(gpus) == 1:
            selected_gpu = usable_gpus[0]
        else:
            gpu_selection_ambiguous = True
    elif len(gpus) > 1 or len(usable_gpus) > 1:
        gpu_selection_ambiguous = True

    available_vram = [
        {
            "adapter": gpu.get("name") or "Unknown GPU",
            "dedicated_vram_gib": _positive_requirement(gpu.get("dedicated_memory_gib")),
        }
        for gpu in gpus
        if _positive_requirement(gpu.get("dedicated_memory_gib")) is not None
    ]
    detected_vram = (
        _positive_requirement(selected_gpu.get("dedicated_memory_gib"))
        if selected_gpu else None
    )
    required_vram = _positive_requirement(requirements.get("min_vram_gib"))
    vram_requirement_label = _requirement_label(requirement_sources["min_vram_gib"])
    if required_vram is None:
        findings.append(_finding(
            "graphics_memory", "unknown", "Dedicated VRAM requirement not provided",
            [f"Detected dedicated VRAM by adapter: {available_vram}." if available_vram
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
                f"{vram_requirement_label.capitalize()}: {required_vram:g} GiB.",
                f"Detected adapters with valid dedicated-memory readings: "
                f"{[gpu.get('name') for gpu in usable_gpus]}.",
                selection_message,
            ],
            ["The operating system inventory does not prove which adapter runs this application."],
            "low",
            "Select the adapter used by the workload or check it in the application's graphics settings.",
        ))
    elif selected_gpu is None or detected_vram is None:
        findings.append(_finding(
            "graphics_memory", "unknown", "VRAM comparison unavailable",
            [f"{vram_requirement_label.capitalize()}: {required_vram:g} GiB; dedicated VRAM could not be verified."],
            ["Invalid or unavailable OS readings are not inferred."],
            "low", "Check the GPU model and dedicated-memory specification.",
        ))
    elif detected_vram >= required_vram:
        findings.append(_finding(
            "graphics_memory", "meets",             "Detected dedicated VRAM meets the selected floor",
            [f"Detected dedicated VRAM: {detected_vram:g} GiB; {vram_requirement_label} is {required_vram:g} GiB."],
            ["Capacity alone does not measure GPU speed or active VRAM pressure."],
            "high for reported capacity comparison",
            "Check the workload's recommended GPU requirements for additional context.",
        ))
    else:
        findings.append(_finding(
            "graphics_memory", "potential_concern",             "Detected dedicated VRAM is below the selected floor",
            [f"Detected dedicated VRAM: {detected_vram:g} GiB; {vram_requirement_label} is {required_vram:g} GiB."],
            ["This does not establish runtime memory exhaustion or prove the cause of a symptom."],
            "high for reported capacity comparison",
            "Verify the requirement and confirm the selected GPU is the one used by the workload.",
        ))

    volumes = (inventory.get("storage") or {}).get("volumes") or []
    known_free = [
        _nonnegative(volume.get("free_gib_at_scan"))
        for volume in volumes
        if _number(volume.get("free_gib_at_scan")) is not None
    ]
    required_free = _positive_requirement(requirements.get("min_free_storage_gib"))
    storage_requirement_label = _requirement_label(requirement_sources["min_free_storage_gib"])
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
            [f"{storage_requirement_label.capitalize()}: {required_free:g} GiB; free space could not be read."],
            ["No storage value was inferred."],
            "low", "Check free space on the drive used for the application and project files.",
        ))
    elif max(known_free) >= required_free:
        findings.append(_finding(
            "storage_capacity", "meets",             "At least one detected volume meets the selected free-space floor",
            [f"Maximum free space at scan: {max(known_free):g} GiB; {storage_requirement_label} is {required_free:g} GiB."],
            ["This does not verify that the application uses that volume."],
            "high for detected free-space comparison",
            "Confirm that the application and its workspace can use the volume with available space.",
        ))
    else:
        findings.append(_finding(
            "storage_capacity", "potential_concern",             "No detected volume meets the selected free-space floor",
            [f"Maximum free space at scan: {max(known_free):g} GiB; {storage_requirement_label} is {required_free:g} GiB."],
            ["Free-space limits can change and this does not measure storage performance."],
            "high for detected free-space comparison",
            "Verify the requirement and check whether temporary/workspace files can use another drive.",
        ))

    cpu = inventory.get("cpu") or {}
    required_cores = _positive_integer(requirements.get("min_cpu_cores"))
    cores_requirement_label = _requirement_label(requirement_sources["min_cpu_cores"])
    detected_cores = _positive_integer(cpu.get("physical_cores"))
    if required_cores is not None:
        if detected_cores is None:
            findings.append(_finding(
                "processor_cores", "unknown", "CPU core-count comparison unavailable",
                [f"{cores_requirement_label.capitalize()}: {required_cores} physical cores; installed physical core count was not detected."],
                ["Logical processor count is not substituted for physical core count."],
                "low", "Check the processor specifications and the application's official requirement.",
            ))
        elif detected_cores >= required_cores:
            findings.append(_finding(
                "processor_cores", "meets",                 "Detected physical core count meets the selected floor",
                [f"Detected {detected_cores} physical cores; {cores_requirement_label} is {required_cores}."],
                ["Core count alone does not establish CPU performance or application compatibility."],
                "high for reported core-count comparison",
                "Check the application's recommended processor requirement for additional context.",
            ))
        else:
            findings.append(_finding(
                "processor_cores", "potential_concern",                 "Detected physical core count is below the selected floor",
                [f"Detected {detected_cores} physical cores; {cores_requirement_label} is {required_cores}."],
                ["This is a core-count mismatch, not proof that it caused the reported symptom."],
                "high for reported core-count comparison",
                "Verify the requirement against the application's official documentation.",
            ))

    required_base_clock = _positive_requirement(requirements.get("min_cpu_base_clock_ghz"))
    base_clock_requirement_label = _requirement_label(
        requirement_sources["min_cpu_base_clock_ghz"]
    )
    if required_base_clock is not None:
        maximum_clock_mhz = _positive_requirement(cpu.get("max_clock_mhz"))
        evidence = [
            f"{base_clock_requirement_label.capitalize()} performance-core base clock: {required_base_clock:g} GHz."
        ]
        if maximum_clock_mhz is not None:
            evidence.append(
                f"Detected maximum clock: {maximum_clock_mhz:g} MHz; this is not a comparable base-clock measurement."
            )
        else:
            evidence.append("A comparable installed performance-core base clock was not detected.")
        findings.append(_finding(
            "processor_base_clock",
            "unknown",
            "CPU base-clock comparison unavailable",
            evidence,
            ["Maximum/boost clock and performance-core base clock are different measurements; no comparison was inferred."],
            "low",
            "Verify the exact processor model's base-clock specification and compare it with the supplied requirement.",
        ))

    cpu_requirement = requirements.get("cpu_requirement_text")
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

    known_free_for_profile = max(known_free) if known_free else None
    profile_comparison = _profile_comparison(
        questionnaire,
        requirements,
        requirement_sources,
        installed_ram=installed_ram,
        installed_vram=detected_vram,
        physical_cores=detected_cores,
        free_storage=known_free_for_profile,
    )
    return {
        "engine_version": ENGINE_VERSION,
        "assessment_type": "hardware_suitability_from_detected_inventory_and_explicit_or_profile_floors",
        "overall_status": _overall_status(findings),
        "summary": (
            "This assessment compares detected hardware with user-entered requirements or clearly labeled purpose-profile planning floors. "
            "A shortfall is a capacity/core-count gap; it does not prove a live performance bottleneck."
        ),
        "findings": findings,
        "profile_comparison": profile_comparison,
        "effective_requirements": requirements,
        "requirement_sources": requirement_sources,
        "assumptions": [
            "User-entered requirements and purpose-profile floors have not been independently validated for a specific application.",
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
