import random


class Player:
    def __init__(self):
        self.hand = []  # List to hold the player's cards
        self.bidded = 0  # The bid made by the player
        self.won = 0  # The number of tricks won by the player

    def bid(self):
        # Logic for the player to make a bid
        pass


class AIBot(Player):
    def __init__(self):
        super().__init__()
        # Additional attributes for AI bot


class ComputerBot(Player):
    def __init__(self):
        super().__init__()
        # Additional attributes for computer bot

    def bid(self, n, current_total=0):
        """Choose a bid without making the running total equal the round size."""
        legal_bids = [bid for bid in range(n + 1) if current_total + bid != n]
        if not legal_bids:
            raise ValueError("No legal bid for this round and current total.")
        self.bidded = random.choice(legal_bids)
        return self.bidded

    def play_card(self, played_cards, triumph_suit):
        assert(len(self.hand) > 0), "No cards left in hand to play."
        # Logic for the computer bot to play a card
        fixed_suit = played_cards[0] // 13 if played_cards != [] else None
        free_play = all(x//13!=fixed_suit for x in self.hand)
        playable_hand = []
        if free_play:
            playable_hand = self.hand[:]  # If free play, all cards are playable
        else:
            for x in self.hand:
                if x//13 == triumph_suit or x//13 == fixed_suit:
                    playable_hand.append(x)
                # elif fixed_suit is not None and x//13==fixed_suit:
                #     playable_hand.append(x)
                # elif fixed_suit is None:
                #     playable_hand.append(x)

        card = random.choice(playable_hand)  # Example: Randomly choose a card from playable hand
        self.hand.remove(card)  # Remove the chosen card from hand
        return card
        # index = random.choice(list(range(len(playable_hand))))  # Example: Randomly choose a card from hand
        # print(played_cards, triumph_suit, fixed_suit, self.hand, playable_hand, index, 'played_cards, triumph_suit, fixed_suit, self.hand, playable_hand, index')
        # return self.hand.pop(index)  # Remove and return the chosen card
