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
    def test_posts_schema_version_and_inventory_assessment(self, build_opener):
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
            "hardware": {"cpu": {"name": "Example"}},
            "assessment": {"overall_status": "unknown"},
            "ambient_sample": None,
        }
        result = upload_report("https://example.com/api/v1/reports", report)
        self.assertEqual(result["report_url"], "https://example.com/report/abc")
        request = build_opener.return_value.open.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")


if __name__ == "__main__":
    unittest.main()
