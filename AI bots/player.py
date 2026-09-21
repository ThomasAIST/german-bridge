import random


class Player:
    def __init__(self):
        self.hand = []  # List to hold the player's cards

    def bid(self):
        # Logic for the player to make a bid
        pass

class AIBot(Player):
    def __init__(self):
        super().__init__()
        # Additional attributes for AI bot
        self.bidded = 0
        self.won = 0


class ComputerBot(Player):
    def __init__(self):
        super().__init__()
        # Additional attributes for computer bot

    def bid(self, n):
        # Logic for the computer bot to make a bid
        return random.randint(0, n)  # Example: Random bid between 0 and 7

    def play_card(self, played_cards, triumph_suit):
        # Logic for the computer bot to play a card
        fixed_suit = played_cards[0] // 13 if played_cards != [] else None
        playable_hand = []
        for x in self.hand:
            if x//13 == triumph_suit:
                playable_hand.append(x)
            elif fixed_suit is not None and x//13==fixed_suit:
                playable_hand.append(x)
            elif fixed_suit is None:
                playable_hand.append(x)

        index = random.choice(list(range(len(playable_hand))))  # Example: Randomly choose a card from hand
        return self.hand.pop(index)  # Remove and return the chosen card