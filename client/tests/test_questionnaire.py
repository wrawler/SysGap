import unittest

from questionnaire import run_questionnaire


class QuestionnaireTests(unittest.TestCase):
    def test_collects_optional_structured_cpu_requirement_values(self):
        answers = iter([
            "4",  # General use
            "1",  # No current problem
            "",   # Activity
            "",   # Minimum RAM
            "",   # Minimum VRAM
            "6",  # Minimum CPU cores
            "3.2",  # Minimum CPU base clock
            "",   # Minimum free storage
            "",   # CPU requirement text
            "",   # Requirement source
        ])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["user_supplied_requirements"]["min_cpu_cores"], 6)
        self.assertEqual(result["user_supplied_requirements"]["min_cpu_base_clock_ghz"], 3.2)

    def test_rejects_fractional_cpu_core_count(self):
        answers = iter([
            "4", "1", "", "", "", "6.5", "6", "3.2", "", "", "",
        ])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["user_supplied_requirements"]["min_cpu_cores"], 6)


if __name__ == "__main__":
    unittest.main()
