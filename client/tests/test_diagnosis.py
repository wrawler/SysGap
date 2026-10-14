import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import diagnosis


class DiagnosisOrchestratorTests(unittest.TestCase):
    def test_runs_collection_then_score_based_comparison_and_upload_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            report_path = report_dir / "assessment_20260101_000000_abc12345.json"
            commands = []

            def run(command, cwd, check):
                commands.append(command)
                if command[1].endswith("collector.py"):
                    report_path.write_text("{}", encoding="utf-8")
                return SimpleNamespace(returncode=0)

            with (
                patch.object(diagnosis, "REPORT_DIR", report_dir),
                patch.object(diagnosis, "CLIENT_DIR", report_dir),
                patch("builtins.input", return_value="n"),
                patch("diagnosis.subprocess.run", side_effect=run),
            ):
                self.assertEqual(diagnosis.main(), 0)

            self.assertEqual(len(commands), 2)
            self.assertTrue(commands[0][1].endswith("collector.py"))
            self.assertTrue(commands[1][1].endswith("compare_and_submit.py"))
            self.assertEqual(commands[1][commands[1].index("--report") + 1], str(report_path.resolve()))
            self.assertEqual(
                commands[1][commands[1].index("--components") + 1:],
                ["cpu", "gpu", "ram", "storage", "--upload"],
            )
            self.assertFalse(report_path.exists())

    def test_keeps_intermediate_reports_when_comparison_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            report_path = report_dir / "assessment_20260101_000000_abc12345.json"
            report_path.write_text("{}", encoding="utf-8")
            report_path.with_suffix(".txt").write_text("summary", encoding="utf-8")

            def run(command, cwd, check):
                if command[1].endswith("collector.py"):
                    return SimpleNamespace(returncode=0)
                return SimpleNamespace(returncode=2)

            with (
                patch.object(diagnosis, "REPORT_DIR", report_dir),
                patch.object(diagnosis, "CLIENT_DIR", report_dir),
                patch("builtins.input", return_value="n"),
                patch("diagnosis.subprocess.run", side_effect=run),
                patch.object(diagnosis, "_created_assessment", return_value=report_path),
            ):
                self.assertEqual(diagnosis.main(), 2)

            self.assertTrue(report_path.exists())
            self.assertTrue(report_path.with_suffix(".txt").exists())

    def test_locates_only_newly_created_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            old_report = report_dir / "assessment_old.json"
            new_report = report_dir / "assessment_new.json"
            old_report.write_text("{}", encoding="utf-8")
            before = {old_report.resolve()}
            new_report.write_text("{}", encoding="utf-8")

            self.assertEqual(diagnosis._created_assessment(before, report_dir), new_report.resolve())


if __name__ == "__main__":
    unittest.main()
