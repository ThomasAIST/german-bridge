const crypto = require('crypto');
const engine = require('./gameEngine');
const { botBid, botPlayCard } = require('./bot');
const db = require('./db');

const QUICK_MATCH_SIZE = 4;
const TABLE_SIZE = 4;
const QUICK_MATCH_FILL_DELAY_MS = 15000; // fill empty seats with bots after this long
const BOT_THINK_DELAY_MS = 700;          // small delay so bot turns feel natural in the UI

function makeRoomCode() {
  return crypto.randomBytes(3).toString('hex').toUpperCase(); // e.g. "A1B2C3"
}

class RoomManager {
  constructor(io) {
    this.io = io;
    this.rooms = new Map(); // code -> room
  }

  // ---- room lifecycle -----------------------------------------------

  createRoom({ hostUser, maxPlayers, mode }) {
    if (maxPlayers !== TABLE_SIZE) {
      throw new Error(`German Bridge tables require exactly ${TABLE_SIZE} players.`);
    }
    let code;
    do { code = makeRoomCode(); } while (this.rooms.has(code));

    const room = {
      code,
      mode,                    // 'private' | 'quick' | 'bots'
      maxPlayers,
      hostId: hostUser.id,
      seats: [],
      status: 'waiting',       // waiting | playing | finished
      game: null,
      fillTimer: null,
    };
    this.rooms.set(code, room);
    this.addHuman(room, hostUser);
    return room;
  }

  findOpenQuickRoom() {
    for (const room of this.rooms.values()) {
      if (room.mode === 'quick' && room.status === 'waiting' && room.seats.length < room.maxPlayers) {
        return room;
      }
    }
    return null;
  }

  addHuman(room, user) {
    if (room.seats.find(s => s.userId === user.id)) return; // already seated
    if (room.seats.length >= room.maxPlayers) throw new Error('Room is full.');
    room.seats.push({
      id: `u${user.id}`,
      userId: user.id,
      name: user.username,
      isBot: false,
      connected: true,
    });
  }

  addBot(room) {
    if (room.seats.length >= room.maxPlayers) throw new Error('Room is full.');
    const botNum = room.seats.filter(s => s.isBot).length + 1;
    room.seats.push({
      id: `bot_${room.code}_${botNum}_${Date.now()}`,
      userId: null,
      name: `Bot ${botNum}`,
      isBot: true,
      connected: true,
    });
  }

  fillWithBots(room) {
    while (room.seats.length < room.maxPlayers) this.addBot(room);
  }

  removeSeat(room, seatId) {
    room.seats = room.seats.filter(s => s.id !== seatId);
  }

  scheduleQuickFill(room) {
    if (room.mode !== 'quick' || room.fillTimer) return;
    room.fillTimer = setTimeout(() => {
      room.fillTimer = null;
      if (room.status === 'waiting') {
        this.fillWithBots(room);
        this.startGame(room);
      }
    }, QUICK_MATCH_FILL_DELAY_MS);
  }

  // ---- game lifecycle -------------------------------------------------

  startGame(room) {
    if (room.status !== 'waiting') return;
    if (room.fillTimer) { clearTimeout(room.fillTimer); room.fillTimer = null; }
    if (room.seats.length !== TABLE_SIZE) throw new Error(`Need exactly ${TABLE_SIZE} players to start.`);

    room.status = 'playing';
    const players = room.seats.map(s => ({ id: s.id, name: s.name, isBot: s.isBot, userId: s.userId }));
    const gameId = `g_${room.code}_${Date.now()}`;
    room.game = engine.createGame(gameId, players);
    room.gameStartedAt = new Date().toISOString();
    engine.startRound(room.game);
    this.broadcastState(room);
    this.maybeRunBotTurn(room);
  }

  broadcastState(room) {
    this.io.to(room.code).emit('room_state', this.publicRoomView(room));
    if (!room.game) return;
    for (const seat of room.seats) {
      if (seat.isBot || !seat.connected) continue;
      const view = engine.viewFor(room.game, seat.id);
      if (seat.socketId) this.io.to(seat.socketId).emit('game_state', view);
    }
  }

