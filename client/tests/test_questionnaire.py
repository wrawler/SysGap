import unittest

from questionnaire import run_questionnaire


class QuestionnaireTests(unittest.TestCase):
    def test_collects_optional_structured_cpu_requirement_values(self):
        answers = iter([
            "5",  # General use
            "1",  # No current problem
            "",   # Activity
            "",   # Minimum RAM
            "",   # Minimum VRAM
            "6",  # Minimum CPU cores
            "3.2",  # Minimum CPU base clock
            "",   # Minimum free storage
            "",   # CPU requirement text
            "https://example.test/requirements",
        ])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["user_supplied_requirements"]["min_cpu_cores"], 6)
        self.assertEqual(result["user_supplied_requirements"]["min_cpu_base_clock_ghz"], 3.2)
        self.assertEqual(result["effective_requirements"]["min_ram_gib"], 16)
        self.assertEqual(result["requirement_sources"]["min_ram_gib"], "purpose_profile")
        self.assertEqual(result["effective_requirements"]["min_cpu_cores"], 6)
        self.assertEqual(
            result["effective_requirements"]["source_reference"],
            "https://example.test/requirements",
        )

    def test_rejects_fractional_cpu_core_count(self):
        answers = iter([
            "5", "1", "", "", "", "6.5", "6", "3.2", "", "", "",
        ])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["user_supplied_requirements"]["min_cpu_cores"], 6)

    def test_gaming_profile_fills_blank_floors_and_user_answers_override_it(self):
        answers = iter([
            "1", "1", "", "", "", "", "32", "", "", "", "", "", "",
        ])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["effective_requirements"]["min_ram_gib"], 32)
        self.assertEqual(result["requirement_sources"]["min_ram_gib"], "user_supplied")
        self.assertEqual(result["effective_requirements"]["min_vram_gib"], 8)
        self.assertEqual(result["effective_requirements"]["min_cpu_cores"], 6)
        self.assertEqual(result["effective_requirements"]["min_free_storage_gib"], 100)
        self.assertEqual(result["effective_requirements"]["min_cpu_base_clock_ghz"], None)

    def test_rendering_is_a_separate_purpose_profile(self):
        answers = iter(["3", "1", "", "", "", "", "", "", "", "", "", "", ""])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["purpose"], "rendering")
        self.assertEqual(result["effective_requirements"]["min_ram_gib"], 32)

    def test_upgrade_planning_does_not_apply_an_unrelated_profile(self):
        answers = iter(["6", "1", "", "", "", "", "", "", "", "", ""])
        result = run_questionnaire(lambda _prompt: next(answers))
        self.assertEqual(result["effective_requirements"]["min_ram_gib"], None)
        self.assertEqual(result["requirement_sources"]["min_ram_gib"], "not_set")


if __name__ == "__main__":
    unittest.main()
