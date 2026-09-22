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

    def bid(self, n):
        # Logic for the computer bot to make a bid
        self.bidded = random.randint(0, n)  # Example: Random bid between 0 and n
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

        index = random.choice(list(range(len(playable_hand))))  # Example: Randomly choose a card from hand
        return self.hand.pop(index)  # Remove and return the chosen card