  publicRoomView(room) {
    return {
      code: room.code,
      mode: room.mode,
      maxPlayers: room.maxPlayers,
      status: room.status,
      hostId: room.hostId,
      seats: room.seats.map(s => ({ id: s.id, userId: s.userId, name: s.name, isBot: s.isBot, connected: s.connected })),
    };
  }

  // ---- player actions ---------------------------------------------------

  handleBid(room, seatId, bid) {
    engine.placeBid(room.game, seatId, bid);
    this.afterAction(room);
  }

  handlePlay(room, seatId, card) {
    engine.playCard(room.game, seatId, card);
    this.afterAction(room);
  }

  afterAction(room) {
    const g = room.game;
    if (g.phase === 'round_end') {
      // brief pause so players can see the round summary, then continue
      setTimeout(() => {
        if (!this.rooms.has(room.code) || room.game !== g) return;
        engine.startRound(g);
        this.broadcastState(room);
        this.maybeRunBotTurn(room);
      }, 3500);
      this.broadcastState(room);
      return;
    }
    if (g.phase === 'game_end') {
      room.status = 'finished';
      this.persistGame(room);
      this.broadcastState(room);
      return;
    }
    this.broadcastState(room);
    this.maybeRunBotTurn(room);
  }

  maybeRunBotTurn(room) {
    const g = room.game;
    if (!g || g.phase === 'game_end' || g.phase === 'round_end') return;
    const seat = room.seats.find(s => s.id === g.players[g.turnIndex].id);
    if (!seat || !seat.isBot) return;

    setTimeout(() => {
      if (!this.rooms.has(room.code) || room.game !== g) return; // room/game changed underneath
      try {
        if (g.phase === 'bidding') {
          const hand = g.hands[seat.id];
          let bid = botBid(hand, g.trumpSuit, g.round);
          const otherBids = g.players
            .filter(player => player.id !== seat.id)
            .map(player => g.bids[player.id]);
          const isLastBid = otherBids.every(currentBid => currentBid !== null);
          const bidTotal = otherBids.reduce((total, currentBid) => total + currentBid, 0) + bid;
          if (isLastBid && bidTotal === g.round) {
            bid = Array.from({ length: g.round + 1 }, (_, value) => value)
              .find(value => value !== bid);
          }
          this.handleBid(room, seat.id, bid);
        } else if (g.phase === 'playing') {
          const card = botPlayCard(g, seat.id);
          this.handlePlay(room, seat.id, card);
        }
      } catch (e) {
        // defensive: should not happen if bot logic only picks legal moves
        console.error('Bot error:', e.message);
      }
    }, BOT_THINK_DELAY_MS);
  }

  persistGame(room) {
    const g = room.game;
    const standings = engine.standings(g);
    const insertGame = db.prepare(`
      INSERT INTO games (id, mode, num_players, rounds_played, started_at)
      VALUES (?, ?, ?, ?, ?)
    `);
    const insertPlayer = db.prepare(`
      INSERT INTO game_players (game_id, user_id, display_name, is_bot, final_score, placement)
      VALUES (?, ?, ?, ?, ?, ?)
    `);
    const tx = db.transaction(() => {
      insertGame.run(g.id, room.mode, g.players.length, g.round, room.gameStartedAt);
      standings.forEach((s, i) => {
        const seat = room.seats.find(se => se.id === s.id);
        insertPlayer.run(g.id, seat && seat.userId ? seat.userId : null, s.name, s.isBot ? 1 : 0, s.score, i + 1);
      });
    });
    tx();
  }

  // ---- lookups ------------------------------------------------------

  getRoom(code) {
    return this.rooms.get((code || '').toUpperCase());
  }

  roomOfSeat(seatId) {
    for (const room of this.rooms.values()) {
      if (room.seats.find(s => s.id === seatId)) return room;
    }
    return null;
  }
}

module.exports = { RoomManager, QUICK_MATCH_SIZE };
