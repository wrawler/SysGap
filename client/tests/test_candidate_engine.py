import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from candidate_engine import select_candidates
from select_candidates import main as select_candidates_main


def report(
    *,
    form_factor="desktop",
    minimum=32,
    installed=16,
    component="ram",
    free=None,
    gpus=None,
    purpose=None,
    cpu_cores=4,
):
    return {
        "hardware": {
            "computer": {"form_factor": form_factor},
            "cpu": {"physical_cores": cpu_cores},
            "memory": {"summary": {"total_gib": installed}},
            "storage": {"volumes": [{"free_gib_at_scan": free}] if free is not None else []},
            "gpus": gpus or [],
        },
        "questionnaire": {
            "context": {},
            "purpose": purpose,
            "user_supplied_requirements": {
                "min_ram_gib": minimum if component == "ram" else None,
                "min_vram_gib": minimum if component == "gpu" else None,
                "min_free_storage_gib": minimum if component == "storage" else None,
                "min_cpu_cores": minimum if component == "cpu" else None,
                "min_cpu_base_clock_ghz": None,
            }
        },
    }


def ram_record(opendb_id, capacity, name):
    return {
        "opendb_id": opendb_id,
        "metadata": {"name": name, "manufacturer": "Example"},
        "capacity": capacity,
        "ram_type": "DDR5",
        "form_factor": "288-pin DIMM",
        "modules": {"quantity": 2},
    }


class CandidateEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = Path(self.temp.name)
        (self.catalog / "RAM").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_ram(self, record):
        (self.catalog / "RAM" / f"{record['opendb_id']}.json").write_text(
            json.dumps(record),
            encoding="utf-8",
        )

    def test_ranks_capacity_matches_by_smallest_excess_only(self):
        self.write_ram(ram_record("id-64", 64, "64 GB kit"))
        self.write_ram(ram_record("id-36", 36, "36 GB kit"))
        self.write_ram(ram_record("id-48", 48, "48 GB kit"))
        self.write_ram(ram_record("id-24", 24, "24 GB kit"))

        result = select_candidates(report(), self.catalog, "ram")

        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual([item["candidate_id"] for item in result["candidates"]],
                         ["id-36", "id-48"])
        self.assertAlmostEqual(result["candidates"][0]["capacity_value_gib"], 33.53, places=2)
        self.assertTrue(all(item["compatibility_status"] == "unknown"
                            for item in result["candidates"]))
        self.assertFalse(result["performance_ranking"])

    def test_decimal_gb_candidate_below_gib_minimum_is_excluded(self):
        self.write_ram(ram_record("id-32", 32, "32 GB kit"))
        result = select_candidates(report(), self.catalog, "ram")
        self.assertEqual(result["status"], "no_capacity_match")
        self.assertEqual(result["candidates"], [])

    def test_laptop_capacity_matches_are_returned_with_service_manual_caveat(self):
        self.write_ram(ram_record("id-48", 48, "48 GB kit"))
        result = select_candidates(report(form_factor="laptop"), self.catalog, "ram")
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(result["candidates"][0]["candidate_id"], "id-48")
        self.assertIn(
            "exact laptop service manual",
            result["notes"][0],
        )
        self.assertEqual(result["candidates"][0]["compatibility_status"], "unknown")

    def test_no_requirement_means_not_ranked(self):
        result = select_candidates(report(minimum=None), self.catalog, "ram")
        self.assertEqual(result["status"], "not_ranked")
        self.assertEqual(result["candidates"], [])

    def test_already_satisfied_ram_requirement_produces_no_upgrade(self):
        result = select_candidates(report(installed=64, minimum=32), self.catalog, "ram")
        self.assertEqual(result["status"], "requirement_already_met")
        self.assertEqual(result["candidates"], [])

    def test_storage_free_space_meeting_floor_skips_drive_shortlist(self):
        result = select_candidates(
            report(component="storage", minimum=32, free=64),
            self.catalog,
            "storage",
        )
        self.assertEqual(result["status"], "requirement_already_met")
        self.assertEqual(result["installed_comparison"]["installed_value_gib"], 64)
        self.assertEqual(result["candidates"], [])

    def test_ambiguous_gpu_does_not_suggest_an_upgrade(self):
        gpu_directory = self.catalog / "GPU"
        gpu_directory.mkdir()
        (gpu_directory / "candidate.json").write_text(json.dumps({
            "opendb_id": "gpu-candidate",
            "metadata": {"name": "Example GPU", "manufacturer": "Example"},
            "memory": 12_000_000_000,
        }), encoding="utf-8")
        result = select_candidates(
            report(
                component="gpu",
                minimum=8,
                gpus=[
                    {"name": "GPU A", "dedicated_memory_gib": 4},
                    {"name": "GPU B", "dedicated_memory_gib": 12},
                ],
            ),
            self.catalog,
            "gpu",
        )
        self.assertEqual(result["status"], "comparison_unknown")
        self.assertEqual(result["installed_comparison"]["status"], "comparison_unknown")
        self.assertEqual(result["candidates"], [])
        self.assertTrue(any("ambiguous" in note for note in result["notes"]))

    def test_cpu_is_not_ranked_without_a_structured_requirement(self):
        result = select_candidates(report(), self.catalog, "cpu")
        self.assertEqual(result["status"], "not_ranked")
        self.assertFalse(result["performance_ranking"])

    def test_cpu_shortlist_uses_blank_core_floor_from_profile(self):
        cpu_directory = self.catalog / "CPU"
        cpu_directory.mkdir()
        (cpu_directory / "cpu.json").write_text(json.dumps({
            "opendb_id": "cpu-candidate",
            "metadata": {"name": "Example 8-core CPU", "manufacturer": "Example"},
            "cores": {"total": 8, "threads": 16},
            "clocks": {"performance": {"base": 3.4, "boost": 4.5}},
        }), encoding="utf-8")
        profile_report = report(component="cpu", minimum=None, purpose="gaming")
        result = select_candidates(profile_report, self.catalog, "cpu")
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(result["requirement_source"], "purpose_profile")
        self.assertEqual(result["candidates"][0]["candidate_id"], "cpu-candidate")
        self.assertEqual(
            result["candidates"][0]["comparison_to_installed"],
            "relative_performance_unknown",
        )
        self.assertEqual(result["candidates"][0]["price_status"], "unavailable")

    def test_only_two_closest_passing_options_are_returned(self):
        for capacity in (36, 40, 48):
            self.write_ram(ram_record(f"id-{capacity}", capacity, f"{capacity}GB kit"))
        result = select_candidates(report(), self.catalog, "ram", limit=2)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(
            [candidate["candidate_id"] for candidate in result["candidates"]],
            ["id-36", "id-40"],
        )

    def test_cpu_profile_floor_already_met_does_not_suggest_upgrade(self):
        profile_report = report(
            component="cpu",
            minimum=None,
            purpose="gaming",
            cpu_cores=8,
        )
        result = select_candidates(profile_report, self.catalog, "cpu")
        self.assertEqual(result["status"], "requirement_already_met")
        self.assertEqual(result["candidates"], [])

    def test_cli_binds_candidate_file_to_exact_report_bytes(self):
        self.write_ram(ram_record("id-48", 48, "48 GB kit"))
        report_path = self.catalog / "assessment.json"
        report_bytes = json.dumps(report()).encode("utf-8")
        report_path.write_bytes(report_bytes)
        output_path = self.catalog / "candidates.json"

        with patch(
            "sys.argv",
            [
                "select_candidates.py",
                "--report", str(report_path),
                "--catalog-root", str(self.catalog),
                "--component", "ram",
                "--output", str(output_path),
            ],
        ):
            self.assertEqual(select_candidates_main(), 0)

        result = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(result["source_report_sha256"], hashlib.sha256(report_bytes).hexdigest())


if __name__ == "__main__":
    unittest.main()
