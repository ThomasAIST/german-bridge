"""Check notebook loading and persistence of successful or interrupted profiles."""

import contextlib
import csv
import io
import json
from pathlib import Path
import pstats
import tempfile
import unittest

from profile_train import load_notebook_training, main, profile_call


class ProfileTests(unittest.TestCase):
    def test_loader_skips_magics_training_and_save_calls(self):
        sources = ["%load_ext autoreload\n%autoreload 2",
                   "show_gui = True\nran_training = False\nif True:\n    device = 'cuda'\nseen_device = device",
                   "def train():\n    global ran_training\n    ran_training = True",
                   "episode = 1000\nlearning_rate = 0.004\ntrain()",
                   "raise RuntimeError('The save cell must not run')"]
        notebook = {"cells": [{"cell_type": "code", "source": [source]} for source in sources]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "train.ipynb"
            path.write_text(json.dumps(notebook), encoding="utf-8")
            namespace = load_notebook_training(path, device="cpu")
        self.assertFalse(namespace["ran_training"])
        self.assertFalse(namespace["show_gui"])
        self.assertEqual(namespace["seen_device"], "cpu")
        self.assertEqual(namespace["episode"], 1000)
        self.assertEqual(namespace["learning_rate"], 0.004)
        namespace["train"]()
        self.assertTrue(namespace["ran_training"])

    def test_loader_reports_missing_train(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing.ipynb"
            path.write_text(json.dumps({"cells": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No train"):
                load_notebook_training(path)

    def test_profile_files_survive_completion_error_and_interrupt(self):
        with tempfile.TemporaryDirectory() as temporary:
            for error, expected_status in ((None, "completed"),
                                           (RuntimeError("failed training"), "failed"),
                                           (KeyboardInterrupt(), "interrupted")):
                def work():
                    sum(range(20))
                    if error is not None:
                        raise error

                output = Path(temporary) / expected_status
                with contextlib.redirect_stdout(io.StringIO()):
                    if error is None:
                        profile_call(work, output, top=5)
                    else:
                        with self.assertRaises(type(error)):
                            profile_call(work, output, top=5)
                self.assertEqual({path.name for path in output.iterdir()},
                                 {"train.prof", "report.txt", "functions.csv", "run.json"})
                info = json.loads((output / "run.json").read_text(encoding="utf-8"))
                self.assertEqual(info["status"], expected_status)
                self.assertGreaterEqual(info["wall_seconds"], 0)
                stats = pstats.Stats(str(output / "train.prof"))
                self.assertTrue(any(name == "work" for filename, line, name in stats.stats))
                with (output / "functions.csv").open(newline="", encoding="utf-8") as handle:
                    self.assertTrue(any(row["function"] == "work" for row in csv.DictReader(handle)))
                report = (output / "report.txt").read_text(encoding="utf-8")
                self.assertIn("cumulative time", report)
                self.assertIn("self time", report)

    def test_cli_rejects_zero_episodes_or_epochs(self):
        for option in ("--episodes", "--epochs"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main([option, "0"])
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
