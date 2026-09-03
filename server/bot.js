// Lightweight heuristic bot. Not game-theoretically optimal, but plays
// sensible, legal, and reasonably competitive German Bridge.
const { legalCards } = require('./gameEngine');

// Estimate how many tricks a hand is likely to win, given trump suit.
// Simple point-count style heuristic:
//  - Each trump card contributes roughly (rank-8)/6 of a trick, floored at 0.05
//  - Each non-trump Ace/King contributes a partial trick
//  - Very short non-trump suits (singleton/void) are worth a bit extra since
//    they can be ruffed with trump later.
function estimateTricks(hand, trumpSuit) {
  const bySuit = {};
  for (const c of hand) {
    bySuit[c.suit] = bySuit[c.suit] || [];
    bySuit[c.suit].push(c);
  }
  let total = 0;
  for (const suit of Object.keys(bySuit)) {
    const cards = bySuit[suit].sort((a, b) => b.rank - a.rank);
    if (suit === trumpSuit) {
      for (const c of cards) total += Math.max(0.15, (c.rank - 7) / 7);
    } else {
      cards.forEach((c, i) => {
        if (i === 0 && c.rank === 14) total += 0.85;
        else if (i === 0 && c.rank === 13) total += 0.5;
        else if (i === 0 && c.rank === 12) total += 0.25;
      });
      if (cards.length === 1) total += 0.2; // ruff potential
      if (cards.length === 0) total += 0.1;
    }
  }
  return total;
}

function botBid(hand, trumpSuit, handSize) {
  const est = estimateTricks(hand, trumpSuit);
  let bid = Math.round(est);
  // small randomness so bots aren't perfectly predictable
  if (Math.random() < 0.15) bid += Math.random() < 0.5 ? 1 : -1;
  return Math.max(0, Math.min(handSize, bid));
}

// Choose a card to play given the current engine state and this bot's id.
function botPlayCard(state, playerId) {
  const hand = state.hands[playerId];
  const legal = legalCards(state, playerId);
  const trump = state.trumpSuit;
  const trickSoFar = state.currentTrick;
  const bid = state.bids[playerId];
  const won = state.tricksWon[playerId];
  const wantsMoreTricks = won < bid;

  if (trickSoFar.length === 0) {
    // Leading: if we still need tricks, lead a strong card (favor trump if
    // we hold a lot of it); if we've made our bid, lead low to avoid
    // winning unwanted tricks.
    const sorted = legal.slice().sort((a, b) => b.rank - a.rank);
    if (wantsMoreTricks) {
      const trumpCards = sorted.filter(c => c.suit === trump);
      return trumpCards.length ? trumpCards[0] : sorted[0];
    }
    return sorted[sorted.length - 1];
  }

  // Following: figure out what currently wins the trick.
  const ledSuit = trickSoFar[0].card.suit;
  let winning = trickSoFar[0].card;
  for (const entry of trickSoFar.slice(1)) {
    winning = cardBeats(entry.card, winning, ledSuit, trump) ? entry.card : winning;
  }

  const canWin = legal.filter(c => cardBeats(c, winning, ledSuit, trump));
  if (wantsMoreTricks && canWin.length) {
    // win as cheaply as possible
    canWin.sort((a, b) => cardStrength(a, ledSuit, trump) - cardStrength(b, ledSuit, trump));
    return canWin[0];
  }
  // don't want to win (or can't): play lowest legal card, preferring to
  // dump non-trump over trump
  const sorted = legal.slice().sort((a, b) => {
    const aTrump = a.suit === trump ? 1 : 0;
    const bTrump = b.suit === trump ? 1 : 0;
    if (aTrump !== bTrump) return aTrump - bTrump;
    return a.rank - b.rank;
  });
  return sorted[0];
}

function cardBeats(card, currentBest, ledSuit, trumpSuit) {
  const cardIsTrump = card.suit === trumpSuit;
  const bestIsTrump = currentBest.suit === trumpSuit;
  if (cardIsTrump && !bestIsTrump) return true;
  if (!cardIsTrump && bestIsTrump) return false;
  if (cardIsTrump && bestIsTrump) return card.rank > currentBest.rank;
  if (card.suit === ledSuit && currentBest.suit === ledSuit) return card.rank > currentBest.rank;
  if (card.suit === ledSuit) return true;
  return false;
}

function cardStrength(card, ledSuit, trumpSuit) {
  if (card.suit === trumpSuit) return 100 + card.rank;
  if (card.suit === ledSuit) return card.rank;
  return 0;
}

module.exports = { botBid, botPlayCard, estimateTricks };
