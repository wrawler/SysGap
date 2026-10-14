import unittest
from unittest.mock import patch

import cli


class CliTests(unittest.TestCase):
    @patch("cli.diagnosis.run_workflow", return_value=0)
    def test_run_delegates_to_shared_workflow(self, run_workflow):
        self.assertEqual(cli.main(["run", "--sample-seconds", "5"]), 0)
        run_workflow.assert_called_once()
        self.assertEqual(run_workflow.call_args.kwargs["sample_seconds"], 5)

    def test_without_command_prints_help(self):
        self.assertEqual(cli.main([]), 0)


if __name__ == "__main__":
    unittest.main()
