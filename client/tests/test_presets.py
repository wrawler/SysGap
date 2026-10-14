import unittest

from presets import PRESET_DATA_VERSION, available_presets, get_preset


class PresetTests(unittest.TestCase):
    def test_prioritized_purposes_have_curated_presets(self):
        self.assertEqual(PRESET_DATA_VERSION, "1")
        self.assertGreaterEqual(len(available_presets("gaming")), 3)
        self.assertGreaterEqual(len(available_presets("video_editing")), 3)
        self.assertGreaterEqual(len(available_presets("local_ai")), 3)

    def test_ai_preset_exposes_parameter_and_quantization_context(self):
        preset = get_preset("local_ai", "ai_13b_q4")
        self.assertEqual(preset["parameters_billion"], 13)
        self.assertEqual(preset["quantization"], "4-bit")
        self.assertEqual(preset["requirements"]["min_vram_gib"], 12)

    def test_preset_results_are_copies(self):
        preset = get_preset("gaming", "gaming_1080p_competitive")
        preset["requirements"]["min_ram_gib"] = 999
        self.assertEqual(
            get_preset("gaming", "gaming_1080p_competitive")["requirements"]["min_ram_gib"],
            16,
        )

    def test_unknown_preset_is_explicit(self):
        with self.assertRaises(ValueError):
            get_preset("gaming", "typo")


if __name__ == "__main__":
    unittest.main()
