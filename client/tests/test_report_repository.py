import json
import tempfile
import unittest
from pathlib import Path

from report_repository import write_report


class ReportRepositoryTests(unittest.TestCase):
    def test_writes_json_and_text_using_report_id(self):
        report = {"report_id": "abc123", "schema_version": 1}
        with tempfile.TemporaryDirectory() as directory:
            json_path, text_path = write_report(
                report,
                Path(directory),
                lambda value: f"Report {value['report_id']}",
            )

            self.assertEqual(json_path.name, "assessment_abc123.json")
            self.assertEqual(text_path.name, "assessment_abc123.txt")
            self.assertEqual(json.loads(json_path.read_text())["report_id"], "abc123")
            self.assertEqual(text_path.read_text(), "Report abc123")

    def test_allows_explicit_stem_for_merged_reports(self):
        report = {"report_id": "abc123", "schema_version": 1}
        with tempfile.TemporaryDirectory() as directory:
            json_path, _ = write_report(
                report,
                Path(directory),
                lambda _value: "text",
                stem="assessment_abc123_with_recommendations",
            )

            self.assertEqual(
                json_path.name,
                "assessment_abc123_with_recommendations.json",
            )


if __name__ == "__main__":
    unittest.main()
