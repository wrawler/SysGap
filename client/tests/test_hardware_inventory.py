import unittest
from unittest.mock import patch

import hardware_inventory


class HardwareInventoryTests(unittest.TestCase):
    def test_non_windows_uses_common_provider_without_wmi_fields(self):
        with (
            patch.object(hardware_inventory.os, "name", "posix"),
            patch.object(hardware_inventory.platform, "system", return_value="Other"),
        ):
            provider = hardware_inventory._platform_provider()
            notes = []
            result = provider.collect(notes)
        self.assertEqual(provider.name, "common-psutil")
        self.assertTrue(notes)
        self.assertEqual(result["gpus"], [])
        self.assertEqual(result["cpu"]["logical_processors"], hardware_inventory.psutil.cpu_count())

    @patch.object(hardware_inventory.platform, "system", return_value="Linux")
    @patch.object(hardware_inventory.shutil, "which", return_value=None)
    def test_linux_common_provider_records_missing_gpu_tool(self, _which, _system):
        notes = []
        result = hardware_inventory._CommonInventoryProvider().collect(notes)
        self.assertEqual(result["gpus"], [])
        self.assertTrue(any("lspci" in note for note in notes))

    def test_windows_uses_wmi_provider(self):
        with patch.object(hardware_inventory.os, "name", "nt"):
            provider = hardware_inventory._platform_provider()

        self.assertEqual(provider.name, "windows-wmi")


if __name__ == "__main__":
    unittest.main()
