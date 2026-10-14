import json
import unittest
from unittest.mock import patch

from api_client import _validate_url, upload_report


class ApiClientTests(unittest.TestCase):
    def test_rejects_plain_http_remote_endpoint(self):
        with self.assertRaises(ValueError):
            _validate_url("http://example.com/api/v1/reports")

    def test_allows_https_and_localhost_http(self):
        _validate_url("https://example.com/api/v1/reports")
        _validate_url("http://localhost:8000/api/v1/reports")

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            _validate_url("https://user:secret@example.com/api/v1/reports")

    @patch("api_client.urllib.request.build_opener")
    def test_default_upload_contains_only_minimized_telemetry(self, build_opener):
        class Response:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                return b'{"report_url":"https://example.com/report/abc"}'

        build_opener.return_value.open.return_value = Response()
        report = {
            "schema_version": 1,
            "questionnaire": {"purpose": "gaming"},
            "hardware": {
                "computer": {"model": "Sensitive model"},
                "cpu": {"name": "Sensitive CPU", "physical_cores": 8},
                "memory": {"summary": {"total_gib": 32}},
                "storage": {"volumes": [{"mountpoint": "/home", "free_gib_at_scan": 100}]},
            },
            "questionnaire": {
                "purpose": "gaming",
                "activity": "private text",
                "preset_id": "gaming_1080p_competitive",
                "effective_requirements": {"min_ram_gib": 16},
            },
            "assessment": {
                "overall_status": "unknown",
                "summary": "summary",
                "findings": [{"status": "unknown", "title": "RAM", "evidence": ["private"]}],
            },
            "recommendations": [{"component": "ram", "status": "not_ranked"}],
        }
        result = upload_report("https://example.com/api/v1/reports", report)
        self.assertEqual(result["report_url"], "https://example.com/report/abc")
        request = build_opener.return_value.open.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        posted = json.loads(request.data)
        self.assertEqual(posted["telemetry"]["recommendations"][0]["component"], "ram")
        self.assertEqual(posted["hardware"]["ram_total_gib"], 32)
        self.assertNotIn("computer", posted["hardware"])
        self.assertNotIn("activity", posted["telemetry"]["questionnaire"])
        self.assertNotIn("evidence", posted["telemetry"]["assessment"]["findings"][0])
        self.assertNotIn("ambient_sample", posted["telemetry"])
        self.assertNotIn("report_id", posted)
        self.assertNotIn("client_version", posted)
        self.assertNotIn("catalog_lookup_results", posted)

    @patch("api_client.urllib.request.build_opener")
    def test_advanced_upload_includes_detailed_report(self, build_opener):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                return b"{}"

        build_opener.return_value.open.return_value = Response()
        report = {
            "schema_version": 1,
            "questionnaire": {"purpose": "gaming", "activity": "private text"},
            "hardware": {"computer": {"model": "Detailed model"}},
            "assessment": {},
            "ambient_sample": {"duration_seconds": 10},
        }
        upload_report(
            "https://example.com/api/v1/reports",
            report,
            advanced_sharing=True,
        )
        posted = json.loads(build_opener.return_value.open.call_args.args[0].data)
        self.assertEqual(posted["hardware"]["computer"]["model"], "Detailed model")
        self.assertEqual(posted["telemetry"]["questionnaire"]["activity"], "private text")
        self.assertIn("ambient_sample", posted["telemetry"])

    @patch("api_client.urllib.request.build_opener")
    def test_resolves_relative_report_url_to_absolute_api_url(self, build_opener):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size):
                return b'{"report_url":"/api/v1/reports/abcd1234"}'

        build_opener.return_value.open.return_value = Response()
        result = upload_report(
            "https://api.example.test/api/v1/reports",
            {
                "schema_version": 1,
                "questionnaire": {"purpose": "gaming"},
                "hardware": {},
                "assessment": {},
            },
        )
        self.assertEqual(
            result["report_url"],
            "https://api.example.test/api/v1/reports/abcd1234",
        )

    def test_rejects_oversized_upload(self):
        report = {
            "schema_version": 1,
            "questionnaire": {"purpose": "gaming"},
            "hardware": {"details": "x" * (2 * 1024 * 1024)},
            "assessment": {},
        }
        with self.assertRaises(ValueError):
            upload_report(
                "https://example.com/api/v1/reports",
                report,
                advanced_sharing=True,
            )


if __name__ == "__main__":
    unittest.main()
