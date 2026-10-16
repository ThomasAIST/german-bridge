import random
import time
from collections import deque
import gymnasium as gym
import numpy as np
import torch
from gymnasium.spaces import Discrete, Tuple, Dict, Box, MultiBinary, MultiDiscrete
from helpers import *
from player import AIBot, ComputerBot



class GermanBridgeGameEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(self, render_mode=None, render_delay=1.0, charts_only=False):
        super().__init__()
        if render_mode not in (None, "human"):
            raise ValueError("render_mode must be None or 'human'")
        self.render_mode = render_mode
        self.render_delay = max(0.0, float(render_delay))
        self.charts_only = bool(charts_only)
        self._last_gui_update = None
        self._gui = None
        self._viewer_closed = False
        self.recent_events = deque(maxlen=10)
        self.episode_history = []  # Final AI score and rank for each completed game
        self._episode_result_recorded = False
        self._training_started_at = None
        self._training_finished_at = None
        self._last_episode_finished_at = None
        self._completed_training_episodes = 0
        self._terminal_status = None
        self._last_terminal_update = None
        self.training_progress = {"phase": "Data collection", "episode": None,
                                  "total_episodes": None, "steps": 0,
                                  "episode_reward": 0.0, "last_reward": None}
        self.action_space = Discrete(14+52)  # Example: 52 possible actions (cards)
        # self.observation_space = Dict({
        #     'hand': MultiBinary(52),  # Example: 13 cards in hand
        #     # 'triumph_suit': Discrete(4),  # Example: 4 possible triumph suits
        #     'bids of previous players': Box(low=0, high=1, shape=(4,), dtype=float),  # Example: Bids of previous players
        #     'players scores': Box(low=0, high=1, shape=(4,), dtype=float),  # Example: Scores of all players
        #     'playing positions': Discrete(4),  # Example: Positions of all players
        #     'own bid/wins': Box(low=0, high=1, shape=(3,), dtype=float),  # Example: Own bid
        #     'cards played by previous players': MultiDiscrete([52, 52, 52, 52]),  # Example: Cards played by previous players
        #     'previous hands of other players': MultiBinary((3, 52)),  # Example: Previous hands of other players
        #     # Add more observation space elements as needed
        # })
        self.observation_space = Dict({
            'hand': MultiBinary(52),  # Example: 13 cards in hand
            'context': Box(low=-1, high=1, shape=(4+4+4+3,), dtype=float),  # Example: Context features
            'previous': Tuple((MultiBinary(52), MultiBinary(52), MultiBinary(52), Box(low=-1, high=1, shape=(3, 52), dtype=float))),  # Example: Previous hands and played cards       
            'phase': Discrete(2),  # Example: Phase of the game (0 for bidding, 1 for playing)
            'round': Discrete(13),  # Example: Round number
            'triumph_suit': Discrete(4),  # Example: Triumph suit
            'fixed_suit': Discrete(4),  # Example: Fixed suit
            'own hand': MultiBinary(52),  # Example: Own hand
            'players bids': MultiBinary(14),  # Example: Bids of all players
        })

        # Additional attributes for the game state
        self.deck = list(range(52))  # Reset the deck of cards
        
        self.players = []  # List to hold the players in the game
        self.agent_position = None  # Randomly choose a position for the agent

        self.current_bidder = None  # Track the current bidder
        self.current_player = None  # Track the current player

        self.bidding_stage = False
        self.playing_stage = False

        self.round = None
        self.scores = [None] * 4  # Initialize scores for each player

        self.played_cards = []  # List to hold the cards played in the current round
        self.played_by = []  # Seat corresponding to each card in the current trick
        self.last_trick = None
        self.triumph_suit = None  # Track the triumph suit for the current round

        self.game_over = False

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # Logic to reset the game state

        # Reset the list of players
        self.players = []
        self.scores = [0] * 4  # Reset scores for each player

        # Randomly choose a position for the agent
        self.agent_position = random.randint(0, 3)  
        # print('Agent position:', self.agent_position)
        for i in range(4):
            if i == self.agent_position:
                self.players.append(AIBot())  # Add an AI bot player
            else:
                self.players.append(ComputerBot())  # Add a computer bot player

        self.game_over = False  # Reset the game over flag
        self._episode_result_recorded = False
        self.played_cards = []
        self.played_by = []
        self.last_trick = None
        self.current_player = None
        self.recent_events.clear()
        self.training_progress.update(steps=0, episode_reward=0.0, last_reward=None)

        # Reset the current player to the first player
        self.current_bidder = 0
        for i in range(4):
            self.players[i].hand = []  # Clear the hand of each player
            self.players[i].bidded = None  # None means this player has not bid yet
            self.players[i].won = 0  # Reset the won tricks of each player

        for i in range(13):
            self.round = i + 1  # Update the round number
            # print('self.round', self.round, 'testing')
            self._deal_round(i+1)  # Deal a round of cards to each player
            self.bidding_stage = True  # Set the bidding stage to True
            self.playing_stage = False  # Set the playing stage to False

            self.current_bidder = (i + 1) % 4  # Update the current bidder
            self._render_event(f"Round {self.round}: dealt {self.round} card(s) each.")
            for j in range(4):
                if self.current_bidder == self.agent_position:
                    # The agent will make a bid based on its policy
                    self._render_event()
                    return self.get_observation(), {}  # Return the observation for the agent's turn to bid
                else:
                    # The computer bot will make a bid
                    current_total = sum(p.bidded for p in self.players if p.bidded is not None)
                    self.players[self.current_bidder].bid(i+1, current_total=current_total)
                    self._render_event(f"P{self.current_bidder} bids {self.players[self.current_bidder].bidded}.")
                self.current_bidder = (self.current_bidder + 1) % 4  # Move to the next bidder
                # print('self.current_bidder', self.current_bidder)

    def step(self, action):
        # print('self.round', self.round)
        # Logic to take a step in the game based on the action taken
        assert(self.bidding_stage ^ self.playing_stage), "Game is not in a valid stage for stepping."
        # print(action)
        if action < 14:
            assert(self.bidding_stage), "Action is a bid, but the game is not in the bidding stage."
            # print(self.current_bidder, self.agent_position, 'current bidder and agent position')
            assert(self.current_bidder == self.agent_position), "It's not the agent's turn to bid."
            # The action is a bid
            self.players[self.current_bidder].bidded = action
            if all(x.bidded is not None for x in self.players):
                assert sum(x.bidded for x in self.players) != self.round, "Total bids exceed the number of cards in the round."
            self._render_event(f"P{self.current_bidder} (AI) bids {action}.")
            self.current_bidder = (self.current_bidder + 1) % 4  # Move to the next bidder
            # while True:
            #     self.current_bidder = (self.current_bidder + 1) % 4  # Move to the next bidder
            #     if self.players[self.current_bidder].bidded == 0 and not isinstance(self.players[self.current_bidder], AIBot):
            #         self.players[self.current_bidder].bid(n=action)  # Example: Random bid between 0 and n
            #     else:
            #         break

            bid_result = self._bid_round()  # Conduct a bidding round where each player makes a bid
            assert bid_result is None, "Bidding round did return an observation."
            assert(all(x.bidded is not None for x in self.players)), "Not all players have made a bid."
            self.bidding_stage = False  # Set the bidding stage to False
            self.playing_stage = True  # Set the playing stage to True

            # Bidding starts at round % 4; the next clockwise seat leads play.
            self.current_player = (self.round + 1) % 4
            self._render_event("Bidding complete. Playing tricks.")
            play_result = self._play_round()  # Conduct a playing round where each player plays a card
            # print(play_result, 'play result', len(play_result), len(self.observation_space.spaces))
            # tem = {
            #     'hand': play_result['hand'],
            #     'context': play_result['context'],
            #     'previous': play_result['previous'],
            #     'phase': play_result['phase'],
            #     'round': play_result['round'],
            #     'triumph_suit': play_result['triumph_suit'],
            #     'fixed_suit': play_result['fixed_suit']
            # }
            assert play_result is not None, "Playing round did return an observation."

            num_triumph_cards = sum(1 for card in self.played_cards if card // 13 == self.triumph_suit)
            reward = 0.5 if max(0, num_triumph_cards-2) <= action <= min(self.round, num_triumph_cards+2) else -0.5  # Reward for bidding close to the number of triumph cards played

            return play_result, 0, self.game_over, False, {}  # Return the observation for the agent's turn to play a card
            # for i in range(4):
            #     if self.current_player == self.agent_position:
            #         # The agent will play a card based on its policy
            #         return self.get_observation(), 0, False, False, {}
            #     else:
            #         # The computer bot will play a card
            #         played_card = self.players[self.current_player].play_card(played_cards=[], triumph_suit=None)  # Example: Randomly choose a card from hand
            #         self.played_cards.append(played_card)

            #     self.current_player = (self.current_player + 1) % 4  # Move to the next player
        else:
            assert(self.playing_stage), "Action is a card play, but the game is not in the playing stage."
            assert(self.current_player == self.agent_position), "It's not the agent's turn to play a card."
            assert(action>=14 and action<66), "Action is not a valid card play."
            assert(action-14 in self.players[self.agent_position].hand), "Action is not a card in the agent's hand."
            # The action is a card play
            played_card = action - 14
            # print(played_card, self.players[self.current_player].hand, 'played card and hand')
            self.players[self.current_player].hand.remove(played_card)  # Remove the played card from the player's hand
            self.played_cards.append(played_card)  
            self.played_by.append(self.current_player)
            self._render_event(f"P{self.current_player} (AI) plays {self._card_name(played_card)}.")
            # Update the game state with the played card
            # while True:
            #     self.current_player = (self.current_player + 1) % 4  # Move to the next player
            #     if self.current_player != self.agent_position:
            #         played_card = self.players[self.current_player].play_card(played_cards=[], triumph_suit=None)  # Example: Randomly choose a card from hand
            #         self.played_cards.append(played_card)  # Update the game state with the played card
            #     else:
            #         break
            self.current_player = (self.current_player + 1) % 4  # Move to the next player
            play_result = self._play_round()  # Conduct a playing round where each player plays a card
            assert play_result is None, "Playing round did return an observation."

            winning_card = self._find_winning_card()  # Determine the winning card of the round
            winning_player = self.played_by[self.played_cards.index(winning_card)]
            self.players[winning_player].won += 1  # Update the won tricks of the winning player
            reward = 0
            if winning_player == self.agent_position:
                if self.players[self.agent_position].won <= self.players[self.agent_position].bidded:
                    reward = 0.5  # Reward the agent for progressing towards their bid
                else:
                    reward = -0.5  # Penalize the agent for losing the round
            
            self.current_player = winning_player  # Set the current player to the winning player for the next round
            self.last_trick = (tuple(zip(self.played_by, self.played_cards)), winning_player)
            self._render_event(f"P{winning_player} wins trick {sum(p.won for p in self.players)} with {self._card_name(winning_card)}.")
            
            self.played_cards = []  # Clear the played cards for the next round
            self.played_by = []

            if self.players[self.agent_position].hand == []:
                # reward = self._calculate_score(self.players[self.agent_position].bidded, self.players[self.agent_position].won)  # Calculate the score for the agent
                # reward = 0.8 if self.players[self.agent_position].won == self.players[self.agent_position].bidded else -0.8
                for i in range(4):
                    self.scores[i] += self._calculate_score(self.players[i].bidded, self.players[i].won)  # Calculate the score for each player
                self._render_event(f"Round {self.round} finished. Scores: {self.scores}.")
                
                self.bidding_stage = True  # Set the bidding stage to True for the next round
                self.playing_stage = False  # Set the playing stage to False for the next round
                self.round += 1  # Increment the round number
                if self.round > 13:
                    self.game_over = True  # Set the game over flag to True if all rounds are completed
                    self._record_episode_result()
                    self._render_event("Game complete.")
                    reward = 1 if self.scores[self.agent_position] >= max(150, max(self.scores)) else -1  # Reward the agent for winning the game
                    return self.get_observation(), reward, True, False, {}  # Return the final observation and done flag
                else:
                    self._deal_round(self.round)  # Deal a new round of cards to each player
                    for i in range(4):
                        self.players[i].bidded = None  # Reset the bid of each player for the new round
                        self.players[i].won = 0  # Reset the won tricks of each player for the new round
                    self.current_bidder = self.round % 4  # Set the current bidder for the new round
                    self._render_event(f"Round {self.round}: dealt {self.round} card(s) each.")
                    bid_result = self._bid_round()  # Conduct a bidding round where each player makes a bid
                    # print('debug', bid_result, self.get_observation())
                    return bid_result, self.scores[self.agent_position]/949, self.game_over, False, {}  # Return the observation for the agent's turn to bid
            else:
                play_result = self._play_round()  # Conduct a playing round where each player plays a card
                num_triumph_cards = sum(1 for card in self.played_cards if card // 13 == self.triumph_suit)
                reward = 0.5 if max(0, num_triumph_cards-2) <= action <= min(self.round, num_triumph_cards+2) else -0.5  # Reward for bidding close to the number of triumph cards played
                return play_result, 0, self.game_over, False, {}  # Return the observation
        assert(True), "Step function did not return an observation."

    def _record_episode_result(self):
        """Keep completed results across resets, with shared ranks for ties."""
        if not self.game_over or self._episode_result_recorded:
            return
        score = self.scores[self.agent_position]
        self.episode_history.append({
            "episode": self.training_progress["episode"] or len(self.episode_history) + 1,
            "score": score,
            "rank": 1 + sum(other_score > score for other_score in self.scores),
            "reward": None,  # Filled after collection and optimizer updates finish
        })
        self._episode_result_recorded = True

    def render(self):
        """Show the observer window; game events call this automatically."""
        if self.render_mode != "human" or self._viewer_closed:
            return
        if self._gui is None:
            from training_gui import GermanBridgeTrainingGUI
            self._gui = GermanBridgeTrainingGUI(self)
        if not self._gui.closed:
            self._gui.refresh(wait=not self.charts_only)
            self._last_gui_update = time.monotonic()

    def _refresh_gui_progress(self, force=False):
        if self.render_mode != "human" or self._viewer_closed:
            return
        if self.charts_only:
            # Service the charts at most four times per second during collection.
            # Episode completion bypasses this throttle so results appear immediately.
            if (not force and self._gui is not None and self._last_gui_update is not None
                    and time.monotonic() - self._last_gui_update < 0.25):
                return
            self.render()
        elif self._gui is not None and not self._gui.closed:
            self._gui.refresh(wait=False)

    def set_training_progress(self, *, episode=None, total_episodes=None,
                              phase=None, steps=None, episode_reward=None,
                              last_reward=None):
        """Update collection metrics without adding an animation delay."""
        phase_changed = phase is not None and phase != self.training_progress["phase"]
        episode_changed = episode is not None and episode != self.training_progress["episode"]
        updates = {"episode": episode, "total_episodes": total_episodes,
                   "phase": phase, "steps": steps,
                   "episode_reward": episode_reward, "last_reward": last_reward}
        self.training_progress.update({key: value for key, value in updates.items()
                                       if value is not None})
        self._refresh_gui_progress()
        if self._training_started_at is not None and self._training_finished_at is None:
            self.print_training_timing(force=phase_changed or episode_changed)

    def start_training_timer(self):
        """Start a new run's wall clock, including collection and model updates."""
        if self._terminal_status is not None:
            self._terminal_status.finish()
        self._terminal_status = None
        self._last_terminal_update = None
        self._training_started_at = time.monotonic()
        self._training_finished_at = None
        self._last_episode_finished_at = None
        self._completed_training_episodes = 0

    def finish_training_episode(self):
        """Call after the episode's optimizer updates, not just after game over."""
        if self._training_started_at is None or self._training_finished_at is not None:
            return
        self._last_episode_finished_at = time.monotonic()
        self._completed_training_episodes += 1
        if self.game_over and self._episode_result_recorded:
            self.episode_history[-1]["reward"] = float(self.training_progress["episode_reward"])
        self.training_progress["phase"] = "Episode complete"
        self._refresh_gui_progress(force=True)
        self.print_training_timing()

    def record_episode_reward(self, reward):
        """Preserve the collected return even if model updates are interrupted."""
        if self.game_over and self._episode_result_recorded:
            self.episode_history[-1]["reward"] = float(reward)
            self._refresh_gui_progress(force=True)

    def finish_training(self, phase="Training complete"):
        """Stop timing but leave the observer available for inspection and saving."""
        if self._training_started_at is not None and self._training_finished_at is None:
            self._training_finished_at = time.monotonic()
        self.set_training_progress(phase=phase)
        if self._gui is not None and not self._gui.closed:
            self._gui.finish_training()
        self.print_training_timing(final=True)

    def print_training_timing(self, force=True, final=False):
        """Replace one status display, including when no GUI is enabled."""
        now = time.monotonic()
        if not force and self._last_terminal_update is not None and now - self._last_terminal_update < 0.25:
            return
        elapsed, average = self.get_training_timing()
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        average_text = "--" if average is None else f"{average:.2f} s"
        progress = self.training_progress
        episode = progress["episode"] or self._completed_training_episodes or "-"
        total = f"/{progress['total_episodes']}" if progress["total_episodes"] is not None else ""
        phase = progress["phase"]
        if phase == "Data collection":
            phase = f"Collecting {progress['steps']}/104"
        last_reward = "--" if progress["last_reward"] is None else f"{progress['last_reward']:+.2f}"
        message = (f"Episode {episode}{total} | {phase}\n"
                   f"Samples: {progress['steps']}/104 | Episode reward: {progress['episode_reward']:+.2f} | "
                   f"Last reward: {last_reward}\n"
                   f"Avg episode: {average_text} | "
                   f"Total elapsed: {hours:02d}:{minutes:02d}:{seconds:02d} ({elapsed:.2f} s)")
        if self._terminal_status is None:
            from training_status import TrainingStatus
            self._terminal_status = TrainingStatus()
        self._terminal_status.update(message, final=final)
        self._last_terminal_update = now

    def get_training_timing(self):
        """Return elapsed seconds and the mean for fully completed episodes."""
        if self._training_started_at is None:
            return 0.0, None
        end = self._training_finished_at
        elapsed = (time.monotonic() if end is None else end) - self._training_started_at
        average = None
        if self._completed_training_episodes:
            average = ((self._last_episode_finished_at - self._training_started_at) /
                       self._completed_training_episodes)
        return elapsed, average

    def set_render_speed(self, delay):
        """Seconds per visible event; zero runs as fast as possible."""
        self.render_delay = max(0.0, float(delay))
        if self._gui is not None and not self._gui.closed:
            self._gui.delay.set(self.render_delay)

    def close(self):
        if self._terminal_status is not None:
            self._terminal_status.finish()
        if self._training_started_at is not None and self._training_finished_at is None:
            self._training_finished_at = time.monotonic()
        self._viewer_closed = True
        if self._gui is not None:
            self._gui.close()

    def _render_event(self, message=None):
        if self.render_mode == "human" and not self.charts_only:
            if message:
                self.recent_events.append(message)
            self.render()

    @staticmethod
    def _suit_name(suit):
        return "-" if suit is None or suit < 0 else ("Clubs", "Diamonds", "Hearts", "Spades")[suit]

    @staticmethod
    def _suit_symbol(suit):
        return ("C", "D", "H", "S")[suit]

    @classmethod
    def _card_name(cls, card):
        ranks = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
        return f"{ranks[card % 13]}{cls._suit_symbol(card // 13)}"

    def get_observation(self):
        assert(self.bidding_stage ^ self.playing_stage), "Game is not in a valid stage for observation."
        # Logic to get the current observation of the game state
        if self.bidding_stage:
            # Return the observation for the bidding stage
            # state = {
            #     'hand': self._hand_to_tensor(self.players[self.agent_position].hand, triumph_suit=None),  # Assuming triumph_suit is not relevant during bidding
            #     'bids of previous players': [x.bidded/self.round for x in self.players],
            #     'players scores': torch.softmax(torch.tensor(self.scores, dtype=torch.float32), dim=0).numpy(),
            #     'playing positions': self.agent_position,
            #     'own bid/wins': [0] * 3,  # Assuming the third value is not relevant during bidding
            #     'cards played by previous players': [0] * 4,  # Assuming the last card in hand is the last played card
            #     'previous hands of other players': torch.full((3, 52), 0, dtype=torch.float32),  # Fill with -1 for players who didn't play
            # }
            state = {
                'hand': hand_to_tensor(self.players[self.agent_position].hand, triumph_suit=None),
                'context': context_to_tensor([x.bidded for x in self.players], self.scores, self.agent_position, self.round),
                'previous': {'hand1': torch.full((1, 52), -1, dtype=torch.float32),
                              'hand2': torch.full((1, 52), -1, dtype=torch.float32),
                              'hand3': torch.full((1, 52), -1, dtype=torch.float32),
                              'played_cards': torch.zeros((1, 52), dtype=torch.float32)},  # Fill with -1 for players who didn't play
                'phase': 0,  # Bidding phase
                'round': self.round,
                'triumph_suit': self.triumph_suit if self.triumph_suit is not None else -1,
                'fixed_suit': self.played_cards[0] // 13 if self.played_cards != [] else -1,
                'own hand': [x for x in self.players[self.agent_position].hand],
                'players bids': [x.bidded for x in self.players if x.bidded is not None]
            }
        elif self.playing_stage:
            # self.padded_played_cards = self.played_cards[:]
            # while len(self.padded_played_cards) < 4:
            #     self.padded_played_cards.append(-1)  # Fill with -1 for players who didn't play
            # # Return the observation for the playing stage
            # state = {
            #     'hand': self._hand_to_tensor(self.players[self.agent_position].hand, triumph_suit=self.triumph_suit),  # Assuming triumph_suit is not relevant during bidding
            #     'bids of previous players': [x.bidded/self.round for x in self.players],
            #     'players scores': torch.softmax(torch.tensor(self.scores, dtype=torch.float32), dim=0).numpy(),
            #     'playing positions': self.agent_position,
            #     'own bid/wins': [self.players[self.agent_position].bidded/self.round, self.players[self.agent_position].won/self.round, (self.players[self.agent_position].bidded-self.players[self.agent_position].won)/self.round],  # Assuming the third value is not relevant during bidding
            #     'cards played by previous players': self.padded_played_cards,  # Assuming the last card in hand is the last played card
            #     'previous hands of other players': torch.stack([self._hand_to_tensor(player.hand, triumph_suit=self.triumph_suit) for player in self.players if player != self.players[self.agent_position]]),  # Fill with -1 for players who didn't play
            # }
            previous_hands, previous_cards = previous_to_tensors([x.hand for x in self.players], self.played_cards, self.triumph_suit, self.agent_position, max_previous_hand_length=self.round-max(len(x.hand) for x in self.players if not isinstance(x, AIBot)))
            # print(previous_hands, 'previous hands')
            # print(previous_cards, 'previous cards')
            assert(self.players[self.agent_position].hand !=[]), "Agent's hand is None."
            state = {
                'hand': hand_to_tensor(self.players[self.agent_position].hand, triumph_suit=self.triumph_suit),
                'context': context_to_tensor([x.bidded for x in self.players], self.scores, self.agent_position, self.round, self.players[self.agent_position].bidded, self.players[self.agent_position].won),
                'previous': {'hand1': previous_hands[0], 'hand2': previous_hands[1], 'hand3': previous_hands[2], 'played_cards': previous_cards},
                'phase': 1,  # Playing phase
                'round': self.round,
                'triumph_suit': self.triumph_suit if self.triumph_suit is not None else -1,
                'fixed_suit': self.played_cards[0] // 13 if self.played_cards != [] else -1,
                'own hand': [x for x in self.players[self.agent_position].hand],
                'players bids': [x.bidded for x in self.players]
            }
        state['action_mask'] = self._make_action_mask(state)
        assert(state is not None), "Observation state is None."
        return state

    def _hand_to_tensor(self, hand, triumph_suit):
        """
        Convert a hand of cards into a tensor representation.
        
        Args:
            hand (list): A list of card values in the player's hand.
            triumph_suit (int): The suit of the trump cards (0-3).

        Returns:
            np.ndarray: A tensor representation of the hand.
        """
        tensor = np.zeros((len(hand), 52), dtype=np.float32)  # Adjust size based on context features
        for i, card in enumerate(hand):
            tensor[i][card] = 1.0  # One-hot encode the card
            if card // 13 == triumph_suit:
                tensor[i][card] += 0.5  # Add a bonus for trump cards
        # print('tensor shape:', tensor.shape, tensor, hand, len(hand), triumph_suit)
        return tensor

    def _deal_round(self, n: int):
        """
        Deal a round of n cards to each player.
        """
        random.shuffle(self.deck)  # Shuffle the deck
        self.last_trick = None
        for i in range(4):
            self.players[i].hand = self.deck[i*n:(i+1)*n]  # Deal n cards to each player
        self.triumph_suit = self.deck[4*n] // 13 if 1 <= n <= 12 else None  # Set the triumph suit for the round
    
    def _bid_round(self):
        """
        Conduct a bidding round where each player makes a bid.
        """
        while True:
            if self.players[self.current_bidder].bidded == None:
                if not isinstance(self.players[self.current_bidder], AIBot):
                    current_total = sum(p.bidded for p in self.players if p.bidded is not None)
                    self.players[self.current_bidder].bid(n=self.round, current_total=current_total)
                    self._render_event(f"P{self.current_bidder} bids {self.players[self.current_bidder].bidded}.")
                else:
                    self._render_event()
                    return self.get_observation()  # Return the observation for the agent's turn to bid
                self.current_bidder = (self.current_bidder + 1) % 4  # Move to the
            else:
                break

    def _play_round(self):
        """
        Conduct a playing round where each player plays a card.
        """
        while len(self.played_cards) < 4:
            if self.current_player != self.agent_position:
                played_card = self.players[self.current_player].play_card(played_cards=self.played_cards, triumph_suit=self.triumph_suit)  # Example: Randomly choose a card from hand
                self.played_cards.append(played_card)  # Update the game state with the played card
                self.played_by.append(self.current_player)
                self._render_event(f"P{self.current_player} plays {self._card_name(played_card)}.")
                self.current_player = (self.current_player + 1) % 4  # Move to the next player
            else:
                self._render_event()
                return self.get_observation()  # Return the observation for the agent's turn to play a card

    def _find_winning_card(self) -> int:
        """
        Determine the winning card from a list of played cards based on the rules of the game.
        
        Args:
            played_cards (list): A list of card indices (0-51) representing the cards played by each player.
            triumph_suit (int): The suit of the trump cards (0-3).
            
        Returns:
            int: The winning card in the played_cards list.
        """
        fixed_suit = self.played_cards[0] // 13
        deck = []
        for i in range(4):
            for j in range(13):
                if i == self.triumph_suit:
                    deck.append(j+13)
                elif i == fixed_suit:
                    deck.append(j)
                else:
                    deck.append(0)
        return max(self.played_cards, key=lambda card: deck[card])

    @staticmethod
    def _calculate_score(bid: int, won: int) -> int:
        """
        Calculate the score for a player based on their bid and the number of tricks won.
        
        Args:
            bid (int): The number of tricks the player bid.
            won (int): The number of tricks the player actually won.
            
        Returns:
            int: The score for the player based on their bid and won tricks.
        """
        if bid == won:
            return 10 + bid**2  # Score is 10 plus the number of tricks if the bid is met
        else:
            return -(abs(bid - won)**2)  # Negative score based on how far off the bid was

    @staticmethod
    def _make_action_mask(state):
        # Actions 0–13: bids; actions 14–65: cards.
        mask = torch.zeros(66, dtype=torch.bool)

        round_number = state['round']
        bids = [bid for bid in state['players bids'] if bid is not None]

        if state['phase'] == 0:
            mask[:round_number + 1] = True

            if len(bids) == 3:
                forbidden_bid = round_number - sum(bids)
                if 0 <= forbidden_bid <= round_number:
                    mask[forbidden_bid] = False
        else:
            cards = torch.tensor(
                [card for card in state['own hand'] if card >= 0],
                dtype=torch.long,
            )
            suits = cards // 13
            fixed_suit = state['fixed_suit']
            trump_suit = state['triumph_suit']

            # Preserve your current rule: when following suit is
            # possible, allow that suit and trump cards.
            if (suits == fixed_suit).any():
                cards = cards[
                    (suits == fixed_suit) | (suits == trump_suit)
                ]

            mask[cards + 14] = True

        return mask
# class Player:
#     def __init__(self, name):
#         self.name = name
#         self.hand = []  # List to hold the player's cards

#     def play_card(self, card):
#         # Logic for the player to play a card
#         pass

#     def receive_card(self, card):
#         # Logic for the player to receive a card
#         self.hand.append(card)


# class AIBot(Player):
#     def __init__(self, name):
#         super().__init__(name)
#         # Additional attributes for AI bot

#     def make_decision(self, game_state):
#         # Logic for the AI bot to make a decision based on the game state
#         pass


# class ComputerBot(Player):
#     def __init__(self, name):
#         super().__init__(name)
#         # Additional attributes for Computer bot

#     def bid(n):
#         return random.randint(0, n)  # Random bid between 0 and 7
