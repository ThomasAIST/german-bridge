import torch



def hand_to_tensor(hand: list[int], triumph_suit: int = None) -> torch.Tensor:
    """ 
    Convert a hand of cards into a tensor representation.
    
    Args:
        hand (list): A list of card indices (0-51) representing the player's hand.
        triumph_suit (int, optional): The suit of the trump cards (0-3). If None, no trump cards are considered.
        
    Returns:
        torch.Tensor: A tensor of shape (len(hand), 52) with 1s for cards in hand and 0s otherwise.
    """
    tensor = torch.zeros((len(hand), 52), dtype=torch.float32)
    for i, card in enumerate(hand):
        tensor[i][card] = 2.0 if card//13 == triumph_suit else 1.0
    # print('tensor shape:', tensor.shape, tensor, hand, len(hand), triumph_suit)
    return tensor

def context_to_tensor(bids: list[int], scores: list[int], playing_position: int, n: int, own_bid: int = None, own_won: int = None) -> torch.Tensor:
    """
    Convert the game context into a tensor representation.
    
    Args:
        bids (list): A list of bid values for each player.
        scores (list): A list of scores for each player.
        playing_position (int): The position of the player in the game (0-3).
        n (int): The current number of rounds in the game.
        own_bid (int, optional): The player's own bid.
        own_won (int, optional): The number of tricks the player has won.

    Returns:
        torch.Tensor: A tensor representation of the game context.
    """
    bid_tensor = torch.zeros(4, dtype=torch.float32)  # Adjust size based on context features
    for i in range(len(bids)):
        bid_tensor[i] = bids[i] / n if bids[i] is not None else -1 # Normalize bids

    score_tensor = torch.nn.functional.softmax(torch.tensor(scores, dtype=torch.float32), dim=0)  # Normalize scores to probabilities

    position_tensor = torch.nn.functional.one_hot(torch.tensor(playing_position), num_classes=4).float()  # One-hot encode the playing position
    tensor = torch.cat((bid_tensor, score_tensor, position_tensor), dim=0)

    if own_bid is not None and own_won is not None:
        own_status = [own_bid / n, own_won / n, (own_bid-own_won) / n]  # Normalize own bid and include own won status
        own_status_tensor = torch.tensor(own_status, dtype=torch.float32)
        tensor = torch.cat((tensor, own_status_tensor), dim=0)
    else:
        tensor = torch.cat((tensor, torch.tensor([-1, -1, -1], dtype=torch.float32)), dim=0)  # Fill with -1 if own bid and won are not provided
    return tensor

def previous_to_tensors(previous_hands: list[int], previous_cards: list[int], triumph_suit: int, playing_position: int, max_previous_hand_length: int) -> tuple[torch.Tensor]:
    """
    Convert the previous round's context into a tensor representation.
    
    Args:
        previous_hands (list): A list of lists, where each inner list contains the cards played by each player in the previous round.
        previous_cards (list): A list of lists, where each inner list contains the cards played by each player in the previous round.
        triumph_suit (int): The suit of the trump cards (0-3).
        playing_position (int): The position of the player in the game (0-3).
        max_previous_hand_length (int): The maximum length of the previous hands to pad the tensors

    Returns:
        tuple[torch.Tensor]: A tuple of tensors representing the previous round's context.
    """
    hand_tensors = []
    for i in range(len(previous_hands)):
        if i != playing_position:
            if previous_hands[i] == []:
                hand_tensors.append(torch.full((1, 52), -1, dtype=torch.float32))  # Fill with -1 for players who didn't play
            else:
                hand_tensors.append(hand_to_tensor(previous_hands[i], triumph_suit=triumph_suit))

    for i in range(len(hand_tensors)):
        if hand_tensors[i].shape[0] < max_previous_hand_length:
            hand_tensors[i] = torch.cat((hand_tensors[i], torch.full((max_previous_hand_length - hand_tensors[i].shape[0], 52), -1, dtype=torch.float32)), dim=0)

    if previous_cards == []:
        card_tensors = torch.zeros((1, 52), dtype=torch.float32)  # Fill with zeros if no cards were played
    else:
        card_tensors = hand_to_tensor(previous_cards, triumph_suit=triumph_suit)
    while len(card_tensors) < 3:
        card_tensors = torch.cat((card_tensors, torch.full((1, 52), -1, dtype=torch.float32)), dim=0)  # Fill with -1 for players who didn't play
    # print(hand_tensors, card_tensors, 'tesint')
    return (hand_tensors, card_tensors)

def find_winning_card(played_cards: list[int], triumph_suit: int) -> int:
    """
    Determine the winning card from a list of played cards based on the rules of the game.
    
    Args:
        played_cards (list): A list of card indices (0-51) representing the cards played by each player.
        triumph_suit (int): The suit of the trump cards (0-3).
        
    Returns:
        int: The winning card in the played_cards list.
    """
    fixed_suit = played_cards[0] // 13
    deck = []
    for i in range(4):
        for j in range(13):
            if i == triumph_suit:
                deck.append(j+13)
            elif i == fixed_suit:
                deck.append(j)
            else:
                deck.append(0)
    return max(played_cards, key=lambda card: deck[card])

def calculate_score(bid: int, won: int) -> int:
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

def calculate_advantages(returns, values):
    advantages = returns - values
    # Normalize the advantage
    advantages = (advantages - advantages.mean()) / advantages.std()
    return advantages

def calculate_returns(rewards, discount_factor):
    returns = []
    cumulative_reward = 0
    for r in reversed(rewards):
        cumulative_reward = r + cumulative_reward * discount_factor
        returns.insert(0, cumulative_reward)
    returns = torch.tensor(returns)
    # normalize the return
    returns = (returns - returns.mean()) / returns.std()
    return returns

def calculate_surrogate_loss(old_log_probs, new_log_probs, epsilon, advantages):
    advantages = advantages.detach()  # Detach advantages to prevent gradients from flowing through them
    policy_ratio = torch.exp(new_log_probs - old_log_probs)
    surrogate1 = policy_ratio * advantages
    surrogate2 = torch.clamp(policy_ratio, 1 - epsilon, 1 + epsilon) * advantages
    return torch.min(surrogate1, surrogate2)

def calculate_losses(surrogate_loss, entropy, entropy_coefficient, returns, critic_values):
    entropy_bonus = entropy_coefficient * entropy
    policy_loss = -(surrogate_loss + entropy_bonus).sum()
    value_loss = torch.nn.functional.smooth_l1_loss(returns, critic_values).sum()
    return policy_loss, value_loss