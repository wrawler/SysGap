import unittest

from decision_engine import evaluate_assessment


def inventory(ram=16, gpus=None, free=(200, 50)):
    return {
        "cpu": {"name": "Example CPU", "physical_cores": 4, "max_clock_mhz": 4800},
        "gpus": gpus or [{"name": "Example GPU", "dedicated_memory_gib": 8}],
        "memory": {"summary": {"total_gib": ram}},
        "storage": {"volumes": [{"free_gib_at_scan": value} for value in free]},
    }


def questionnaire(
    ram=None,
    vram=None,
    free=None,
    cores=None,
    base_clock=None,
    purpose="upgrade_planning",
):
    return {
        "purpose": purpose,
        "symptom_label": "No current problem",
        "user_supplied_requirements": {
            "min_ram_gib": ram,
            "min_vram_gib": vram,
            "min_free_storage_gib": free,
            "min_cpu_cores": cores,
            "min_cpu_base_clock_ghz": base_clock,
        },
    }


class DecisionEngineTests(unittest.TestCase):
    def test_no_user_thresholds_are_unknown_not_guessed(self):
        result = evaluate_assessment(questionnaire(), inventory())
        by_area = {finding["area"]: finding for finding in result["findings"]}
        self.assertEqual(by_area["memory"]["status"], "unknown")
        self.assertEqual(by_area["graphics_memory"]["status"], "unknown")
        self.assertEqual(by_area["storage_capacity"]["status"], "unknown")
        self.assertEqual(result["overall_status"], "insufficient_information")

    def test_supplied_capacity_requirements_are_compared(self):
        result = evaluate_assessment(questionnaire(ram=32, vram=12, free=100), inventory())
        by_area = {finding["area"]: finding for finding in result["findings"]}
        self.assertEqual(by_area["memory"]["status"], "potential_concern")
        self.assertEqual(by_area["graphics_memory"]["status"], "potential_concern")
        self.assertEqual(by_area["storage_capacity"]["status"], "meets")
        self.assertEqual(result["overall_status"], "potential_concern")

    def test_preset_ram_floor_allows_small_hardware_reserved_difference(self):
        result = evaluate_assessment(
            questionnaire(purpose="gaming"),
            inventory(ram=15.41),
        )
        finding = next(item for item in result["findings"] if item["area"] == "memory")
        self.assertEqual(finding["status"], "meets")
        self.assertIn("hardware-reserved-memory allowance", finding["evidence"][0])

    def test_user_supplied_ram_floor_remains_strict(self):
        result = evaluate_assessment(
            questionnaire(ram=16),
            inventory(ram=15.41),
        )
        finding = next(item for item in result["findings"] if item["area"] == "memory")
        self.assertEqual(finding["status"], "potential_concern")

    def test_missing_gpu_vram_is_unknown_and_not_shared_memory(self):
        hardware = inventory(gpus=[{"name": "Integrated GPU", "dedicated_memory_gib": None}])
        result = evaluate_assessment(questionnaire(vram=4), hardware)
        finding = next(item for item in result["findings"] if item["area"] == "graphics_memory")
        self.assertEqual(finding["status"], "unknown")
        self.assertIn("could not be verified", finding["evidence"][0])

    def test_multiple_gpus_require_workload_adapter_selection(self):
        hardware = inventory(gpus=[
            {"name": "GPU A", "dedicated_memory_gib": 4},
            {"name": "GPU B", "dedicated_memory_gib": 8},
        ])
        result = evaluate_assessment(questionnaire(vram=6), hardware)
        finding = next(item for item in result["findings"] if item["area"] == "graphics_memory")
        self.assertEqual(finding["status"], "unknown")
        self.assertIn("ambiguous", finding["title"])

    def test_integrated_vram_is_not_assumed_to_be_discrete_workload_gpu(self):
        hardware = inventory(gpus=[
            {"name": "NVIDIA RTX Example", "dedicated_memory_gib": None},
            {"name": "Intel Graphics", "dedicated_memory_gib": 2},
        ])
        result = evaluate_assessment(questionnaire(vram=6), hardware)
        finding = next(item for item in result["findings"] if item["area"] == "graphics_memory")
        self.assertEqual(finding["status"], "unknown")
        self.assertIn("ambiguous", finding["title"])

    def test_explicit_gpu_selection_uses_only_matching_adapter(self):
        hardware = inventory(gpus=[
            {"name": "GPU A", "dedicated_memory_gib": 4},
            {"name": "GPU B", "dedicated_memory_gib": 8},
        ])
        answers = questionnaire(vram=6)
        answers["context"] = {"gpu_used_by_workload": "GPU A"}
        result = evaluate_assessment(answers, hardware)
        finding = next(item for item in result["findings"] if item["area"] == "graphics_memory")
        self.assertEqual(finding["status"], "potential_concern")

    def test_meeting_minimum_does_not_claim_performance(self):
        result = evaluate_assessment(questionnaire(ram=8, vram=4, free=25), inventory())
        self.assertEqual(result["overall_status"], "no_supplied_capacity_floor_failed")
        self.assertIn("does not prove", result["summary"])
        self.assertTrue(any("No workload was observed" in item
                            for finding in result["findings"]
                            for item in finding["caveats"]))

    def test_zero_or_negative_requirements_are_not_accepted_as_numbers(self):
        result = evaluate_assessment(questionnaire(ram=0, vram=-1, free=0), inventory())
        by_area = {finding["area"]: finding for finding in result["findings"]}
        self.assertEqual(by_area["memory"]["status"], "unknown")
        self.assertEqual(by_area["graphics_memory"]["status"], "unknown")
        self.assertEqual(by_area["storage_capacity"]["status"], "unknown")

    def test_cpu_physical_core_floor_is_compared_without_using_logical_processors(self):
        result = evaluate_assessment(questionnaire(cores=6), inventory())
        finding = next(item for item in result["findings"] if item["area"] == "processor_cores")
        self.assertEqual(finding["status"], "potential_concern")
        self.assertIn("4 physical cores", finding["evidence"][0])
        self.assertIn("not proof", finding["caveats"][0])

    def test_cpu_max_clock_is_not_misrepresented_as_base_clock(self):
        result = evaluate_assessment(questionnaire(base_clock=3.2), inventory())
        finding = next(item for item in result["findings"] if item["area"] == "processor_base_clock")
        self.assertEqual(finding["status"], "unknown")
        self.assertIn("4800 MHz", finding["evidence"][1])
        self.assertIn("not a comparable base-clock", finding["evidence"][1])

    def test_cpu_core_floor_met_is_not_a_performance_claim(self):
        hardware = inventory()
        hardware["cpu"]["physical_cores"] = 8
        result = evaluate_assessment(questionnaire(cores=6), hardware)
        finding = next(item for item in result["findings"] if item["area"] == "processor_cores")
        self.assertEqual(finding["status"], "meets")
        self.assertIn("does not establish CPU performance", finding["caveats"][0])

    def test_gaming_profile_fills_blank_floors_and_reports_per_metric_attainment(self):
        result = evaluate_assessment(
            questionnaire(purpose="gaming"),
            inventory(),
        )
        self.assertEqual(result["profile_comparison"]["profile_label"], "Gaming baseline")
        self.assertEqual(
            result["effective_requirements"]["min_vram_gib"],
            8,
        )
        self.assertEqual(
            result["requirement_sources"]["min_vram_gib"],
            "purpose_profile",
        )
        metrics = {
            metric["metric"]: metric
            for metric in result["profile_comparison"]["metrics"]
        }
        self.assertEqual(metrics["ram_capacity"]["target_attainment_percent"], 100)
        self.assertEqual(metrics["cpu_physical_cores"]["target_attainment_percent"], 66.7)
        self.assertEqual(metrics["cpu_physical_cores"]["status"], "below_floor")
        self.assertEqual(
            result["profile_comparison"]["component_scores"]["cpu"]["score"],
            66.7,
        )
        self.assertEqual(
            result["profile_comparison"]["component_scores"]["ram"]["score"],
            100,
        )
        self.assertIn("not a performance score", result["profile_comparison"]["method"])
        self.assertTrue(any(
            "selected purpose-profile floor" in evidence.lower()
            for finding in result["findings"]
            for evidence in finding["evidence"]
        ))

    def test_unknown_gpu_keeps_profile_attainment_unknown(self):
        hardware = inventory(gpus=[
            {"name": "NVIDIA GPU", "dedicated_memory_gib": None},
            {"name": "Intel Graphics", "dedicated_memory_gib": 2},
        ])
        result = evaluate_assessment(questionnaire(purpose="gaming"), hardware)
        gpu_metric = next(
            metric for metric in result["profile_comparison"]["metrics"]
            if metric["metric"] == "dedicated_vram"
        )
        self.assertEqual(gpu_metric["status"], "unknown")
        self.assertIsNone(gpu_metric["target_attainment_percent"])


if __name__ == "__main__":
    unittest.main()
