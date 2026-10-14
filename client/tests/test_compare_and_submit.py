import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import compare_and_submit
from candidate_engine import GB_TO_GIB


def assessment():
    return {
        "schema_version": 1,
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "questionnaire": {
            "purpose": "gaming",
            "purpose_label": "Gaming",
            "activity": None,
            "symptom_label": "No current problem",
        },
        "hardware": {
            "computer": {},
            "operating_system": {"name": "Windows", "release": "11", "architecture": "64-bit"},
            "cpu": {},
            "gpus": [],
            "memory": {"summary": {}, "modules": []},
            "storage": {"physical_disks": [], "volumes": []},
            "motherboard": {},
            "bios": {},
        },
        "assessment": {
            "overall_status": "insufficient_information",
            "summary": "No claim.",
            "findings": [],
            "assumptions": [],
            "collection_notes": [],
        },
    }


def candidate_file(component, digest):
    return {
        "schema_version": 1,
        "source_report_sha256": digest,
        "component": component,
        "status": "not_ranked",
        "ranking_method": "not ranked",
        "candidates": [],
        "notes": [],
        "performance_ranking": False,
    }


class CompareAndSubmitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.report_path = self.root / "assessment.json"
        self.report_bytes = json.dumps(assessment()).encode("utf-8")
        self.report_path.write_bytes(self.report_bytes)

    def tearDown(self):
        self.temp.cleanup()

    def write_candidate(self, component, digest=None):
        path = self.root / f"{component}.json"
        item = candidate_file(component, digest or hashlib.sha256(self.report_bytes).hexdigest())
        path.write_text(json.dumps(item), encoding="utf-8")
        return path

    def test_rejects_candidate_file_from_different_assessment(self):
        candidate_path = self.write_candidate("gpu", "wrong-hash")
        with patch(
            "sys.argv",
            ["compare_and_submit.py", "--report", str(self.report_path),
             "--recommendations", str(candidate_path)],
        ):
            with self.assertRaises(SystemExit):
                compare_and_submit.main()
        self.assertFalse((self.root / "assessment_with_recommendations.json").exists())

    def test_merges_multiple_component_files_and_renders_them(self):
        gpu_path = self.write_candidate("gpu")
        ram_path = self.write_candidate("ram")
        with patch(
            "sys.argv",
            ["compare_and_submit.py", "--report", str(self.report_path),
             "--recommendations", str(gpu_path), str(ram_path)],
        ):
            self.assertEqual(compare_and_submit.main(), 0)

        merged = json.loads(
            (self.root / "assessment_with_recommendations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["component"] for item in merged["recommendations"]],
            ["gpu", "ram"],
        )
        text = (self.root / "assessment_with_recommendations.txt").read_text(encoding="utf-8")
        self.assertIn("CANDIDATE SHORTLISTS", text)
        self.assertIn("GPU: not_ranked", text)
        self.assertIn("RAM: not_ranked", text)

    def test_selects_and_combines_in_one_command(self):
        report_data = assessment()
        report_data["hardware"]["computer"]["form_factor"] = "desktop"
        report_data["hardware"]["memory"]["summary"]["total_gib"] = 8
        report_data["questionnaire"]["user_supplied_requirements"] = {
            "min_ram_gib": 32,
            "min_vram_gib": None,
            "min_free_storage_gib": None,
        }
        self.report_path.write_text(json.dumps(report_data), encoding="utf-8")
        self.report_bytes = self.report_path.read_bytes()
        ram_catalog = self.root / "catalog" / "RAM"
        ram_catalog.mkdir(parents=True)
        (ram_catalog / "ram.json").write_text(json.dumps({
            "opendb_id": "ram-id",
            "metadata": {"name": "32 GB RAM kit", "manufacturer": "Example"},
            "capacity": 36,
            "ram_type": "DDR5",
            "form_factor": "288-pin DIMM",
            "modules": {"quantity": 2},
        }), encoding="utf-8")
        catalog_root = self.root / "catalog"
        with patch(
            "sys.argv",
            ["compare_and_submit.py", "--report", str(self.report_path),
             "--catalog-root", str(catalog_root), "--components", "ram"],
        ):
            self.assertEqual(compare_and_submit.main(), 0)

        merged = json.loads(
            (self.root / "assessment_with_recommendations.json").read_text(encoding="utf-8")
        )
        recommendation = merged["recommendations"][0]
        self.assertEqual(recommendation["component"], "ram")
        self.assertEqual(recommendation["candidates"][0]["candidate_id"], "ram-id")
        self.assertAlmostEqual(recommendation["candidates"][0]["capacity_value_gib"], 36 * GB_TO_GIB)

    @patch("compare_and_submit.select_remote_candidates")
    def test_default_command_uses_remote_catalog_for_all_supported_components(self, select_remote):
        select_remote.side_effect = lambda _report, component, _url, _limit: {
            "schema_version": 1,
            "component": component,
            "status": "not_ranked",
            "candidates": [],
            "notes": [],
        }
        with patch(
            "sys.argv",
            ["compare_and_submit.py", "--report", str(self.report_path)],
        ):
            self.assertEqual(compare_and_submit.main(), 0)

        self.assertEqual(
            [call.args[1] for call in select_remote.call_args_list],
            ["cpu", "gpu", "ram", "storage", "motherboard"],
        )


if __name__ == "__main__":
    unittest.main()
