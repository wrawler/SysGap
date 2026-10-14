import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import hardware_inventory


class HardwareInventoryTests(unittest.TestCase):
    def test_linux_gpu_vram_reads_matching_drm_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            card = Path(directory) / "card1"
            device = card / "device"
            device.mkdir(parents=True)
            (device / "uevent").write_text(
                "PCI_SLOT_NAME=0000:03:00.0\n",
                encoding="utf-8",
            )
            (device / "mem_info_vram_total").write_text(
                str(8 * hardware_inventory.GIB),
                encoding="utf-8",
            )
            self.assertEqual(
                hardware_inventory._linux_gpu_vram_gib("03:00.0", Path(directory)),
                8,
            )

    @patch.object(hardware_inventory.subprocess, "run")
    @patch.object(hardware_inventory.shutil, "which", return_value="/usr/bin/lspci")
    def test_linux_gpu_parser_uses_product_name_and_vram(self, _which, run):
        run.return_value = type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": '03:00.0 "VGA compatible controller [0300]" "Advanced Micro Devices, Inc. [AMD/ATI]" "Navi 23 [Radeon RX 6600]" "ASRock"\n',
            },
        )()
        with patch.object(
            hardware_inventory,
            "_linux_gpu_vram_gib",
            return_value=8,
        ):
            result = hardware_inventory._linux_gpu_names([])
        self.assertEqual(result[0]["name"], "Navi 23 [Radeon RX 6600]")
        self.assertEqual(result[0]["dedicated_memory_gib"], 8)

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
