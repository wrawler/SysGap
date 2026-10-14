import unittest

from ui import concise_report


class UserInterfaceTests(unittest.TestCase):
    def test_concise_report_keeps_summary_without_inventory_dump(self):
        report = {
            "report_id": "abc",
            "questionnaire": {"purpose_label": "Gaming"},
            "assessment": {
                "overall_status": "potential_concern",
                "summary": "One capacity floor was not met.",
                "findings": [
                    {"title": "RAM is below the floor", "status": "potential_concern"}
                ],
            },
            "hardware": {"cpu": {"name": "Detailed CPU name"}},
        }

        rendered = concise_report(report)

        self.assertIn("One capacity floor was not met.", rendered)
        self.assertIn("RAM is below the floor: potential_concern", rendered)
        self.assertNotIn("Detailed CPU name", rendered)
        self.assertIn("complete technical inventory", rendered)


if __name__ == "__main__":
    unittest.main()
