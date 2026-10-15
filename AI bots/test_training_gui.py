"""Regression checks for collection state and observer controls."""

import ast
import json
from pathlib import Path
import random
import tkinter as tk
import unittest
from unittest.mock import patch

from germanbridgegameenv import GermanBridgeGameEnv
from player import AIBot, ComputerBot
from training_gui import GermanBridgeTrainingGUI


def random_action(env, state):
    if env.bidding_stage:
        return random.randint(0, env.round)
    hand, lead = state["own hand"], state["fixed_suit"]
    follows = any(card // 13 == lead for card in hand)
    legal = [card for card in hand if not follows or
             card // 13 in (lead, env.triumph_suit)]
    return 14 + random.choice(legal)


class CollectionTests(unittest.TestCase):
    def test_full_games_and_episode_reset(self):
        env = GermanBridgeGameEnv()
        seats = set()
        try:
            for seed in range(12):
                random.seed(seed)
                state, _ = env.reset()
                seats.add(env.agent_position)
                self.assertEqual(env.played_cards, [])
                self.assertEqual(env.played_by, [])
                self.assertIsNone(env.last_trick)
                done, steps = False, 0
                bidding_rounds = []
                while not done:
                    bidding_round = env.round if env.bidding_stage else None
                    state, reward, done, _, _ = env.step(random_action(env, state))
                    steps += 1
                    self.assertEqual(len(env.played_by), len(env.played_cards))
                    self.assertLessEqual(steps, 104)
                    if env.playing_stage:
                        order = env.played_by + [env.current_player]
                        for previous, following in zip(order, order[1:]):
                            self.assertEqual(following, (previous + 1) % 4)
                        if bidding_round is not None:
                            self.assertEqual(order[0], (bidding_round + 1) % 4)
                            bidding_rounds.append(bidding_round)
                self.assertEqual(steps, 104)
                self.assertEqual(bidding_rounds, list(range(1, 14)))
                self.assertEqual(sum(player.won for player in env.players), 13)
                self.assertEqual(len(env.episode_history), seed + 1)
                self.assertEqual(env.episode_history[-1]["episode"], seed + 1)
                self.assertEqual(env.episode_history[-1]["score"], env.scores[env.agent_position])
            self.assertEqual(seats, {0, 1, 2, 3})
            self.assertIsNone(env._gui)
        finally:
            env.close()

    def test_unmade_bids_are_not_zero(self):
        env = GermanBridgeGameEnv()
        with patch("germanbridgegameenv.random.randint", return_value=1):
            env.reset()
        self.assertEqual([player.bidded for player in env.players], [None] * 4)

    def test_training_timing_includes_updates_and_survives_resets(self):
        env = GermanBridgeGameEnv()
        self.assertEqual(env.get_training_timing(), (0.0, None))
        with patch("germanbridgegameenv.time.monotonic", return_value=100.0) as clock:
            env.start_training_timer()
            env.reset()
            clock.return_value = 115.0
            self.assertEqual(env.get_training_timing(), (15.0, None))
            # The caller finishes the episode only after all model updates.
            clock.return_value = 120.0
            env.finish_training_episode()
            self.assertEqual(env.get_training_timing(), (20.0, 20.0))
            env.reset()
            clock.return_value = 145.0
            self.assertEqual(env.get_training_timing(), (45.0, 20.0))
            clock.return_value = 160.0
            env.finish_training_episode()
            self.assertEqual(env.get_training_timing(), (60.0, 30.0))
            clock.return_value = 170.0
            env.close()
            clock.return_value = 200.0
            self.assertEqual(env.get_training_timing(), (70.0, 30.0))
            # Repeated cleanup must not extend a stopped clock.
            env.close()
            self.assertEqual(env.get_training_timing(), (70.0, 30.0))
            env.start_training_timer()
            self.assertEqual(env.get_training_timing(), (0.0, None))
            env.close()

    def test_completed_history_survives_reset_and_shares_tied_ranks(self):
        env = GermanBridgeGameEnv()
        cases = [([10, 10, 5, 0], 1, 1), ([10, 5, 0, -2], 1, 2),
                 ([12, 4, -8, -8], 2, 3), ([12, 4, -8, -9], 3, 4)]
        try:
            for episode, (scores, seat, expected_rank) in enumerate(cases, 7):
                env.set_training_progress(episode=episode)
                env.reset()
                previous = list(env.episode_history)
                env._record_episode_result()  # Incomplete games must not appear.
                self.assertEqual(env.episode_history, previous)
                env.game_over, env.agent_position, env.scores = True, seat, scores
                env._record_episode_result()
                self.assertEqual(env.episode_history[-1], {
                    "episode": episode, "score": scores[seat], "rank": expected_rank,
                    "reward": None})
                env._record_episode_result()  # Repeated refreshes must not duplicate results.
                self.assertEqual(len(env.episode_history), len(previous) + 1)
                self.assertEqual(env.episode_history[:-1], previous)
        finally:
            env.close()

    def test_computer_bids_never_complete_the_round_total(self):
        bot = ComputerBot()
        for n in range(1, 14):
            for current_total in (0, n - 1, n, n + 1, 3 * n):
                for _ in range(20):
                    bid = bot.bid(n, current_total=current_total)
                    self.assertGreaterEqual(bid, 0)
                    self.assertLessEqual(bid, n)
                    self.assertNotEqual(current_total + bid, n)
                    self.assertEqual(bot.bidded, bid)

    def test_bots_use_actual_bids_during_reset_and_later_rounds(self):
        env = GermanBridgeGameEnv()
        original_bid = ComputerBot.bid
        checked_rounds = []

        def checked_bid(bot, n, current_total=0):
            self.assertEqual(current_total,
                             sum(p.bidded for p in env.players if p.bidded is not None))
            bid = original_bid(bot, n, current_total=current_total)
            self.assertNotEqual(current_total + bid, n)
            checked_rounds.append(n)
            return bid

        try:
            with patch.object(ComputerBot, "bid", checked_bid):
                # Seat zero bids last in round one, exercising bot bids inside reset().
                with patch("germanbridgegameenv.random.randint", return_value=0):
                    state, _ = env.reset()
                self.assertEqual(checked_rounds, [1, 1, 1])
                done = False
                while not done:
                    state, _, done, _, _ = env.step(random_action(env, state))
            self.assertEqual(checked_rounds, [n for n in range(1, 14) for _ in range(3)])
        finally:
            env.close()

    def test_winner_is_a_seat_not_a_trick_index(self):
        env = GermanBridgeGameEnv()
        env.players = [ComputerBot(), ComputerBot(), ComputerBot(), AIBot()]
        env.agent_position, env.current_player, env.round = 3, 2, 1
        env.scores = [0] * 4
        env.playing_stage = True
        for player, card in zip(env.players, [0, 1, 12, 2]):
            player.hand = [card]
            player.bidded = 0
        env._play_round()  # P2 leads the ace; the agent at P3 acts next.
        self.assertEqual(env.played_by, [2])
        env.step(14 + 2)
        self.assertEqual(env.scores, [10, 10, -1, 10])

    def test_notebook_code_compiles(self):
        notebook = json.loads(Path(__file__).with_name("train.ipynb").read_text(encoding="utf-8"))
        for cell in notebook["cells"]:
            source = "".join(cell.get("source", []))
            if cell["cell_type"] == "code" and not source.lstrip().startswith("%"):
                compile(source, "train.ipynb", "exec")

    def test_notebook_gui_toggle(self):
        import gymnasium as gym

        notebook = json.loads(Path(__file__).with_name("train.ipynb").read_text(encoding="utf-8"))
        training_cell = next(cell for cell in notebook["cells"]
                             if "".join(cell.get("source", [])).startswith("episode ="))
        source = ast.parse("".join(training_cell["source"]))
        assignments = {node.targets[0].id: node for node in source.body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        settings = next(cell for cell in notebook["cells"] if cell["cell_type"] == "code")
        self.assertEqual(settings["id"], "gui-settings-toggle")
        namespace = {}
        exec(compile("".join(settings["source"]), "train.ipynb", "exec"), namespace)
        self.assertIs(namespace["show_gui"], True)
        self.assertNotIn("show_gui", assignments)
        create_env = compile(ast.Module(body=[assignments["env"]], type_ignores=[]),
                             "train.ipynb", "exec")
        with patch.dict(gym.envs.registry):
            gym.register(id="GermanBridgeGameEnv-v0", entry_point=GermanBridgeGameEnv)
            for enabled in (True, False):
                namespace.update(gym=gym, show_gui=enabled)
                exec(create_env, namespace)
                env = namespace["env"]
                try:
                    self.assertEqual(env.render_mode, "human" if enabled else None)
                    if not enabled:
                        env.reset()
                        env.render()
                        self.assertIsNone(env.unwrapped._gui)
                finally:
                    env.close()


class ObserverTests(unittest.TestCase):
    def setUp(self):
        # Exercise real Tk widgets without displaying a test window.
        self.root = tk.Tk()
        self.root.withdraw()
        self.env = GermanBridgeGameEnv(render_delay=0)
        self.env.reset()
        self.gui = GermanBridgeTrainingGUI(self.env, root=self.root)
        self.env._gui = self.gui
        self.env.render_mode = "human"

    def tearDown(self):
        self.env.close()

    def test_training_completion_keeps_window_open_and_freezes_clock(self):
        with patch("germanbridgegameenv.time.monotonic", return_value=100.0) as clock:
            self.env.start_training_timer()
            clock.return_value = 150.0
            self.env.finish_training()
            self.assertFalse(self.gui.closed)
            self.assertTrue(self.root.winfo_exists())
            self.assertEqual(self.gui.status.cget("text"), "TRAINING COMPLETE")
            self.assertEqual(str(self.gui.pause_button.cget("state")), "disabled")
            clock.return_value = 200.0
            self.gui._update_timing()
            self.assertIn("00:00:50", self.gui.timing.cget("text"))
            self.gui.tabs.select(2)
            self.root.update()
            self.assertEqual(self.gui.tabs.tab(self.gui.tabs.select(), "text"), "Episode reward")

    def test_reward_chart_preserves_collected_return_before_updates(self):
        self.env.game_over = True
        self.env._record_episode_result()
        self.env.record_episode_reward(-7.5)
        self.assertEqual(self.env.episode_history[-1]["reward"], -7.5)
        self.assertEqual(self.env._completed_training_episodes, 0)
        self.gui.refresh()
        self.assertEqual(len(self.gui.reward_chart.find_withtag("history-point")), 1)
        self.env.episode_history.append({"episode": 2, "score": 0, "rank": 2, "reward": 4.5})
        self.gui.refresh()
        points = self.gui.reward_chart.coords(self.gui.reward_chart.find_withtag("history-line")[0])
        self.assertLess(points[3], points[1])  # Higher reward appears higher on screen.

    def test_training_counters_and_live_updates_while_paused(self):
        with patch("germanbridgegameenv.time.monotonic", return_value=100.0) as clock:
            self.env.start_training_timer()
            clock.return_value = 165.0
            self.gui.refresh()
            self.assertIn("Training elapsed: 00:01:05", self.gui.timing.cget("text"))
            self.assertIn("Avg episode: --", self.gui.timing.cget("text"))
            clock.return_value = 220.0
            self.env.finish_training_episode()
            self.assertIn("Avg episode: 120.00 s", self.gui.timing.cget("text"))
            self.gui.toggle_pause()
            clock.return_value = 230.0
            # Exercise the scheduled timer during the existing pause event loop.
            self.root.after_cancel(self.gui._timing_after_id)
            self.gui._timing_after_id = self.root.after(10, self.gui._tick_timing)
            self.root.after(30, self.gui.next_event)
            self.gui._wait_for_event()
            self.assertTrue(self.gui.paused)
            self.assertIn("Training elapsed: 00:02:10", self.gui.timing.cget("text"))
            self.assertIn("Avg episode: 120.00 s", self.gui.timing.cget("text"))

    def test_seats_follow_clockwise_play_order(self):
        with patch.object(self.gui, "_draw_player", wraps=self.gui._draw_player) as draw:
            self.gui._draw_board()
        positions = {seat: (x + width / 2, y + 90)
                     for seat, x, y, width, active in (call.args for call in draw.call_args_list)}
        center_x = sum(x for x, y in positions.values()) / 4
        center_y = sum(y for x, y in positions.values()) / 4
        for seat in range(4):
            x1, y1 = positions[seat]
            x2, y2 = positions[(seat + 1) % 4]
            # Positive cross product means clockwise in screen coordinates (y down).
            self.assertGreater((x1 - center_x) * (y2 - center_y) -
                               (y1 - center_y) * (x2 - center_x), 0)

    def test_history_score_and_rank_chart_directions(self):
        self.env.episode_history.extend([
            {"episode": episode, "score": score, "rank": rank}
            for episode, score, rank in ((1, -10, 4), (2, 0, 1), (3, 20, 3), (4, 10, 2))])
        self.gui.refresh()
        score_line = self.gui.score_chart.find_withtag("history-line")[0]
        rank_line = self.gui.rank_chart.find_withtag("history-line")[0]
        score_points = self.gui.score_chart.coords(score_line)
        rank_points = self.gui.rank_chart.coords(rank_line)
        self.assertEqual(score_points[::2], sorted(score_points[::2]))
        # Larger scores are higher on the score chart (smaller screen y).
        self.assertLess(score_points[5], score_points[7])
        self.assertLess(score_points[7], score_points[3])
        self.assertLess(score_points[3], score_points[1])
        # Ranks 1, 2, 3, 4 appear from top to bottom, regardless of episode order.
        self.assertLess(rank_points[3], rank_points[7])
        self.assertLess(rank_points[7], rank_points[5])
        self.assertLess(rank_points[5], rank_points[1])
        ticks = {int(self.gui.rank_chart.itemcget(item, "text")):
                 self.gui.rank_chart.coords(item)[1]
                 for item in self.gui.rank_chart.find_withtag("y-tick")}
        self.assertLess(ticks[1], ticks[2])
        self.assertLess(ticks[2], ticks[3])
        self.assertLess(ticks[3], ticks[4])
        self.assertEqual(self.gui.tabs.tab(1, "text"), "Episode history")

    def test_history_charts_handle_empty_single_and_constant_results(self):
        self.gui.refresh()
        for chart in (self.gui.score_chart, self.gui.rank_chart, self.gui.reward_chart):
            self.assertFalse(chart.find_withtag("history-line"))
            texts = [chart.itemcget(item, "text") for item in chart.find_all()
                     if chart.type(item) == "text"]
            self.assertIn("Complete an episode to see its result.", texts)
        self.env.episode_history.append({"episode": 1, "score": 0, "rank": 1, "reward": 0.0})
        self.gui.refresh()
        for chart in (self.gui.score_chart, self.gui.rank_chart, self.gui.reward_chart):
            self.assertEqual(len(chart.find_withtag("history-point")), 1)
            self.assertFalse(chart.find_withtag("history-line"))
        self.env.episode_history.append({"episode": 2, "score": 0, "rank": 1, "reward": 0.0})
        self.gui.refresh()
        for chart in (self.gui.score_chart, self.gui.rank_chart, self.gui.reward_chart):
            points = chart.coords(chart.find_withtag("history-line")[0])
            self.assertEqual(points[1], points[3])
            self.assertLess(points[0], points[2])

    def test_progress_cards_and_final_game(self):
        self.env.set_training_progress(episode=2, total_episodes=5)
        state, _ = self.env.reset()
        done, steps, reward_sum = False, 0, 0
        while not done:
            state, reward, done, _, _ = self.env.step(random_action(self.env, state))
            steps += 1
            reward_sum += reward
            self.env.set_training_progress(steps=steps, episode_reward=reward_sum,
                                           last_reward=reward)
        self.assertIn("Episode: 2 / 5", self.gui.metrics.cget("text"))
        self.assertIn("104 / 104", self.gui.metrics.cget("text"))
        texts = [self.gui.canvas.itemcget(item, "text") for item in self.gui.canvas.find_all()
                 if self.gui.canvas.type(item) == "text"]
        self.assertIn("Round 13 / 13  |  GAME COMPLETE", texts)
        self.assertIn("Game complete.", self.gui.log.get("1.0", "end"))
        self.assertIsNone(self.gui._active_seat())
        self.assertEqual(len(self.env.episode_history), 1)
        self.assertEqual(self.env.episode_history[0]["episode"], 2)
        self.assertEqual(len(self.gui.score_chart.find_withtag("history-point")), 1)
        self.assertEqual(len(self.gui.rank_chart.find_withtag("history-point")), 1)

    def test_pause_next_resume_speed_and_close(self):
        self.gui.toggle_pause()
        self.assertTrue(self.gui.paused)
        self.root.after(20, self.gui.next_event)
        self.gui.refresh(wait=True)
        self.assertTrue(self.gui.paused)
        self.assertFalse(self.gui._advance)
        self.root.after(20, self.gui.toggle_pause)
        self.gui.refresh(wait=True)
        self.assertFalse(self.gui.paused)
        self.env.set_render_speed(0.1)
        self.assertAlmostEqual(self.gui.delay.get(), 0.1)
        self.gui._set_delay("0")
        self.assertEqual(self.env.render_delay, 0)
        # Closing while paused must release the wait without a Tk error.
        self.gui.toggle_pause()
        self.root.after(20, self.gui.close)
        self.gui.refresh(wait=True)
        self.assertTrue(self.gui.closed)
        self.env.render()
        self.assertIs(self.env._gui, self.gui)  # The observer must not reopen.
        state, _ = self.env.reset()
        self.env.step(random_action(self.env, state))  # Collection still runs.


if __name__ == "__main__":
    unittest.main()
