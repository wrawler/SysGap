import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import compare_and_submit
from candidate_engine import GB_TO_GIB
from collector import _render


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
            "profile_comparison": {
                "profile_label": "Gaming baseline",
                "description": "Baseline profile description.",
                "metrics": [{
                    "label": "Installed RAM",
                    "observed": 8,
                    "target": 16,
                    "unit": "GiB",
                    "requirement_source": "purpose_profile",
                    "target_attainment_percent": 50,
                    "status": "below_floor",
                }],
                "component_scores": {
                    "ram": {
                        "score": 50,
                        "status": "below_floor",
                        "basis": "Installed RAM",
                        "limits": "Capacity only.",
                    },
                },
                "assumptions": ["Not an application-specific requirement."],
            },
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

    def test_selects_only_two_candidate_categories_with_largest_known_gaps(self):
        report = assessment()
        report["assessment"]["profile_comparison"]["component_scores"] = {
            "cpu": {"score": 75},
            "gpu": {"score": 40},
            "ram": {"score": 60},
            "storage": {"score": None},
        }
        recommendations = [
            {"component": "cpu", "candidates": [{"model": "CPU option"}]},
            {"component": "gpu", "candidates": [{"model": "GPU option"}]},
            {"component": "ram", "candidates": [{"model": "RAM option"}]},
            {"component": "storage", "candidates": [{"model": "Storage option"}]},
        ]

        selected, ranking = compare_and_submit._select_top_component_gaps(
            report, recommendations
        )

        self.assertEqual([item["component"] for item in selected], ["gpu", "ram"])
        self.assertEqual(
            [item["profile_floor_gap"] for item in ranking],
            [60.0, 40.0],
        )
        self.assertEqual([item["component"] for item in recommendations], [
            "cpu", "gpu", "ram", "storage"
        ])

    @patch("compare_and_submit.upload_report")
    @patch("compare_and_submit.select_remote_candidates")
    @patch("compare_and_submit._consent", return_value=True)
    def test_backend_receives_only_top_two_categories_but_local_report_keeps_all(
        self, _consent, select_remote, upload_report
    ):
        report = assessment()
        report["assessment"]["profile_comparison"]["component_scores"] = {
            "cpu": {"score": 70, "status": "below_floor", "basis": "CPU cores", "limits": "Cores only."},
            "gpu": {"score": 20, "status": "below_floor", "basis": "VRAM", "limits": "VRAM only."},
            "ram": {"score": 60, "status": "below_floor", "basis": "RAM", "limits": "Capacity only."},
            "storage": {"score": 40, "status": "below_floor", "basis": "Free space", "limits": "Space only."},
        }
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        self.report_bytes = self.report_path.read_bytes()

        def recommendation(_report, component, _url, _limit):
            return {
                "schema_version": 1,
                "component": component,
                "status": "candidates_found",
                "candidates": [{"component": component, "model": f"{component} option"}],
                "notes": [],
            }

        select_remote.side_effect = recommendation
        upload_report.return_value = {"report_url": "https://example.test/report"}
        with patch(
            "sys.argv",
            [
                "compare_and_submit.py",
                "--report",
                str(self.report_path),
                "--components",
                "cpu",
                "gpu",
                "ram",
                "storage",
                "--upload",
            ],
        ):
            self.assertEqual(compare_and_submit.main(), 0)

        local = json.loads(
            (self.root / "assessment_with_recommendations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["component"] for item in local["recommendations"]],
            ["gpu", "storage"],
        )
        self.assertEqual(
            [item["component"] for item in local["catalog_lookup_results"]],
            ["cpu", "gpu", "ram", "storage"],
        )
        self.assertEqual(
            [item["component"] for item in local["recommendation_selection"]["selected_components"]],
            ["gpu", "storage"],
        )
        local_text = (self.root / "assessment_with_recommendations.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("TOP COMPONENT GAPS SELECTED FOR BACKEND", local_text)
        self.assertIn("GPU: score 20.0/100; gap 80.0 points", local_text)
        self.assertNotIn("CPU: candidates_found", local_text)
        submitted = upload_report.call_args.args[1]
        self.assertEqual(
            [item["component"] for item in submitted["recommendations"]],
            ["gpu", "storage"],
        )
        self.assertNotIn("catalog_lookup_results", submitted)
        self.assertEqual(len(submitted["recommendations"]), 2)

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
            [item["component"] for item in merged["catalog_lookup_results"]],
            ["gpu", "ram"],
        )
        self.assertEqual(merged["recommendations"], [])
        text = (self.root / "assessment_with_recommendations.txt").read_text(encoding="utf-8")
        self.assertIn("TOP COMPONENT GAPS SELECTED FOR BACKEND", text)
        self.assertIn("PROFILE / REQUIREMENT FLOOR COMPARISON", text)
        self.assertIn("50.0% of floor", text)
        self.assertIn("RAM profile-fit score: 50.0/100", text)
        self.assertIn("None: no known below-floor component had passing catalog candidates.", text)
        self.assertNotIn("CANDIDATE SHORTLISTS", text)
        self.assertFalse((self.root / "assessment_with_recommendations.html").exists())

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

    def test_report_render_explains_installed_comparison_and_candidate_selection(self):
        report_data = assessment()
        report_data["recommendations"] = [{
            "component": "ram",
            "status": "candidates_found",
            "ranking_method": "closest to the supplied floor; not a performance ranking",
            "installed_comparison": {
                "status": "requirement_gap",
                "installed_value_gib": 16,
                "required_value_gib": 32,
            },
            "candidates": [{
                "manufacturer": "Example",
                "model": "32 GiB kit",
                "capacity_value_gib": 32,
                "compatibility_status": "unknown",
                "why_shown": "Meets the supplied floor; kit installation is unknown.",
                "details": {"capacity": 34.36},
                "candidate_id": "ram-id",
            }],
            "notes": [],
        }]
        rendered = _render(report_data)
        self.assertIn("Installed comparison: requirement_gap; detected 16 GiB; supplied floor 32 GiB", rendered)
        self.assertIn("Why shown: Meets the supplied floor; kit installation is unknown.", rendered)
        self.assertIn("Price/value: unavailable", rendered)


if __name__ == "__main__":
    unittest.main()
