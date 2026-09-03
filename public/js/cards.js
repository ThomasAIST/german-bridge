const Cards = (() => {
  const SUIT_SYMBOL = { S: '♠', H: '♥', D: '♦', C: '♣' };
  const SUIT_COLOR = { S: 'black', H: 'red', D: 'red', C: 'black' };
  const RANK_LABEL = { 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };

  function rankLabel(r) { return RANK_LABEL[r] || String(r); }
  function suitSymbol(s) { return SUIT_SYMBOL[s]; }
  function suitName(s) { return { S: 'Spades', H: 'Hearts', D: 'Diamonds', C: 'Clubs' }[s]; }

  // Returns an HTML string for a card. `opts`: {playable, mini, disabled}
  function cardHtml(card, opts = {}) {
    const color = SUIT_COLOR[card.suit];
    const classes = ['card', color];
    if (opts.mini) classes.push('mini');
    if (opts.playable) classes.push('playable');
    if (opts.disabled) classes.push('disabled');
    return `<div class="${classes.join(' ')}" data-suit="${card.suit}" data-rank="${card.rank}">
      <div class="rank">${rankLabel(card.rank)}</div>
      <div class="suit">${suitSymbol(card.suit)}</div>
    </div>`;
  }

  function cardBackHtml(mini) {
    return `<div class="card-back${mini ? ' mini' : ''}"></div>`;
  }

  return { rankLabel, suitSymbol, suitName, cardHtml, cardBackHtml, SUIT_COLOR };
})();
