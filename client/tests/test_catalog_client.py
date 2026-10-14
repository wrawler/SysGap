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


def report(form_factor="desktop", **requirements):
    return {
        "hardware": {"computer": {"form_factor": form_factor}},
        "questionnaire": {"user_supplied_requirements": requirements},
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
        self.assertEqual(query["sort"], {"field": "clocks.performance.base", "direction": "desc"})
        self.assertEqual(query["limit"], 5)
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
                    "limit": 5,
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

    @patch("catalog_client.query_catalog")
    def test_laptop_catalog_matches_include_service_manual_caveat(self, query):
        query.return_value = {
            "total": 1,
            "items": [{
                "opendb_id": "ram-id",
                "metadata": {"name": "Example 16GB RAM kit", "manufacturer": "Example"},
                "capacity": 16,
            }],
        }
        result = select_remote_candidates(
            report(form_factor="laptop", min_ram_gib=16),
            "ram",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["status"], "candidates_found")
        self.assertTrue(any("exact laptop service manual" in note for note in result["notes"]))
        self.assertEqual(result["candidates"][0]["compatibility_status"], "unknown")
        query.assert_called_once()

    @patch("catalog_client.query_catalog")
    def test_unknown_form_factor_can_query_but_is_caveated(self, query):
        query.return_value = {"total": 0, "items": []}
        result = select_remote_candidates(
            report(form_factor="unknown", min_vram_gib=8),
            "gpu",
            DEFAULT_API_BASE_URL,
        )
        self.assertEqual(result["status"], "no_catalog_match")
        self.assertTrue(any("form factor is unknown" in note for note in result["notes"]))
        query.assert_called_once()

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
