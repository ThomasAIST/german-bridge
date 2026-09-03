// Core German Bridge rules engine. Pure functions over a state object so it's
// easy to test and easy to reason about. No networking code lives here.
//
// RULES IMPLEMENTED (per standard "German Bridge" / GBridge description):
// - 3-7 players, standard 52 card deck, Aces high, 2s low.
// - The game is played in rounds. Round n deals n cards to each player
//   (round 1 = 1 card each, round 2 = 2 cards each, ...) up to the maximum
//   number of full rounds that can be dealt from a 52 card deck.
// - Each round a trump suit is chosen at random.
// - Starting with the first bidder, every player must bid a number of tricks
//   they intend to win. No passing; 0 is a legal bid. The player after the
//   first bidder starts play, and the completed bid total cannot equal the
//   number of tricks in the round.
// - Play proceeds trick by trick. Trump cards may always be played; non-trump
//   cards must follow the suit led if able. The highest trump wins the trick;
//   if no trump was played, the highest card of the suit led wins.
//   Trick winner leads next.
// - Scoring per round: if a player takes exactly as many tricks as bid,
//   they score 10 + (tricks^2). Otherwise they score -((tricks-bid)^2).
// - After the final round, the highest total score wins.

const SUITS = ['S', 'H', 'D', 'C'];
const SUIT_NAMES = { S: 'Spades', H: 'Hearts', D: 'Diamonds', C: 'Clubs' };
const RANK_NAMES = { 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };
const CLOCKWISE_STEP = -1;
const PLAYER_COUNT = 4;

function rankLabel(r) {
  return RANK_NAMES[r] || String(r);
}

function cardLabel(c) {
  return `${rankLabel(c.rank)}${c.suit}`;
}

