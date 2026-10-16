"""Check notebook exports, portable weights, and the rank chart's orientation."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import torch

from germanbridgegameenv import GermanBridgeGameEnv
from training_artifacts import create_history_image, save_training_run


class ArtifactTests(unittest.TestCase):
    def test_export_and_notebook_save_cell_create_separate_complete_runs(self):
        actor, critic = torch.nn.Linear(2, 3), torch.nn.Linear(2, 1)
        env = GermanBridgeGameEnv()
        env.episode_history = [
            {"episode": 1, "score": -10, "rank": 4, "reward": -2.5},
            {"episode": 2, "score": 20, "rank": 1, "reward": 7.5}]
        env.finish_training()
        with tempfile.TemporaryDirectory() as temporary:
            first = save_training_run(actor, critic, env, output_root=temporary)
            notebook = json.loads(Path(__file__).with_name("train.ipynb").read_text(encoding="utf-8"))
            cell = notebook["cells"][-1]
            self.assertEqual(cell["id"], "save-training-artifacts")
            namespace = dict(actor_model=actor, critic_model=critic, env=env,
                             episode=2, epoch=1, learning_rate=0.001, batch_size=32,
                             gamma=0.99, epsilon=0.2, entropy_coefficient=0.01,
                             show_gui=False, charts_only=True)

            def save_to_temporary(*args, **kwargs):
                kwargs["output_root"] = temporary
                return save_training_run(*args, **kwargs)

            with patch("training_artifacts.save_training_run", side_effect=save_to_temporary):
                with contextlib.redirect_stdout(io.StringIO()):
                    exec("".join(cell["source"]), namespace)
            second = namespace["saved_folder"]
            self.assertNotEqual(first, second)
            for folder in (first, second):
                self.assertEqual({path.name for path in folder.iterdir()}, {
                    "actor_state_dict.pt", "critic_state_dict.pt", "score_history.png",
                    "rank_history.png", "reward_history.png", "episode_history.csv",
                    "run_metadata.json"})
                for name, original in (("actor", actor), ("critic", critic)):
                    restored = torch.load(folder / f"{name}_state_dict.pt",
                                          map_location="cpu", weights_only=True)
                    for key, value in original.state_dict().items():
                        torch.testing.assert_close(restored[key], value)
                for key in ("score", "rank", "reward"):
                    with Image.open(folder / f"{key}_history.png") as image:
                        self.assertEqual(image.size, (1440, 720))
                        image.verify()
                with (folder / "episode_history.csv").open(newline="", encoding="utf-8") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(float(rows[-1]["reward"]), 7.5)
            metadata = json.loads((second / "run_metadata.json").read_text(encoding="utf-8"))
            self.assertIs(metadata["config"]["show_gui"], False)
            self.assertIs(metadata["config"]["charts_only"], True)
            self.assertEqual(metadata["episodes_with_results"], 2)

    def test_empty_single_and_tied_rank_charts(self):
        for history in ([], [{"episode": 1, "score": 0, "rank": 1, "reward": 0.0}],
                        [{"episode": i, "score": 10, "rank": 1, "reward": None} for i in (1, 2)]):
            for key in ("score", "rank", "reward"):
                image = create_history_image(history, key)
                try:
                    self.assertEqual(image.size, (1440, 720))
                finally:
                    image.close()

    def test_exported_rank_has_first_place_at_the_top(self):
        image = create_history_image([{"episode": 1, "rank": 1},
                                      {"episode": 2, "rank": 4}], "rank")
        try:
            rank_color = (39, 130, 107)
            self.assertEqual(image.getpixel((125, 110)), rank_color)
            self.assertEqual(image.getpixel((1398, 620)), rank_color)
            self.assertNotEqual(image.getpixel((125, 620)), rank_color)
        finally:
            image.close()


if __name__ == "__main__":
    unittest.main()
