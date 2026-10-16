"""Verify that console and notebook progress replace existing output."""

import io
import os
import re
import unittest
from unittest.mock import Mock, patch

from training_status import TrainingStatus


def visible_terminal_rows(output):
    """Interpret the small set of cursor controls used by the status renderer."""
    rows, row, column, index = [""], 0, 0, 0
    while index < len(output):
        control = re.match(r"\x1b\[(\d+)([AK])", output[index:])
        if control:
            if control[2] == "A":
                row -= int(control[1])
                assert row >= 0
            else:
                rows[row] = ""
            index += len(control[0])
            continue
        character = output[index]
        if character == "\r":
            column = 0
        elif character == "\n":
            row += 1
            if row == len(rows):
                rows.append("")
        else:
            previous = rows[row].ljust(column)
            rows[row] = previous[:column] + character + previous[column + 1:]
            column += 1
        index += 1
    return [line for line in rows if line]


class TrainingStatusTests(unittest.TestCase):
    def test_terminal_overwrites_and_clears_longer_previous_message(self):
        stream = io.StringIO()
        status = TrainingStatus(stream=stream)
        status.update("Episode 1 - collecting\nOld reward information\nOld timing information")
        status.update("Episode 2\nReward 3\nAvg 1s", final=True)
        status.finish()
        text = stream.getvalue()
        self.assertEqual(text.count("\x1b[2A"), 1)
        self.assertEqual(text.count("\x1b[2K"), 6)
        self.assertEqual(visible_terminal_rows(text), ["Episode 2", "Reward 3", "Avg 1s"])
        self.assertTrue(text.endswith("\n"))

    def test_terminal_uses_compact_message_without_wrapping(self):
        stream = io.StringIO()
        stream.isatty = lambda: True
        status = TrainingStatus(stream=stream)
        with patch("training_status.shutil.get_terminal_size", return_value=os.terminal_size((80, 24))):
            status.update("Episode 1/1000 | Model update 1/5\n" + "Long reward information " * 5 +
                          "\nAvg episode: 1.20 s | Total elapsed: 00:00:10", final=True)
        rows = visible_terminal_rows(stream.getvalue())
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(len(row) <= 79 for row in rows))
        self.assertIn("Avg episode: 1.20 s", rows[2])
        self.assertIn("Total elapsed: 00:00:10", rows[2])

    def test_notebook_reuses_one_display_without_clearing_other_outputs(self):
        display = Mock()
        with patch("training_status._notebook_display", return_value=display):
            status = TrainingStatus()
            status.update("Collecting\nReward 0\nAvg --")
            status.update("Model update\nReward 1\nAvg --")
            status.update("Training complete\nReward 1\nAvg 2s", final=True)
            status.finish()
        display.assert_called_once_with({"text/plain": "Collecting\nReward 0\nAvg --"},
                                        raw=True, display_id=True)
        self.assertEqual(display.return_value.update.call_count, 2)
        display.return_value.update.assert_called_with(
            {"text/plain": "Training complete\nReward 1\nAvg 2s"}, raw=True)


if __name__ == "__main__":
    unittest.main()
