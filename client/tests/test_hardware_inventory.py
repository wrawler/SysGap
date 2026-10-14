import unittest
from unittest.mock import patch

import hardware_inventory


class HardwareInventoryTests(unittest.TestCase):
    def test_non_windows_uses_common_provider_without_wmi_fields(self):
        with patch.object(hardware_inventory.os, "name", "posix"):
            provider = hardware_inventory._platform_provider()

        self.assertEqual(provider.name, "common-psutil")
        notes = []
        result = provider.collect(notes)
        self.assertTrue(notes)
        self.assertEqual(result["gpus"], [])
        self.assertIsNone(result["cpu"])

    def test_windows_uses_wmi_provider(self):
        with patch.object(hardware_inventory.os, "name", "nt"):
            provider = hardware_inventory._platform_provider()

        self.assertEqual(provider.name, "windows-wmi")


if __name__ == "__main__":
    unittest.main()
