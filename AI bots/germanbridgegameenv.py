import random
import gymnasium as gym
import numpy as np
import torch
from gymnasium.spaces import Discrete, Tuple, Dict, Box, MultiBinary, MultiDiscrete
from helpers import *
from player import AIBot, ComputerBot



class GermanBridgeGameEnv(gym.Env):
    def __init__(self):
        super().__init__()
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

        # Reset the current player to the first player
        self.current_bidder = 0
        for i in range(4):
            self.players[i].hand = []  # Clear the hand of each player
            self.players[i].bidded = 0  # Reset the bid of each player
            self.players[i].won = 0  # Reset the won tricks of each player

        for i in range(13):
            self.round = i + 1  # Update the round number
            # print('self.round', self.round, 'testing')
            self._deal_round(i+1)  # Deal a round of cards to each player
            self.bidding_stage = True  # Set the bidding stage to True
            self.playing_stage = False  # Set the playing stage to False

            self.current_bidder = (i + 1) % 4  # Update the current bidder
            for j in range(4):
                if self.current_bidder == self.agent_position:
                    # The agent will make a bid based on its policy
                    return self.get_observation(), {}  # Return the observation for the agent's turn to bid
                else:
                    # The computer bot will make a bid
                    self.players[self.current_bidder].bid(i+1)  # Example: Random bid between 0 and n
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
            self.current_bidder = (self.current_bidder + 1) % 4  # Move to the next bidder
            # while True:
            #     self.current_bidder = (self.current_bidder + 1) % 4  # Move to the next bidder
            #     if self.players[self.current_bidder].bidded == 0 and not isinstance(self.players[self.current_bidder], AIBot):
            #         self.players[self.current_bidder].bid(n=action)  # Example: Random bid between 0 and n
            #     else:
            #         break

            bid_result = self._bid_round()  # Conduct a bidding round where each player makes a bid
            assert(bid_result is None, "Bidding round did return an observation.")
            assert(all(x.bidded is not None for x in self.players)), "Not all players have made a bid."
            self.bidding_stage = False  # Set the bidding stage to False
            self.playing_stage = True  # Set the playing stage to True

            self.current_player = self.round % 4
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
            assert(play_result is not None, "Playing round did return an observation.")
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
            # The action is a card play
            played_card = action - 14
            # print(played_card, self.players[self.current_player].hand, 'played card and hand')
            self.players[self.current_player].hand.remove(played_card)  # Remove the played card from the player's hand
            self.played_cards.append(played_card)  
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
            assert(play_result is None, "Playing round did return an observation.")

            winning_card = self._find_winning_card()  # Determine the winning card of the round
            winning_player = self.played_cards.index(winning_card)  # Determine the winning player of the round
            self.players[winning_player].won += 1  # Update the won tricks of the winning player
            reward = 0
            if winning_player == self.agent_position:
                if self.players[self.agent_position].won <= self.players[self.agent_position].bidded:
                    reward = 1  # Reward the agent for winning the round
                else:
                    reward = -1  # Penalize the agent for losing the round
            
            self.current_player = winning_player  # Set the current player to the winning player for the next round
            
            self.played_cards = []  # Clear the played cards for the next round

            if self.players[self.agent_position].hand == []:

                for i in range(4):
                    self.scores[i] += self._calculate_score(self.players[i].bidded, self.players[i].won)  # Calculate the score for each player
                
                self.bidding_stage = True  # Set the bidding stage to True for the next round
                self.playing_stage = False  # Set the playing stage to False for the next round
                self.round += 1  # Increment the round number
                if self.round > 13:
                    self.game_over = True  # Set the game over flag to True if all rounds are completed
                    print('Agent position:', self.agent_position)
                    print(self.scores, 'scores after round', self.round-1)
                    print('Agent score:', self.scores[self.agent_position])
                    return self.get_observation(), 0, True, False, {}  # Return the final observation and done flag
                else:
                    self._deal_round(self.round)  # Deal a new round of cards to each player
                    for i in range(4):
                        self.players[i].bidded = None  # Reset the bid of each player for the new round
                        self.players[i].won = 0  # Reset the won tricks of each player for the new round
                    self.current_bidder = self.round % 4  # Set the current bidder for the new round
                    bid_result = self._bid_round()  # Conduct a bidding round where each player makes a bid
                    # print('debug', bid_result, self.get_observation())
                    return bid_result, reward, self.game_over, False, {}  # Return the observation for the agent's turn to bid
            else:
                play_result = self._play_round()  # Conduct a playing round where each player plays a card
                return play_result, reward, self.game_over, False, {}  # Return the observation
        assert(True), "Step function did not return an observation."

    def render(self, mode='human'):
        # Logic to render the game state
        pass

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
                    self.players[self.current_bidder].bid(n=self.round)  # Example: Random bid between 0 and n
                else:
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
                self.current_player = (self.current_player + 1) % 4  # Move to the next player
            else:
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