function createDeck() {
  const deck = [];
  for (const suit of SUITS) {
    for (let rank = 2; rank <= 14; rank++) {
      deck.push({ suit, rank });
    }
  }
  return deck;
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function maxRounds(numPlayers) {
  return Math.floor(52 / numPlayers);
}

// players: [{id, name, isBot}]
function createGame(gameId, players, options = {}) {
  if (players.length !== PLAYER_COUNT) {
    throw new Error(`German Bridge requires exactly ${PLAYER_COUNT} players.`);
  }
  const totalRounds = options.totalRounds || maxRounds(players.length);
  return {
    id: gameId,
    players: players.map((p, seat) => ({ ...p, seat })),
    totalRounds,
    round: 0,               // 0-indexed; hand size = round + 1
    dealerIndex: -1,        // incremented to 0 on first startRound
    firstBidderIndex: 0,
    trumpSuit: null,
    hands: {},              // playerId -> [cards]
    bids: {},               // playerId -> number | null
    tricksWon: {},          // playerId -> count this round
    currentTrick: [],       // [{playerId, card}]
    trickLeaderIndex: 0,
    turnIndex: 0,
    scores: Object.fromEntries(players.map(p => [p.id, 0])),
    scoreHistory: [],       // per-round breakdown for the UI / history
    phase: 'lobby',         // lobby -> bidding -> playing -> round_end -> game_end
    log: [],
    lastTrick: null,        // {cards:[{playerId,card}], winnerId} for UI display between tricks
  };
}

function playerIndex(state, playerId) {
  return state.players.findIndex(p => p.id === playerId);
}

function nextClockwiseIndex(index, playerCount) {
  return (index + CLOCKWISE_STEP + playerCount) % playerCount;
}

function startRound(state) {
  state.round += 1;
  state.dealerIndex = nextClockwiseIndex(state.dealerIndex, state.players.length);
  const handSize = state.round; // "hand size = n at round n"
  const deck = shuffle(createDeck());

  state.hands = {};
  state.bids = {};
  state.tricksWon = {};
  state.currentTrick = [];
  state.lastTrick = null;
  state.trumpSuit = SUITS[Math.floor(Math.random() * SUITS.length)];

  let cursor = 0;
  for (const p of state.players) {
    state.hands[p.id] = sortHand(deck.slice(cursor, cursor + handSize));
    state.bids[p.id] = null;
    state.tricksWon[p.id] = 0;
    cursor += handSize;
  }

  // Bidding starts with the next player in clockwise order from the dealer.
  state.firstBidderIndex = nextClockwiseIndex(state.dealerIndex, state.players.length);
  state.turnIndex = state.firstBidderIndex;
  state.trickLeaderIndex = nextClockwiseIndex(state.firstBidderIndex, state.players.length);
  state.phase = 'bidding';
  state.log.push(`Round ${state.round}: ${handSize} card(s) each, trump is ${SUIT_NAMES[state.trumpSuit]}.`);
  return state;
}

function sortHand(cards) {
  const order = { S: 0, H: 1, D: 2, C: 3 };
  return cards.slice().sort((a, b) => order[a.suit] - order[b.suit] || b.rank - a.rank);
}

function currentPlayer(state) {
  return state.players[state.turnIndex];
}

function placeBid(state, playerId, bid) {
  if (state.phase !== 'bidding') throw new Error('Not in bidding phase.');
  if (currentPlayer(state).id !== playerId) throw new Error('Not your turn to bid.');
  const handSize = state.round;
  if (!Number.isInteger(bid) || bid < 0 || bid > handSize) {
    throw new Error(`Bid must be an integer between 0 and ${handSize}.`);
  }
  const bidTotal = Object.values(state.bids).reduce((total, currentBid) =>
    total + (currentBid === null ? 0 : currentBid), 0) + bid;
  const isLastBid = state.players.every(p => p.id === playerId || state.bids[p.id] !== null);
  if (isLastBid && bidTotal === handSize) {
    throw new Error(`The total bids cannot equal ${handSize} tricks.`);
  }
  state.bids[playerId] = bid;
  state.log.push(`${nameOf(state, playerId)} bids ${bid}.`);
  state.turnIndex = nextClockwiseIndex(state.turnIndex, state.players.length);

  const allBid = state.players.every(p => state.bids[p.id] !== null);
  if (allBid) {
    state.phase = 'playing';
    state.turnIndex = state.trickLeaderIndex;
  }
  return state;
}

function legalCards(state, playerId) {
  const hand = state.hands[playerId];
  if (state.currentTrick.length === 0) return hand; // leading: anything goes
  const ledSuit = state.currentTrick[0].card.suit;
  const canFollow = hand.some(c => c.suit === ledSuit);
  return canFollow
    ? hand.filter(c => c.suit === ledSuit || c.suit === state.trumpSuit)
    : hand;
}

function playCard(state, playerId, card) {
  if (state.phase !== 'playing') throw new Error('Not in playing phase.');
  if (currentPlayer(state).id !== playerId) throw new Error('Not your turn to play.');

  const hand = state.hands[playerId];
  const idx = hand.findIndex(c => c.suit === card.suit && c.rank === card.rank);
  if (idx === -1) throw new Error("You don't have that card.");

  const legal = legalCards(state, playerId);
  const isLegal = legal.some(c => c.suit === card.suit && c.rank === card.rank);
  if (!isLegal) throw new Error('You must follow suit if you can.');

  hand.splice(idx, 1);
  state.currentTrick.push({ playerId, card });
  state.log.push(`${nameOf(state, playerId)} plays ${cardLabel(card)}.`);

  if (state.currentTrick.length === state.players.length) {
    resolveTrick(state);
  } else {
    state.turnIndex = nextClockwiseIndex(state.turnIndex, state.players.length);
  }
  return state;
}

function resolveTrick(state) {
  const led = state.currentTrick[0].card.suit;
  let winner = state.currentTrick[0];
  for (const entry of state.currentTrick.slice(1)) {
    winner = beats(entry.card, winner.card, led, state.trumpSuit) ? entry : winner;
  }
  state.tricksWon[winner.playerId] += 1;
  state.log.push(`${nameOf(state, winner.playerId)} wins the trick.`);
  state.lastTrick = { cards: state.currentTrick, winnerId: winner.playerId };
  state.currentTrick = [];
  state.trickLeaderIndex = playerIndex(state, winner.playerId);
  state.turnIndex = state.trickLeaderIndex;

  const handEmpty = state.hands[winner.playerId].length === 0;
  if (handEmpty) {
    scoreRound(state);
  }
}

function beats(card, currentBest, ledSuit, trumpSuit) {
  const cardIsTrump = card.suit === trumpSuit;
  const bestIsTrump = currentBest.suit === trumpSuit;
  if (cardIsTrump && !bestIsTrump) return true;
  if (!cardIsTrump && bestIsTrump) return false;
  if (cardIsTrump && bestIsTrump) return card.rank > currentBest.rank;
  // neither is trump: only the led suit can win
  if (card.suit === ledSuit && currentBest.suit === ledSuit) return card.rank > currentBest.rank;
  if (card.suit === ledSuit) return true;
  return false;
}

function scoreRound(state) {
  const breakdown = {};
  for (const p of state.players) {
    const bid = state.bids[p.id];
    const won = state.tricksWon[p.id];
    const diff = won - bid;
    const roundScore = diff === 0 ? 10 + won * won : -(diff * diff);
    state.scores[p.id] += roundScore;
    breakdown[p.id] = { bid, won, roundScore, total: state.scores[p.id] };
  }
  state.scoreHistory.push({ round: state.round, trump: state.trumpSuit, breakdown });
  state.phase = 'round_end';

  if (state.round >= state.totalRounds) {
    state.phase = 'game_end';
    state.log.push('Game over!');
  }
}

function nameOf(state, playerId) {
  const p = state.players.find(pl => pl.id === playerId);
  return p ? p.name : playerId;
}

function standings(state) {
  return state.players
    .map(p => ({ id: p.id, name: p.name, isBot: p.isBot, score: state.scores[p.id] }))
    .sort((a, b) => b.score - a.score);
}

// Produces a state view safe to send to a specific player: their own hand is
// visible, everyone else's hand is reduced to a card count.
function viewFor(state, playerId) {
  return {
    id: state.id,
    round: state.round,
    totalRounds: state.totalRounds,
    trumpSuit: state.trumpSuit,
    phase: state.phase,
    players: state.players.map(p => ({
      id: p.id,
      name: p.name,
      isBot: p.isBot,
      seat: p.seat,
      handCount: state.hands[p.id] ? state.hands[p.id].length : 0,
      bid: state.bids[p.id] === undefined ? null : state.bids[p.id],
      tricksWon: state.tricksWon[p.id] || 0,
      score: state.scores[p.id] || 0,
    })),
    myHand: state.hands[playerId] || [],
    currentTrick: state.currentTrick,
    lastTrick: state.lastTrick,
    turnPlayerId: state.players[state.turnIndex] ? state.players[state.turnIndex].id : null,
    dealerId: state.players[state.dealerIndex] ? state.players[state.dealerIndex].id : null,
    legalCards: state.phase === 'playing' ? legalCards(state, playerId) : [],
    log: state.log.slice(-12),
    scoreHistory: state.scoreHistory,
    standings: standings(state),
  };
}

module.exports = {
  SUITS, SUIT_NAMES, RANK_NAMES,
  createDeck, shuffle, maxRounds,
  createGame, startRound, placeBid, playCard, legalCards,
  currentPlayer, standings, viewFor, cardLabel, rankLabel,
};
