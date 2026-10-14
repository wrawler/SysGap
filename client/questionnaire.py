"""Purpose and symptom questionnaire; no diagnosis is inferred from answers alone."""

from __future__ import annotations

import math
from typing import Any, Callable

from profiles import PROFILES, resolve_requirements

PURPOSES = {
    "gaming": "Gaming",
    "video_editing": "Video editing",
    "rendering": "3D / CPU-GPU rendering",
    "local_ai": "Local AI / machine learning",
    "general": "Everyday / general use",
    "upgrade_planning": "Upgrade planning",
    "other": "Other",
}

SYMPTOMS = {
    "none": "No current problem; checking suitability or planning an upgrade",
    "slow_or_low_fps": "Low frame rate or generally slow performance",
    "stutter": "Stuttering, pauses, or freezing",
    "long_render": "Long export, render, or computation time",
    "memory_warning": "Memory/VRAM warning or out-of-memory error",
    "slow_loading": "Slow application/game loading or file transfers",
    "crash_or_shutdown": "Crash, restart, or unexpected shutdown",
    "other": "Other / not sure",
}


def _choose(prompt: str, options: dict[str, str], input_fn: Callable[[str], str]) -> str:
    keys = list(options)
    print(f"\n{prompt}")
    for index, key in enumerate(keys, start=1):
        print(f"  {index}. {options[key]}")
    while True:
        answer = input_fn("Select a number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return keys[int(answer) - 1]
        print(f"Enter a number from 1 to {len(keys)}.")


def _optional_text(prompt: str, input_fn: Callable[[str], str]) -> str | None:
    value = input_fn(prompt).strip()
    return value or None


def _optional_positive_number(
    prompt: str,
    input_fn: Callable[[str], str],
) -> float | None:
    while True:
        value = input_fn(prompt).strip()
        if not value:
            return None
        try:
            number = float(value)
        except ValueError:
            print("Enter a positive number or leave blank if unknown.")
            continue
        if math.isfinite(number) and number > 0:
            return number
        print("Enter a positive number or leave blank if unknown.")


def _optional_positive_integer(
    prompt: str,
    input_fn: Callable[[str], str],
) -> int | None:
    while True:
        value = input_fn(prompt).strip()
        if not value:
            return None
        if value.isdigit() and int(value) > 0:
            return int(value)
        print("Enter a positive whole number or leave blank if unknown.")


def run_questionnaire(input_fn: Callable[[str], str] = input) -> dict[str, Any]:
    purpose = _choose("What do you mainly want to use this PC for?", PURPOSES, input_fn)
    symptom = _choose("Which best describes your current situation?", SYMPTOMS, input_fn)
    activity = _optional_text(
        "Name the application, game, AI model, or workload if known (optional): ",
        input_fn,
    )

    context: dict[str, Any] = {}
    if purpose == "gaming":
        context["resolution"] = _optional_text(
            "Typical resolution (e.g. 1920x1080; optional): ", input_fn
        )
        context["target_fps"] = _optional_positive_number(
            "Desired frame rate in FPS, if relevant (optional): ", input_fn
        )
    elif purpose == "video_editing":
        context["footage_resolution"] = _optional_text(
            "Typical footage resolution (e.g. 4K; optional): ", input_fn
        )
        context["project_description"] = _optional_text(
            "Project/effect complexity (optional): ", input_fn
        )
    elif purpose == "rendering":
        context["renderer"] = _optional_text(
            "Renderer or application (optional): ", input_fn
        )
        context["render_mode"] = _optional_text(
            "CPU, GPU, or mixed rendering mode (optional): ", input_fn
        )
    elif purpose == "local_ai":
        context["model_or_workload"] = _optional_text(
            "Model or workload (optional): ", input_fn
        )
    if purpose in {"gaming", "video_editing", "local_ai"}:
        context["gpu_used_by_workload"] = _optional_text(
            "GPU used by this workload, if known (optional): ", input_fn
        )

    profile = PROFILES.get(purpose)
    if profile:
        print(f"\nSelected fallback: {profile['label']}")
        print(profile["description"])
        defaults = profile["requirements"]
        default_text = ", ".join(
            f"{name}={value}"
            for name, value in (
                ("RAM GiB", defaults["min_ram_gib"]),
                ("VRAM GiB", defaults["min_vram_gib"]),
                ("CPU physical cores", defaults["min_cpu_cores"]),
                ("free workspace GiB", defaults["min_free_storage_gib"]),
            )
            if value is not None
        )
        print(f"Blank numeric answers use these provisional planning floors: {default_text}.")
        print("They are not official requirements and do not predict performance.")

    print(
        "\nIf you have the application's official system requirements, enter the "
        "minimum values here. Your entries override the selected purpose profile. "
        "Blank entries use its labeled planning baseline when available; "
        "upgrade_planning/other have no default profile."
    )
    requirements = {
        "min_ram_gib": _optional_positive_number(
            "Minimum RAM required (GiB, optional): ", input_fn
        ),
        "min_vram_gib": _optional_positive_number(
            "Minimum dedicated VRAM required (GiB, optional): ", input_fn
        ),
        "min_cpu_cores": _optional_positive_integer(
            "Minimum CPU physical cores required by the workload (optional): ", input_fn
        ),
        "min_cpu_base_clock_ghz": _optional_positive_number(
            "Minimum CPU performance-core base clock (GHz, optional): ", input_fn
        ),
        "min_free_storage_gib": _optional_positive_number(
            "Minimum free workspace/storage required (GiB, optional): ", input_fn
        ),
        "cpu_requirement_text": _optional_text(
            "CPU requirement as published by the app (text only; optional): ", input_fn
        ),
        "source_reference": _optional_text(
            "Official requirement URL/document reference (optional): ", input_fn
        ),
    }
    response = {
        "purpose": purpose,
        "purpose_label": PURPOSES[purpose],
        "symptom": symptom,
        "symptom_label": SYMPTOMS[symptom],
        "activity": activity,
        "context": context,
        "user_supplied_requirements": requirements,
        "answers_are_self_reported": True,
    }
    effective, sources = resolve_requirements(response)
    response["effective_requirements"] = effective
    response["requirement_sources"] = sources
    response["profile_id"] = purpose if purpose in PROFILES else None
    return response
