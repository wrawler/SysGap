import json
import unittest
from unittest.mock import patch

from catalog_client import (
    DECIMAL_GB_PER_GIB,
    DEFAULT_API_BASE_URL,
    QUERY_FIELDS,
    build_catalog_query,
    query_catalog,
    select_remote_candidates,
)


def report(form_factor="desktop", purpose=None, **requirements):
    return {
        "hardware": {
            "computer": {"form_factor": form_factor},
            "cpu": {"physical_cores": 4},
            "gpus": [],
            "memory": {"summary": {}},
            "storage": {"volumes": []},
        },
        "questionnaire": {
            "context": {},
            "purpose": purpose,
            "user_supplied_requirements": requirements,
        },
    }


class CatalogClientTests(unittest.TestCase):
    def test_cpu_query_uses_only_user_supplied_fields_and_expected_filter_paths(self):
        query, notes = build_catalog_query(
            report(min_cpu_cores=6, min_cpu_base_clock_ghz=3.2),
            "cpu",
        )
        self.assertEqual(query["component"], "cpu")
        self.assertEqual(
            query["filters"],
            [
                {"field": "cores.total", "min": 6},
                {"field": "clocks.performance.base", "min": 3.2},
            ],
        )
        self.assertEqual(query["sort"], {"field": "cores.total", "direction": "asc"})
        self.assertEqual(query["limit"], 100)
        self.assertEqual(query["fields"], QUERY_FIELDS["cpu"])
        self.assertTrue(notes)

    def test_missing_threshold_does_not_query_or_invent_one(self):
        self.assertIsNone(build_catalog_query(report(), "gpu"))
        self.assertIsNone(build_catalog_query(report(), "cpu"))
        self.assertIsNone(build_catalog_query(report(min_free_storage_gib=20), "motherboard"))

    def test_non_integer_cpu_core_floor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive whole number"):
            build_catalog_query(report(min_cpu_cores=6.5), "cpu")

    def test_invalid_gpu_requirement_is_reported(self):
        with self.assertRaisesRegex(ValueError, "min_vram_gib"):
            build_catalog_query(report(min_vram_gib="unknown"), "gpu")

    def test_storage_shortlist_carries_free_space_vs_capacity_caveat(self):
        query, notes = build_catalog_query(
            report(min_free_storage_gib=500),
            "storage",
        )
        self.assertAlmostEqual(
            query["filters"][0]["min"],
            500 * DECIMAL_GB_PER_GIB,
        )
        self.assertTrue(any("lower-bound" in note for note in notes))

    def test_gpu_and_ram_gib_floors_convert_to_decimal_catalog_gb(self):
        gpu_query, _ = build_catalog_query(report(min_vram_gib=8), "gpu")
        ram_query, _ = build_catalog_query(report(min_ram_gib=16), "ram")
        self.assertAlmostEqual(gpu_query["filters"][0]["min"], 8 * DECIMAL_GB_PER_GIB)
        self.assertAlmostEqual(ram_query["filters"][0]["min"], 16 * DECIMAL_GB_PER_GIB)
        self.assertEqual(gpu_query["sort"], {"field": "memory", "direction": "asc"})
        self.assertEqual(ram_query["sort"], {"field": "capacity", "direction": "asc"})

    def test_blank_numeric_answers_use_selected_profile_floors(self):
        gaming = report(
            purpose="gaming",
            min_cpu_cores=None,
            min_cpu_base_clock_ghz=None,
            min_vram_gib=None,
            min_ram_gib=None,
            min_free_storage_gib=None,
        )
        cpu_query, _ = build_catalog_query(gaming, "cpu")
        gpu_query, _ = build_catalog_query(gaming, "gpu")
        ram_query, _ = build_catalog_query(gaming, "ram")
        storage_query, _ = build_catalog_query(gaming, "storage")
        self.assertEqual(cpu_query["filters"], [{"field": "cores.total", "min": 6}])
        self.assertEqual(gpu_query["filters"][0]["min"], 8 * DECIMAL_GB_PER_GIB)
        self.assertEqual(ram_query["filters"][0]["min"], 16 * DECIMAL_GB_PER_GIB)
        self.assertEqual(storage_query["filters"][0]["min"], 100 * DECIMAL_GB_PER_GIB)

    @patch("catalog_client.urllib.request.build_opener")
    def test_posts_query_and_validates_catalog_response(self, build_opener):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                return json.dumps({
                    "component": "CPU",
                    "offset": 0,
                    "limit": 100,
                    "total": 1,
                    "items": [{
                        "opendb_id": "cpu-id",
                        "metadata": {"name": "Example CPU", "manufacturer": "Example"},
                        "cores": {"total": 8},
                    }],
                }).encode("utf-8")

        build_opener.return_value.open.return_value = Response()
        query = build_catalog_query(
            report(min_cpu_cores=6),
            "cpu",
        )[0]
        response = query_catalog(DEFAULT_API_BASE_URL, query)
        self.assertEqual(response["total"], 1)
        request = build_opener.return_value.open.call_args.args[0]
        self.assertEqual(
            request.full_url,
            f"{DEFAULT_API_BASE_URL}/api/v1/catalog/query",
        )
        self.assertEqual(json.loads(request.data), query)

    @patch("catalog_client.query_catalog")
    def test_transforms_remote_items_without_claiming_compatibility_or_performance(self, query):
        query.return_value = {
            "total": 1,
            "items": [{
                "opendb_id": "cpu-id",
                "metadata": {"name": "Example CPU", "manufacturer": "Example"},
                "cores": {"total": 8},
                "clocks": {"performance": {"base": 3.6}},
            }],
        }
        result = select_remote_candidates(
            report(min_cpu_cores=6),
            "cpu",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(result["candidates"][0]["candidate_id"], "cpu-id")
        self.assertEqual(result["candidates"][0]["compatibility_status"], "unknown")
        self.assertFalse(result["performance_ranking"])
        self.assertEqual(result["candidates"][0]["match_status"], "meets_effective_floors")
        self.assertIn("relative workload performance is unknown", result["candidates"][0]["why_shown"])

    @patch("catalog_client.query_catalog")
    def test_laptop_catalog_matches_include_service_manual_caveat(self, query):
        query.return_value = {
            "total": 1,
            "items": [{
                "opendb_id": "ram-id",
                "metadata": {"name": "Example 16GB RAM kit", "manufacturer": "Example"},
                "capacity": 17.179869184,
            }],
        }
        device = report(form_factor="laptop", min_ram_gib=16)
        device["hardware"]["memory"]["summary"]["total_gib"] = 8
        result = select_remote_candidates(
            device,
            "ram",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["status"], "candidates_found")
        self.assertTrue(any("exact laptop service manual" in note for note in result["notes"]))
        self.assertEqual(result["candidates"][0]["compatibility_status"], "unknown")
        self.assertAlmostEqual(result["candidates"][0]["capacity_value_gib"], 16)
        query.assert_called_once()

    @patch("catalog_client.query_catalog")
    def test_unknown_form_factor_can_query_but_is_caveated(self, query):
        query.return_value = {"total": 0, "items": []}
        device = report(form_factor="unknown", min_vram_gib=8)
        device["hardware"]["gpus"] = [
            {"name": "GPU A", "dedicated_memory_gib": 4},
        ]
        result = select_remote_candidates(
            device,
            "gpu",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["status"], "no_catalog_match")
        self.assertTrue(any("form factor is unknown" in note for note in result["notes"]))
        query.assert_called_once()

    @patch("catalog_client.query_catalog")
    def test_unknown_installed_gpu_does_not_produce_upgrade_recommendation(self, query):
        device = report(purpose="gaming", min_vram_gib=None)
        device["hardware"]["gpus"] = [
            {"name": "NVIDIA GPU", "dedicated_memory_gib": None},
            {"name": "Intel Graphics", "dedicated_memory_gib": 2},
        ]
        result = select_remote_candidates(device, "gpu", DEFAULT_API_BASE_URL)
        self.assertEqual(result["status"], "comparison_unknown")
        self.assertEqual(result["candidates"], [])
        query.assert_not_called()

    def test_default_candidate_limit_is_two(self):
        from catalog_client import QUERY_LIMIT

        self.assertEqual(QUERY_LIMIT, 2)

    @patch("catalog_client.query_catalog")
    def test_candidates_are_filtered_then_locally_ordered_by_closest_supplied_floor(self, query):
        query.return_value = {
            "total": 3,
            "items": [
                {
                    "opendb_id": "cpu-more-cores",
                    "metadata": {"name": "More cores", "manufacturer": "Example"},
                    "cores": {"total": 8},
                    "clocks": {"performance": {"base": 3.3}},
                },
                {
                    "opendb_id": "cpu-close",
                    "metadata": {"name": "Closest floor match", "manufacturer": "Example"},
                    "cores": {"total": 6},
                    "clocks": {"performance": {"base": 3.4}},
                },
                {
                    "opendb_id": "cpu-below",
                    "metadata": {"name": "Below clock floor", "manufacturer": "Example"},
                    "cores": {"total": 8},
                    "clocks": {"performance": {"base": 3.1}},
                },
            ],
        }
        result = select_remote_candidates(
            report(min_cpu_cores=6, min_cpu_base_clock_ghz=3.2),
            "cpu",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(
            [candidate["candidate_id"] for candidate in result["candidates"]],
            ["cpu-close", "cpu-more-cores"],
        )
        self.assertEqual(result["match_count"], 3)
        self.assertIn("closest passing candidates", result["ranking_method"])
        self.assertTrue(all(
            candidate["match_status"] == "meets_effective_floors"
            for candidate in result["candidates"]
        ))

    @patch("catalog_client.query_catalog")
    def test_ram_floor_already_met_skips_upgrade_shortlist(self, query):
        device = report(min_ram_gib=16)
        device["hardware"]["memory"]["summary"]["total_gib"] = 32
        result = select_remote_candidates(
            device,
            "ram",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["status"], "requirement_already_met")
        self.assertEqual(result["installed_comparison"]["installed_value_gib"], 32)
        query.assert_not_called()

    @patch("catalog_client.query_catalog")
    def test_gpu_ambiguity_keeps_installed_comparison_unknown(self, query):
        query.return_value = {"total": 0, "items": []}
        device = report(min_vram_gib=8)
        device["hardware"]["gpus"] = [
            {"name": "GPU A", "dedicated_memory_gib": 4},
            {"name": "GPU B", "dedicated_memory_gib": 12},
        ]
        result = select_remote_candidates(device, "gpu", DEFAULT_API_BASE_URL)
        self.assertEqual(result["installed_comparison"]["status"], "comparison_unknown")
        self.assertTrue(any("workload" in note for note in result["notes"]))
        self.assertEqual(result["status"], "comparison_unknown")
        self.assertEqual(result["candidates"], [])
        query.assert_not_called()

    @patch("catalog_client.query_catalog")
    def test_catalog_pages_are_fetched_before_closest_options_are_selected(self, query):
        first = {
            "total": 2,
            "items": [{
                "opendb_id": "large",
                "metadata": {"name": "Large capacity", "manufacturer": "Example"},
                "memory": 16 * DECIMAL_GB_PER_GIB,
            }],
        }
        second = {
            "total": 2,
            "items": [{
                "opendb_id": "closest",
                "metadata": {"name": "Closest capacity", "manufacturer": "Example"},
                "memory": 8.1 * DECIMAL_GB_PER_GIB,
            }],
        }
        query.side_effect = [first, second]
        device = report(min_vram_gib=8)
        device["hardware"]["gpus"] = [
            {"name": "GPU A", "dedicated_memory_gib": 4},
        ]
        result = select_remote_candidates(
            device,
            "gpu",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["candidates"][0]["candidate_id"], "closest")
        self.assertEqual(query.call_count, 2)
        self.assertEqual(query.call_args_list[1].args[1]["offset"], 1)

    def test_invalid_catalog_response_shape_is_reported(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                return b'{"items":"not-a-list","total":0}'

        with patch("catalog_client.urllib.request.build_opener") as build_opener:
            build_opener.return_value.open.return_value = Response()
            with self.assertRaisesRegex(RuntimeError, "invalid query-result shape"):
                query_catalog(DEFAULT_API_BASE_URL, {"component": "gpu"})


if __name__ == "__main__":
    unittest.main()
