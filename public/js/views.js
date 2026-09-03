const Views = (() => {

  function authView() {
    return `
    <div class="max-w-md mx-auto mt-10 fade-in">
      <div class="panel p-8">
        <h1 class="font-poppins font-800 text-2xl mb-1">Welcome to German Bridge</h1>
        <p class="text-slate-400 text-sm mb-6">Sign in to play, track your history, and climb the table.</p>

        <div class="flex gap-2 mb-6 text-sm">
          <button class="btn ${State.authTab==='login'?'btn-primary':'btn-secondary'} flex-1" onclick="App.setAuthTab('login')">Log In</button>
          <button class="btn ${State.authTab==='register'?'btn-primary':'btn-secondary'} flex-1" onclick="App.setAuthTab('register')">Sign Up</button>
        </div>

        <form id="auth-form" class="space-y-4" onsubmit="App.submitAuth(event)">
          <div>
            <label class="text-xs text-slate-400">Username</label>
            <input class="input mt-1" name="username" autocomplete="username" required minlength="3" maxlength="20" />
          </div>
          <div>
            <label class="text-xs text-slate-400">Password</label>
            <input class="input mt-1" name="password" type="password" autocomplete="${State.authTab==='login'?'current-password':'new-password'}" required minlength="4" />
          </div>
          <div id="auth-error" class="text-red-400 text-sm hidden"></div>
          <button type="submit" class="btn btn-primary w-full">${State.authTab==='login'?'Log In':'Create Account'}</button>
        </form>
      </div>
    </div>`;
  }

  function lobbyView(user) {
    return `
    <div class="fade-in space-y-8">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="font-poppins font-800 text-3xl">Hey, ${escapeHtml(user.username)} 👋</h1>
          <p class="text-slate-400 mt-1">Ready for a hand of German Bridge?</p>
        </div>
        <button class="btn btn-ghost" onclick="App.viewProfile()">📜 My History</button>
      </div>

      <div class="grid md:grid-cols-3 gap-5">
        <div class="panel p-6 flex flex-col gap-3">
          <div class="text-3xl">⚡</div>
          <h2 class="font-poppins font-700 text-lg">Quick Match</h2>
          <p class="text-slate-400 text-sm flex-1">Join a four-player table instantly. Empty seats fill with bots after 15s so you're never left waiting.</p>
          <button class="btn btn-primary" onclick="App.quickMatch()">Find a Table</button>
        </div>

        <div class="panel p-6 flex flex-col gap-3">
          <div class="text-3xl">🤖</div>
          <h2 class="font-poppins font-700 text-lg">Practice vs Bots</h2>
          <p class="text-slate-400 text-sm flex-1">Play a private table filled entirely with bots — great for learning the bidding and scoring.</p>
          <div class="input text-sm text-slate-300">4 players: you + 3 bots</div>
          <button class="btn btn-secondary" onclick="App.playVsBots()">Start Practice Game</button>
        </div>

        <div class="panel p-6 flex flex-col gap-3">
          <div class="text-3xl">🔒</div>
          <h2 class="font-poppins font-700 text-lg">Private Room</h2>
          <p class="text-slate-400 text-sm flex-1">Create a table and invite friends with a room code, or join one you've been given.</p>
          <div class="input text-sm text-slate-300">Fixed table size: 4 players</div>
          <button class="btn btn-secondary" onclick="App.createRoom()">Create Room</button>
          <div class="flex gap-2 mt-1">
            <input id="join-code" class="input" placeholder="Room code" maxlength="6" style="text-transform:uppercase" />
            <button class="btn btn-secondary shrink-0" onclick="App.joinRoomByCode()">Join</button>
          </div>
        </div>
      </div>

      <div class="panel p-6">
        <h3 class="font-poppins font-700 mb-2">How German Bridge works</h3>
        <ul class="text-sm text-slate-400 space-y-1 list-disc list-inside">
          <li>Round <em>n</em> deals <em>n</em> cards to each player. A trump suit is drawn at random each round.</li>
          <li>Everyone bids the exact number of tricks they'll win — no passing, 0 is allowed.</li>
          <li>Follow suit if you can. Highest trump wins the trick, otherwise highest card of the suit led.</li>
          <li>Hit your bid exactly: score <strong>10 + tricks²</strong>. Miss it: score <strong>-(difference)²</strong>.</li>
        </ul>
      </div>
    </div>`;
  }

  function roomWaitingView(room, user) {
    const seatsHtml = Array.from({ length: room.maxPlayers }).map((_, i) => {
      const seat = room.seats[i];
      if (!seat) {
        return `<div class="panel p-4 flex items-center gap-3 opacity-50">
          <div class="w-10 h-10 rounded-full border-2 border-dashed border-white/20 flex items-center justify-center">+</div>
          <span class="text-sm text-slate-400">Empty seat</span>
        </div>`;
      }
      return `<div class="panel p-4 flex items-center gap-3">
        <div class="w-10 h-10 rounded-full ${seat.isBot ? 'bg-indigo-500/30' : 'bg-amber-500/30'} flex items-center justify-center font-700">
          ${seat.isBot ? '🤖' : escapeHtml(seat.name[0].toUpperCase())}
        </div>
        <div>
          <div class="text-sm font-600">${escapeHtml(seat.name)}</div>
          <div class="text-xs text-slate-400">${seat.isBot ? 'Bot' : (seat.connected ? 'Connected' : 'Disconnected')}</div>
        </div>
      </div>`;
    }).join('');

    const isHost = State.user && room.hostId === State.user.id;
    const canStart = room.seats.length === 4;

    return `
    <div class="fade-in max-w-3xl mx-auto space-y-6">
      <div class="panel p-6 text-center">
        <p class="text-slate-400 text-sm mb-1">${room.mode === 'quick' ? 'Quick match — filling table…' : room.mode === 'bots' ? 'Practice table' : 'Private room'}</p>
        <h1 class="font-poppins font-800 text-3xl tracking-widest">${room.code}</h1>
        ${room.mode === 'private' ? `<button class="btn btn-ghost mt-2 text-xs" onclick="App.copyRoomCode('${room.code}')">📋 Copy invite code</button>` : ''}
      </div>

      <div class="grid sm:grid-cols-2 gap-3">${seatsHtml}</div>

      <div class="flex items-center justify-center gap-3">
        ${isHost ? `<button class="btn btn-secondary" onclick="App.addBot()" ${room.seats.length>=room.maxPlayers?'disabled':''}>+ Add Bot</button>` : ''}
        ${isHost ? `<button class="btn btn-primary" onclick="App.startGame()" ${canStart?'':'disabled'}>Start Game</button>` : `<span class="text-sm text-slate-400">Waiting for host to start…</span>`}
        <button class="btn btn-ghost" onclick="App.leaveRoom()">Leave</button>
      </div>
    </div>`;
  }

  function gameView(game, room, user) {
    if (!game) return `<div class="text-center text-slate-400 mt-20">Loading table…</div>`;

    if (game.phase === 'game_end') {
      return gameEndView(game, room);
    }

    return `
    <div class="fade-in space-y-4">
      <div id="game-header">${gameHeaderHtml(game)}</div>

      <div class="table-felt relative mx-auto" style="width:100%; max-width:820px; height:460px;">
        <div id="game-seats">${gameSeatsHtml(game)}</div>
        <div id="game-trick" class="absolute inset-0 flex items-center justify-center">${renderTrick(game)}</div>
        <div id="round-end-banner">${game.phase === 'round_end' ? renderRoundEndBanner(game) : ''}</div>
      </div>

      <div id="game-player-panel">${gamePlayerPanelHtml(game)}</div>

      <div id="game-standings">${gameStandingsHtml(game)}</div>

      <div id="game-log">${gameLogHtml(game)}</div>
    </div>`;
  }

  function gameHeaderHtml(game) {
    return `<div class="flex items-center justify-between flex-wrap gap-2">
      <div class="flex items-center gap-3">
        <span class="seat-badge">Round ${game.round}/${game.totalRounds}</span>
        <span class="seat-badge">Trump ${Cards.suitSymbol(game.trumpSuit)} ${Cards.suitName(game.trumpSuit)}</span>
      </div>
      <button class="btn btn-ghost text-xs" onclick="App.leaveRoom()">Leave table</button>
    </div>`;
  }

  function gameSeatsHtml(game) {
    const myIndex = game.players.findIndex(p => p.id === State.mySeatId);
    const others = [];
    if (myIndex >= 0) {
      for (let offset = 1; offset < game.players.length; offset += 1) {
        const index = (myIndex - offset + game.players.length) % game.players.length;
        others.push(game.players[index]);
      }
    } else {
      others.push(...game.players);
    }
    const seatPositions = layoutSeats(others.length);
    return others.map((p, i) => otherSeatHtml(p, game, seatPositions[i])).join('');
  }

  function gamePlayerPanelHtml(game) {
    const me = game.players.find(p => p.id === State.mySeatId);
    const bidBar = game.phase === 'bidding' && game.turnPlayerId === State.mySeatId ? renderBidBar(game) : '';
    return `<div class="panel p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="font-600 text-sm">${me ? escapeHtml(me.name) : 'You'} ${me && me.bid !== null ? `· bid ${me.bid}, won ${me.tricksWon}` : ''}</span>
        <span class="seat-badge ${game.turnPlayerId === State.mySeatId ? 'turn' : ''}">${game.turnPlayerId === State.mySeatId ? "Your turn" : "Waiting…"}</span>
      </div>
      ${bidBar}
      <div class="flex flex-wrap gap-2 justify-center mt-2">${renderMyHand(game)}</div>
    </div>`;
  }

  function gameStandingsHtml(game) {
    return `<div class="panel p-4">
      <h3 class="text-xs uppercase tracking-wide text-slate-400 mb-2">Standings</h3>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
        ${game.standings.map(s => `
          <div class="flex items-center justify-between text-sm bg-white/5 rounded-lg px-3 py-2">
            <span>${s.isBot ? '🤖 ' : ''}${escapeHtml(s.name)}</span>
            <span class="font-700 ${s.score<0?'text-red-400':'text-amber-300'}">${s.score}</span>
          </div>`).join('')}
      </div>
    </div>`;
  }

  function gameLogHtml(game) {
    return `<div class="panel p-4 max-h-32 overflow-y-auto text-xs text-slate-400 space-y-1">
      ${game.log.map(l => `<div>${escapeHtml(l)}</div>`).join('')}
    </div>`;
  }

  function layoutSeats(n) {
    // Positions are ordered clockwise from the user's seat at the bottom.
    const spots = {
      1: [{ top: '4%', left: '50%' }],
      2: [{ top: '10%', left: '18%' }, { top: '10%', left: '82%' }],
      3: [{ top: '38%', left: '6%' }, { top: '4%', left: '50%' }, { top: '38%', left: '94%' }],
      4: [{ top: '38%', left: '6%' }, { top: '4%', left: '28%' }, { top: '4%', left: '72%' }, { top: '38%', left: '94%' }],
      5: [{ top: '42%', left: '4%' }, { top: '10%', left: '14%' }, { top: '2%', left: '50%' }, { top: '10%', left: '86%' }, { top: '42%', left: '96%' }],
      6: [{ top: '42%', left: '10%' }, { top: '20%', left: '6%' }, { top: '2%', left: '30%' }, { top: '2%', left: '70%' }, { top: '20%', left: '94%' }, { top: '42%', left: '90%' }],
    };
    return spots[n] || spots[6];
  }

  function otherSeatHtml(p, game, pos) {
    const isTurn = game.turnPlayerId === p.id;
    return `<div class="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1" style="top:${pos.top}; left:${pos.left};">
      <div class="flex items-center gap-1">
        <div class="w-8 h-8 rounded-full ${p.isBot ? 'bg-indigo-500/40' : 'bg-amber-500/40'} flex items-center justify-center text-sm">${p.isBot ? '🤖' : escapeHtml(p.name[0].toUpperCase())}</div>
        <span class="seat-badge ${isTurn ? 'turn' : ''}">${escapeHtml(p.name)}</span>
      </div>
      <div class="flex gap-1">${Array.from({length: Math.min(p.handCount,7)}).map(()=>Cards.cardBackHtml(true)).join('')}</div>
      <div class="text-[11px] text-slate-300">${p.bid !== null ? `bid ${p.bid} · won ${p.tricksWon}` : 'bidding…'}</div>
    </div>`;
  }

  function renderTrick(game) {
    const cards = game.currentTrick.length ? game.currentTrick : (game.lastTrick ? game.lastTrick.cards : []);
    if (!cards.length) return `<div class="text-slate-400 text-sm">Waiting for the first card…</div>`;
    return `<div class="flex gap-2">${cards.map(entry => Cards.cardHtml(entry.card)).join('')}</div>`;
  }

  function renderBidBar(game) {
    const max = game.round;
    const btns = Array.from({ length: max + 1 }).map((_, n) =>
      `<button class="btn btn-secondary" style="min-width:44px" onclick="App.placeBid(${n})">${n}</button>`).join('');
    return `<div class="mb-3">
      <p class="text-xs text-slate-400 mb-2">How many tricks will you win this round?</p>
      <div class="flex flex-wrap gap-2">${btns}</div>
    </div>`;
  }

  function renderMyHand(game) {
    if (!game.myHand.length) return `<span class="text-slate-500 text-sm">No cards this round.</span>`;
    const legalSet = new Set(game.legalCards.map(c => `${c.suit}${c.rank}`));
    const canPlay = game.phase === 'playing' && game.turnPlayerId === State.mySeatId;
    return game.myHand.map(c => {
      const isLegal = legalSet.has(`${c.suit}${c.rank}`);
      return Cards.cardHtml(c, { playable: canPlay && isLegal, disabled: canPlay && !isLegal });
    }).join('');
  }

  function renderRoundEndBanner(game) {
    const last = game.scoreHistory[game.scoreHistory.length - 1];
    if (!last) return '';
    const rows = game.players.map(p => {
      const b = last.breakdown[p.id];
      return `<div class="flex justify-between text-sm"><span>${p.isBot ? '🤖 ' : ''}${escapeHtml(p.name)}</span><span>${b.bid}→${b.won} · <strong class="${b.roundScore<0?'text-red-400':'text-emerald-400'}">${b.roundScore>0?'+':''}${b.roundScore}</strong></span></div>`;
    }).join('');
    return `<div class="absolute inset-0 flex items-center justify-center bg-black/60 rounded-[50%/30%]">
      <div class="panel p-5 w-72">
        <h3 class="font-poppins font-700 mb-2 text-center">Round ${last.round} complete</h3>
        <div class="space-y-1">${rows}</div>
        <p class="text-xs text-slate-400 mt-3 text-center">Next round starting…</p>
      </div>
    </div>`;
  }

  function gameEndView(game, room) {
    const standings = game.standings;
    return `
    <div class="fade-in max-w-xl mx-auto text-center space-y-6">
      <div class="text-5xl">🏆</div>
      <h1 class="font-poppins font-800 text-3xl">Game Over</h1>
      <p class="text-slate-400">${standings[0].isBot ? '🤖 ' : ''}${escapeHtml(standings[0].name)} takes the table!</p>
      <div class="panel p-5 space-y-2 text-left">
        ${standings.map((s, i) => `
          <div class="flex items-center justify-between px-2 py-2 rounded-lg ${i===0?'bg-amber-500/15':''}">
            <span>${i+1}. ${s.isBot ? '🤖 ' : ''}${escapeHtml(s.name)}</span>
            <span class="font-700 ${s.score<0?'text-red-400':'text-amber-300'}">${s.score}</span>
          </div>`).join('')}
      </div>
      <div class="flex gap-3 justify-center">
        <button class="btn btn-primary" onclick="App.goTo('lobby')">Back to Lobby</button>
        <button class="btn btn-secondary" onclick="App.viewProfile()">View History</button>
      </div>
    </div>`;
  }

  function profileView(data) {
    const stats = data.stats || {};
    const games = data.games || [];
    return `
    <div class="fade-in space-y-6 max-w-3xl mx-auto">
      <div class="flex items-center justify-between">
        <h1 class="font-poppins font-800 text-3xl">${escapeHtml(data.username)}'s History</h1>
        <button class="btn btn-ghost" onclick="App.goTo('lobby')">← Back to Lobby</button>
      </div>
      <div class="grid grid-cols-3 gap-4">
        <div class="panel p-4 text-center"><div class="text-2xl font-800">${stats.played || 0}</div><div class="text-xs text-slate-400">Games Played</div></div>
        <div class="panel p-4 text-center"><div class="text-2xl font-800">${stats.wins || 0}</div><div class="text-xs text-slate-400">Wins</div></div>
        <div class="panel p-4 text-center"><div class="text-2xl font-800">${stats.avgScore ? Math.round(stats.avgScore) : 0}</div><div class="text-xs text-slate-400">Avg Score</div></div>
      </div>
      <div class="panel p-4">
        <h3 class="text-xs uppercase tracking-wide text-slate-400 mb-3">Recent Games</h3>
        ${games.length === 0 ? `<p class="text-sm text-slate-500">No games yet — go play one!</p>` : `
        <div class="space-y-2">
          ${games.map(g => `
            <div class="flex items-center justify-between bg-white/5 rounded-lg px-3 py-2 text-sm">
              <div>
                <div class="font-600">${g.mode} · ${g.num_players} players · ${g.rounds_played} rounds</div>
                <div class="text-xs text-slate-400">${new Date(g.finished_at + 'Z').toLocaleString()}</div>
              </div>
              <div class="text-right">
                <div class="font-700 ${g.final_score<0?'text-red-400':'text-amber-300'}">${g.final_score} pts</div>
                <div class="text-xs text-slate-400">Placed #${g.placement}</div>
              </div>
            </div>`).join('')}
        </div>`}
      </div>
    </div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  }

  return {
    authView, lobbyView, roomWaitingView, gameView, profileView, escapeHtml,
    gameHeaderHtml, gameSeatsHtml, gamePlayerPanelHtml, gameStandingsHtml, gameLogHtml,
    renderTrick, renderRoundEndBanner,
  };
})();
