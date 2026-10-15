"""Tkinter observer for GermanBridgeGameEnv, driven by the training loop.

All Tk calls run on the same thread as reset()/step(); no extra mainloop or
background thread is needed. Import this module only when rendering is enabled.
"""

import time
import tkinter as tk
from tkinter import ttk


class GermanBridgeTrainingGUI:
    BG = "#101820"
    PANEL = "#1b2a32"
    TEXT = "#f7f3e8"
    MUTED = "#b7cbd3"
    ACCENT = "#f5c451"

    def __init__(self, env, root=None):
        self.env = env
        self.root = root if root is not None else tk.Tk()
        self.closed = False
        self.paused = False
        self._advance = False
        self._chart_versions = {}
        self.root.title("German Bridge - Training observer")
        self.root.geometry("1180x740")
        self.root.minsize(1000, 700)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=18, pady=(14, 4))
        self._label(header, "GERMAN BRIDGE", 20, bold=True).pack(anchor="w")
        self._label(header, "Training observer  |  All four hands are visible", 10,
                    color=self.MUTED).pack(anchor="w")

        content = tk.Frame(self.root, bg=self.BG)
        content.pack(fill="both", expand=True)
        sidebar = tk.Frame(content, bg=self.PANEL, width=280)
        sidebar.pack(side="right", fill="y", padx=(0, 16), pady=(8, 16))
        sidebar.pack_propagate(False)
        self.tabs = ttk.Notebook(content)
        self.tabs.pack(side="left", fill="both", expand=True, padx=(0, 8))
        table_tab = tk.Frame(self.tabs, bg=self.BG)
        history_tab = tk.Frame(self.tabs, bg=self.BG)
        self.tabs.add(table_tab, text="Live game")
        self.tabs.add(history_tab, text="Episode history")
        reward_tab = tk.Frame(self.tabs, bg=self.BG)
        self.tabs.add(reward_tab, text="Episode reward")
        self.canvas = tk.Canvas(table_tab, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self._draw_board())
        self._label(history_tab, "Completed episodes | Final game scores | Ties share a rank",
                    10, color=self.MUTED).pack(anchor="w", padx=14, pady=(10, 4))
        self.score_chart = tk.Canvas(history_tab, bg=self.BG, height=260,
                                     highlightthickness=0)
        self.rank_chart = tk.Canvas(history_tab, bg=self.BG, height=260,
                                    highlightthickness=0)
        self.reward_chart = tk.Canvas(reward_tab, bg=self.BG, highlightthickness=0)
        self.reward_chart.pack(fill="both", expand=True, padx=8, pady=4)
        self.reward_chart.bind("<Configure>", lambda event: self._draw_history_chart("reward"))
        for chart, key in ((self.score_chart, "score"), (self.rank_chart, "rank")):
            chart.pack(fill="both", expand=True, padx=8, pady=4)
            chart.bind("<Configure>", lambda event, key=key: self._draw_history_chart(key))

        self.status = self._label(sidebar, "DATA COLLECTION", 12, bold=True,
                                  color=self.ACCENT)
        self.status.pack(anchor="w", padx=14, pady=(14, 8))
        self.metrics = self._label(sidebar, "", 11)
        self.metrics.configure(justify="left")
        self.metrics.pack(anchor="w", padx=14)
        self.timing = self._label(sidebar, "Training elapsed: 00:00:00\nAvg episode: --", 10)
        self.timing.configure(justify="left")
        self.timing.pack(anchor="w", padx=14, pady=(8, 0))
        self.progress = ttk.Progressbar(sidebar, maximum=104)
        self.progress.pack(fill="x", padx=14, pady=(10, 12))

        self._label(sidebar, "SCORES", 11, bold=True).pack(anchor="w", padx=14)
        self.scores = self._label(sidebar, "", 10)
        self.scores.configure(justify="left")
        self.scores.pack(anchor="w", padx=14, pady=(4, 12))
        self._label(sidebar, "RECENT ACTIONS", 11, bold=True).pack(anchor="w", padx=14)
        self.log = tk.Text(sidebar, height=11, wrap="word", bg=self.PANEL,
                           fg=self.MUTED, font=("Segoe UI", 9), relief="flat",
                           state="disabled", takefocus=False)
        self.log.pack(fill="both", expand=True, padx=14, pady=(6, 10))

        controls = tk.Frame(sidebar, bg=self.PANEL)
        controls.pack(fill="x", padx=14)
        self.pause_button = tk.Button(controls, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side="left", fill="x", expand=True)
        self.step_button = tk.Button(controls, text="Next event", command=self.next_event,
                                     state="disabled")
        self.step_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.delay = tk.DoubleVar(master=self.root, value=env.render_delay)
        self._label(sidebar, "Seconds per event (0 = fastest)", 9,
                    color=self.MUTED).pack(anchor="w", padx=14, pady=(10, 0))
        tk.Scale(sidebar, from_=0, to=max(2, env.render_delay), resolution=0.05,
                 orient="horizontal", variable=self.delay, command=self._set_delay,
                 bg=self.PANEL, fg=self.TEXT, highlightthickness=0,
                 troughcolor=self.BG).pack(fill="x", padx=14)
        self.footer = self._label(sidebar, "Closing this window continues training.", 9,
                                  color=self.MUTED)
        self.footer.pack(anchor="w", padx=14, pady=(4, 12))
        self._timing_after_id = self.root.after(250, self._tick_timing)

    def _label(self, parent, text, size, bold=False, color=None):
        return tk.Label(parent, text=text, bg=parent.cget("bg"),
                        fg=color or self.TEXT,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def refresh(self, wait=False):
        """Paint the state and service controls, optionally pacing game events."""
        if self.closed:
            return
        try:
            self._update_timing()
            self._draw_board()
            self._draw_history_chart("score")
            self._draw_history_chart("rank")
            self._draw_history_chart("reward")
            progress = self.env.training_progress
            phase = progress["phase"].upper()
            self.status.configure(text=f"{'PAUSED | ' if self.paused else ''}{phase}")
            episode = progress["episode"]
            total = progress["total_episodes"]
            episode_text = "-" if episode is None else str(episode)
            if total is not None:
                episode_text += f" / {total}"
            reward = progress["last_reward"]
            self.metrics.configure(text=(
                f"Episode: {episode_text}\n"
                f"Samples collected: {progress['steps']} / 104\n"
                f"Episode reward: {progress['episode_reward']:+.2f}\n"
                f"Last reward: {'-' if reward is None else f'{reward:+.2f}'}"))
            self.progress["value"] = progress["steps"]
            order = sorted(range(len(self.env.players)),
                           key=lambda seat: self.env.scores[seat], reverse=True)
            self.scores.configure(text="\n".join(
                f"{1 + sum(score > self.env.scores[seat] for score in self.env.scores)}.  "
                f"P{seat}{' (AI)' if seat == self.env.agent_position else ''}"
                f"     {self.env.scores[seat]:+d}"
                for seat in order))
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.insert("end", "\n".join(self.env.recent_events))
            self.log.see("end")
            self.log.configure(state="disabled")
            self.root.update_idletasks()
            self.root.update()
            if wait and not self.closed:
                self._wait_for_event()
        except tk.TclError:
            # The window may be destroyed by WM_DELETE_WINDOW during update().
            self.closed = True

    def _update_timing(self):
        elapsed, average = self.env.get_training_timing()
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        average_text = "--" if average is None else f"{average:.2f} s"
        self.timing.configure(text=(f"Training elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
                                    f"Avg episode: {average_text}"))

    def _tick_timing(self):
        if not self.closed:
            self._update_timing()
            self._timing_after_id = self.root.after(250, self._tick_timing)

    def _draw_history_chart(self, key):
        """Draw an episode chart using Tk only; redraw on new results or resize."""
        if self.closed:
            return
        canvas = {"score": self.score_chart, "rank": self.rank_chart,
                  "reward": self.reward_chart}[key]
        history = [result for result in self.env.episode_history if result.get(key) is not None]
        width, height = max(320, canvas.winfo_width()), max(220, canvas.winfo_height())
        version = (len(history), width, height)
        if self._chart_versions.get(key) == version:
            return
        self._chart_versions[key] = version
        canvas.delete("all")
        color = {"score": self.ACCENT, "rank": "#65b89c", "reward": "#79b8ff"}[key]

        def label(x, y, text, anchor="nw", bold=False, tags=()):
            return canvas.create_text(x, y, text=text, anchor=anchor, fill=self.MUTED,
                                      font=("Segoe UI", 10, "bold" if bold else "normal"),
                                      tags=tags)

        title = {"score": "AI final score by episode", "rank": "AI rank by episode (1st at top)",
                 "reward": "AI episode reward by episode"}[key]
        label(14, 8, title, bold=True)
        left, right, top, bottom = 66, width - 24, 46, height - 44
        values = [result[key] for result in history]
        if key == "rank":
            low, high = 1, 4
            ticks = [1, 2, 3, 4]
        else:
            low, high = min([0] + values), max([0] + values)
            padding = max(1, (high - low) * 0.1)
            low, high = low - padding, high + padding
            ticks = [low + i * (high - low) / 4 for i in range(5)]

        def y_position(value):
            fraction = (value - low) / (high - low)
            # Screen y grows downwards, so lower rank numbers sit at the top.
            return top + fraction * (bottom - top) if key == "rank" else bottom - fraction * (bottom - top)

        for value in ticks:
            y = y_position(value)
            canvas.create_line(left, y, right, y, fill="#2c424c", dash=(3, 4))
            tick = str(value) if key == "rank" else (
                f"{value:,.0f}" if high - low >= 4 else f"{value:.1f}".rstrip("0").rstrip("."))
            label(left - 10, y, tick, anchor="e", tags=("y-tick",))
        canvas.create_line(left, top, left, bottom, right, bottom, fill=self.MUTED)
        label((left + right) / 2, height - 5, "Episode", anchor="s")
        if not history:
            label((left + right) / 2, (top + bottom) / 2,
                  "Complete an episode to see its result.", anchor="center")
            return

        episodes = [result["episode"] for result in history]
        first, last = min(episodes), max(episodes)
        if first == last:
            first, last = first - 0.5, last + 0.5

        def x_position(episode):
            return left + (episode - first) / (last - first) * (right - left)

        tick_episodes = sorted({episodes[round(i * (len(episodes) - 1) / 4)] for i in range(5)})
        for episode in tick_episodes:
            x = x_position(episode)
            canvas.create_line(x, bottom, x, bottom + 4, fill=self.MUTED)
            label(x, bottom + 7, str(episode), anchor="n", tags=("x-tick",))
        points = [(x_position(result["episode"]), y_position(result[key])) for result in history]
        if len(points) > 1:
            canvas.create_line(*(coordinate for point in points for coordinate in point),
                                fill=color, width=2, tags=("history-line",))
        # Keep large histories light while retaining a visible most recent result.
        for x, y in points if len(points) <= 40 else points[-1:]:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color,
                                outline=color, tags=("history-point",))
        latest = f"#{values[-1]}" if key == "rank" else f"{values[-1]:+g}"
        label(right, 8, f"Latest: {latest}", anchor="ne")

    def _wait_for_event(self):
        started = time.monotonic()
        while not self.closed:
            if self.paused:
                if self._advance:
                    self._advance = False
                    break
            elif time.monotonic() - started >= self.env.render_delay:
                break
            self.root.update()
            if not self.closed:
                time.sleep(0.01)

    def toggle_pause(self):
        if self.closed:
            return
        self.paused = not self.paused
        self._advance = False
        self.pause_button.configure(text="Resume" if self.paused else "Pause")
        self.step_button.configure(state="normal" if self.paused else "disabled")
        self.status.configure(text=("PAUSED | " if self.paused else "") +
                              self.env.training_progress["phase"].upper())

    def next_event(self):
        if self.paused:
            self._advance = True

    def _set_delay(self, value):
        self.env.render_delay = float(value)

    def finish_training(self):
        self.paused = False
        self._advance = False
        self.pause_button.configure(state="disabled", text="Pause")
        self.step_button.configure(state="disabled")
        self.footer.configure(text="Close when finished inspecting results.")
        self.refresh(wait=False)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.paused = False
        self.root.after_cancel(self._timing_after_id)
        self.root.destroy()

    def _active_seat(self):
        env = self.env
        if env.game_over or not env.players:
            return None
        if env.bidding_stage and env.current_bidder is not None:
            for offset in range(4):
                seat = (env.current_bidder + offset) % 4
                if env.players[seat].bidded is None:
                    return seat
        if env.playing_stage and len(env.played_cards) < 4:
            seat = env.current_player
            if seat in env.played_by:
                seat = (seat + 1) % 4
            return seat
        return None

    def _text(self, x, y, text, size=11, color=None, anchor="nw", bold=False, **kwargs):
        self.canvas.create_text(x, y, text=text, fill=color or self.TEXT,
                                font=("Segoe UI", size, "bold" if bold else "normal"),
                                anchor=anchor, **kwargs)

    def _draw_board(self):
        if self.closed:
            return
        env = self.env
        c = self.canvas
        c.delete("all")
        width, height = max(700, c.winfo_width()), max(600, c.winfo_height())
        phase = "GAME COMPLETE" if env.game_over else (
            "BIDDING" if env.bidding_stage else "PLAYING" if env.playing_stage else "READY")
        self._text(18, 10, f"Round {min(env.round or 0, 13)} / 13  |  {phase}",
                   size=13, color=self.ACCENT, bold=True)
        self._text(18, 35, f"Trump: {env._suit_name(env.triumph_suit)}", color=self.MUTED)
        active = self._active_seat()
        if active is not None:
            self._text(width - 18, 35, f"P{active} to {'bid' if env.bidding_stage else 'play'}",
                       color=self.ACCENT, anchor="ne")
        gap = 14
        panel_width = (width - 36 - gap) / 2
        # Clockwise: P0 (bottom right), P1 (bottom left), P2 (top left), P3 (top right).
        for seat, x, y in ((2, 18, 65), (3, 18 + panel_width + gap, 65),
                           (1, 18, height - 195), (0, 18 + panel_width + gap, height - 195)):
            if seat < len(env.players):
                self._draw_player(seat, x, y, panel_width, active)

        center_x, center_y = width / 2, (245 + height - 195) / 2
        c.create_oval(45, 252, width - 45, height - 202,
                      fill="#1e6650", outline="#65b89c", width=2)
        completed = sum(player.won for player in env.players)
        trick = min(completed + 1, env.round or 1, 13)
        if len(env.played_cards) == 4:
            trick = completed
        self._text(center_x, center_y - 65,
                   f"CURRENT TRICK {trick} / {min(env.round or 0, 13)}",
                   size=10, anchor="n", color="#b7e4d2", bold=True)
        for index, (seat, card) in enumerate(zip(env.played_by, env.played_cards)):
            x = center_x - 120 + index * 64
            self._text(x + 25, center_y - 43, f"P{seat}", size=9, anchor="n")
            self._draw_card(x, center_y - 24, card, 50, 58)
        if not env.played_cards:
            self._text(center_x, center_y - 8,
                       "Waiting for bids" if env.bidding_stage else
                       "Game finished" if env.game_over else "Waiting for the lead",
                       color="#b7e4d2", anchor="n")
        if env.last_trick:
            cards, winner = env.last_trick
            summary = "  ".join(f"P{seat}: {env._card_name(card)}" for seat, card in cards)
            self._text(center_x, center_y + 48, f"Last: {summary}  |  Winner: P{winner}",
                       size=9, color=self.MUTED, anchor="n")

    def _draw_player(self, seat, x, y, width, active):
        env, c = self.env, self.canvas
        player = env.players[seat]
        is_agent = seat == env.agent_position
        border = self.ACCENT if seat == active else "#65b89c" if is_agent else "#36515d"
        c.create_rectangle(x, y, x + width, y + 180, fill=self.PANEL,
                           outline=border, width=3 if seat == active else 1)
        role = "AI AGENT" if is_agent else "COMPUTER"
        self._text(x + 12, y + 10, f"P{seat}  |  {role}", size=11, bold=True,
                   color=self.ACCENT if is_agent else self.TEXT)
        bid = "-" if player.bidded is None else player.bidded
        self._text(x + 12, y + 33,
                   f"Bid: {bid}    Tricks: {player.won}    Score: {env.scores[seat]:+d}",
                   size=10, color=self.MUTED)
        cards = sorted(player.hand)
        spacing = min(50, (width - 24 - 40) / 6)
        for index, card in enumerate(cards):
            row, col = divmod(index, 7)
            self._draw_card(x + 12 + col * spacing, y + 57 + row * 57, card, 40, 51)
        if not cards:
            self._text(x + 12, y + 72, "No cards remaining", size=10, color=self.MUTED)

    def _draw_card(self, x, y, card, width, height):
        c = self.canvas
        suit = card // 13
        rank = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")[card % 13]
        symbol = ("\u2663", "\u2666", "\u2665", "\u2660")[suit]
        color = "#b83343" if suit in (1, 2) else "#17232b"
        c.create_rectangle(x, y, x + width, y + height, fill="#f5f1e8",
                           outline=self.ACCENT if suit == self.env.triumph_suit else "#d9cdb8",
                           width=2 if suit == self.env.triumph_suit else 1)
        self._text(x + 5, y + 2, rank, size=11, color=color, bold=True)
        self._text(x + width / 2, y + height - 7, symbol, size=18,
                   color=color, anchor="s")
