const State = {
  view: 'auth',       // auth | lobby | profile
  authTab: 'login',
  user: null,
  room: null,
  game: null,
  mySeatId: null,
  profileData: null,
};

const App = (() => {
  const $app = () => document.getElementById('app');
  const $nav = () => document.getElementById('nav-auth');

  function init() {
    const user = Api.getUser();
    if (user && Api.getToken()) {
      State.user = user;
      connectSocket();
      State.view = 'lobby';
    } else {
      State.view = 'auth';
    }
    render();
  }

  function connectSocket() {
    const socket = Sockets.connect();
    socket.on('connect_error', () => {
      toast('Session expired — please log in again.');
      Api.clearSession();
      State.user = null;
      State.view = 'auth';
      render();
    });
    socket.on('room_state', (room) => {
      State.room = room;
      const mySeat = room.seats.find(s => s.userId === State.user.id);
      State.mySeatId = mySeat ? mySeat.id : null;
      if (room.status === 'waiting') State.game = null;
      if (room.status === 'waiting' || !State.game) render();
    });
    socket.on('game_state', (game) => {
      State.game = game;
      updateGameView();
    });
  }

  // ---------------- routing / rendering ----------------

  function render() {
    renderNav();
    let html = '';
    if (State.view === 'auth') html = Views.authView();
    else if (State.view === 'profile') html = State.profileData ? Views.profileView(State.profileData) : `<div class="text-center text-slate-400 mt-20">Loading…</div>`;
    else if (State.room) html = State.room.status === 'waiting'
      ? Views.roomWaitingView(State.room, State.user)
      : Views.gameView(State.game, State.room, State.user);
    else html = Views.lobbyView(State.user);

    $app().innerHTML = html;
    wireCardClicks();
  }

  function renderNav() {
    if (!State.user) { $nav().innerHTML = ''; return; }
    $nav().innerHTML = `
      <span class="text-slate-300 hidden sm:inline">👤 ${Views.escapeHtml(State.user.username)}</span>
      <button class="btn btn-ghost text-xs" onclick="App.logout()">Log Out</button>`;
  }

  function updateGameView() {
    if (!State.game || State.game.phase === 'game_end' || !document.getElementById('game-header')) {
      render();
      return;
    }

    document.getElementById('game-header').innerHTML = Views.gameHeaderHtml(State.game);
    document.getElementById('game-seats').innerHTML = Views.gameSeatsHtml(State.game);
    document.getElementById('game-trick').innerHTML = Views.renderTrick(State.game);
    document.getElementById('round-end-banner').innerHTML = State.game.phase === 'round_end'
      ? Views.renderRoundEndBanner(State.game) : '';
    document.getElementById('game-player-panel').innerHTML = Views.gamePlayerPanelHtml(State.game);
    document.getElementById('game-standings').innerHTML = Views.gameStandingsHtml(State.game);
    document.getElementById('game-log').innerHTML = Views.gameLogHtml(State.game);
    wireCardClicks();
  }

  function goTo(view) {
    if (view === 'lobby') { State.room = null; State.game = null; }
    State.view = view;
    render();
  }

  function viewProfile() {
    State.view = 'profile';
    State.profileData = null;
    render();
    Api.profile().then(data => { State.profileData = data; render(); }).catch(e => toast(e.message));
  }

  // ---------------- auth ----------------

  function setAuthTab(tab) { State.authTab = tab; render(); }

  async function submitAuth(e) {
    e.preventDefault();
    const form = e.target;
    const username = form.username.value.trim();
    const password = form.password.value;
    const errBox = document.getElementById('auth-error');
    errBox.classList.add('hidden');
    try {
      if (State.authTab === 'login') await Api.login(username, password);
      else await Api.register(username, password);
      State.user = Api.getUser();
      connectSocket();
      State.view = 'lobby';
      render();
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove('hidden');
    }
  }

  function logout() {
    Sockets.disconnect();
    Api.logout();
    State.user = null;
    State.room = null;
    State.game = null;
    State.view = 'auth';
    render();
  }

  // ---------------- lobby actions ----------------

  function quickMatch() {
    Sockets.get().emit('quick_match', {}, (res) => {
      if (!res.ok) toast(res.error);
    });
  }

  function playVsBots() {
    Sockets.get().emit('play_vs_bots', { numBots: 3 }, (res) => {
      if (!res.ok) toast(res.error);
    });
  }

  function createRoom() {
    Sockets.get().emit('create_room', { maxPlayers: 4 }, (res) => {
      if (!res.ok) toast(res.error);
    });
  }

  function joinRoomByCode() {
    const code = document.getElementById('join-code').value.trim().toUpperCase();
    if (!code) return toast('Enter a room code.');
    Sockets.get().emit('join_room', { code }, (res) => {
      if (!res.ok) toast(res.error);
    });
  }

  function copyRoomCode(code) {
    navigator.clipboard?.writeText(code);
    toast('Room code copied!');
  }

  // ---------------- room actions ----------------

  function addBot() {
    Sockets.get().emit('add_bot', {}, (res) => { if (!res.ok) toast(res.error); });
  }

  function startGame() {
    Sockets.get().emit('start_game', {}, (res) => { if (!res.ok) toast(res.error); });
  }

  function leaveRoom() {
    Sockets.get().emit('leave_room', {}, () => {
      State.room = null;
      State.game = null;
      State.view = 'lobby';
      render();
    });
  }

  // ---------------- game actions ----------------

  function placeBid(n) {
    Sockets.get().emit('place_bid', { bid: n }, (res) => { if (!res.ok) toast(res.error); });
  }

  function playCard(suit, rank) {
    Sockets.get().emit('play_card', { card: { suit, rank: Number(rank) } }, (res) => { if (!res.ok) toast(res.error); });
  }

  function wireCardClicks() {
    $app().querySelectorAll('.card.playable').forEach(el => {
      el.onclick = () => playCard(el.dataset.suit, el.dataset.rank);
    });
  }

  // ---------------- utils ----------------

  function toast(msg) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
  }

  return {
    init, goTo, viewProfile, setAuthTab, submitAuth, logout,
    quickMatch, playVsBots, createRoom, joinRoomByCode, copyRoomCode,
    addBot, startGame, leaveRoom, placeBid, playCard,
  };
})();

App.init();
