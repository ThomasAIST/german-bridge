require('dotenv').config();
const path = require('path');
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');

const db = require('./db');
const { register, login, requireAuth, verifyToken } = require('./auth');
const { RoomManager, QUICK_MATCH_SIZE } = require('./rooms');

if (process.env.NODE_ENV === 'production' && (!process.env.JWT_SECRET || process.env.JWT_SECRET.length < 32)) {
  throw new Error('JWT_SECRET must be at least 32 characters in production.');
}

const app = express();
const allowedOrigins = (process.env.FRONTEND_URL || '')
  .split(',')
  .map(value => value.trim().replace(/\/$/, ''))
  .filter(Boolean)
  .map(value => {
    try { return new URL(value).origin; } catch { return value; }
  });
const frontendUrl = allowedOrigins[0] || '';
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && (!allowedOrigins.length || allowedOrigins.includes(origin))) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
    res.setHeader('Access-Control-Max-Age', '86400');
  }
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});
app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));

app.get('/health', (req, res) => {
  res.json({ ok: true });
});

const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: allowedOrigins.length ? allowedOrigins : true,
    methods: ['GET', 'POST'],
  },
});
const roomManager = new RoomManager(io);

// ---------------------------------------------------------------------
// REST API: accounts + history
// ---------------------------------------------------------------------

app.post('/api/register', (req, res) => {
  (async () => { try {
    const { username, password } = req.body || {};
    const result = await register(username, password);
    res.json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  } })();
});

app.post('/api/login', (req, res) => {
  (async () => { try {
    const { username, password } = req.body || {};
    const result = await login(username, password);
    res.json(result);
  } catch (e) {
    res.status(400).json({ error: e.message });
  } })();
});

app.get('/api/profile', requireAuth, async (req, res) => {
  const games = await db.all(`
    SELECT g.id, g.mode, g.num_players, g.rounds_played, g.finished_at,
           gp.final_score, gp.placement
    FROM game_players gp
    JOIN games g ON g.id = gp.game_id
    WHERE gp.user_id = ?
    ORDER BY g.finished_at DESC
    LIMIT 50
  `, [req.user.id]);

  const stats = await db.get(`
    SELECT COUNT(*) as played,
           SUM(CASE WHEN placement = 1 THEN 1 ELSE 0 END) as wins,
           AVG(final_score) as avgScore
    FROM game_players WHERE user_id = ?
  `, [req.user.id]);

  res.json({ username: req.user.username, games, stats });
});

// game detail incl. other players, for a history entry
app.get('/api/games/:id', requireAuth, async (req, res) => {
  const players = await db.all(`
    SELECT display_name, is_bot, final_score, placement
    FROM game_players WHERE game_id = ? ORDER BY placement ASC
  `, [req.params.id]);
  if (!players.length) return res.status(404).json({ error: 'Game not found.' });
  res.json({ players });
});

// ---------------------------------------------------------------------
// Socket.IO: lobby + realtime gameplay
// ---------------------------------------------------------------------

io.use((socket, next) => {
  const token = socket.handshake.auth && socket.handshake.auth.token;
  const payload = token && verifyToken(token);
  if (!payload) return next(new Error('unauthorized'));
  socket.user = payload; // {id, username}
  next();
});

io.on('connection', (socket) => {
  const user = socket.user;

  const attachSeat = (room) => {
    const seat = room.seats.find(s => s.userId === user.id);
    if (seat) { seat.socketId = socket.id; seat.connected = true; }
    socket.join(room.code);
    socket.data.roomCode = room.code;
  };

  socket.on('create_room', ({ maxPlayers }, cb) => {
    try {
      const room = roomManager.createRoom({
        hostUser: user,
        maxPlayers: 4,
        mode: 'private',
      });
      attachSeat(room);
      roomManager.broadcastState(room);
      cb && cb({ ok: true, code: room.code });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('join_room', ({ code }, cb) => {
    try {
      const room = roomManager.getRoom(code);
      if (!room) throw new Error('Room not found.');
      if (room.status !== 'waiting') throw new Error('That game has already started.');
      roomManager.addHuman(room, user);
      attachSeat(room);
      roomManager.broadcastState(room);
      cb && cb({ ok: true, code: room.code });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('quick_match', (_, cb) => {
    try {
      let room = roomManager.findOpenQuickRoom();
      if (!room) {
        room = roomManager.createRoom({ hostUser: user, maxPlayers: QUICK_MATCH_SIZE, mode: 'quick' });
      } else {
        roomManager.addHuman(room, user);
      }
      attachSeat(room);
      roomManager.broadcastState(room);
      roomManager.scheduleQuickFill(room);
      if (room.seats.length === room.maxPlayers) {
        roomManager.startGame(room);
      }
      cb && cb({ ok: true, code: room.code });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('play_vs_bots', ({ numBots }, cb) => {
    try {
      const room = roomManager.createRoom({ hostUser: user, maxPlayers: 4, mode: 'bots' });
      attachSeat(room);
      roomManager.fillWithBots(room);
      roomManager.broadcastState(room);
      roomManager.startGame(room);
      cb && cb({ ok: true, code: room.code });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('add_bot', (_, cb) => {
    try {
      const room = roomManager.getRoom(socket.data.roomCode);
      if (!room) throw new Error('Not in a room.');
      if (room.hostId !== user.id) throw new Error('Only the host can add bots.');
      roomManager.addBot(room);
      roomManager.broadcastState(room);
      cb && cb({ ok: true });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('start_game', (_, cb) => {
    try {
      const room = roomManager.getRoom(socket.data.roomCode);
      if (!room) throw new Error('Not in a room.');
      if (room.hostId !== user.id) throw new Error('Only the host can start the game.');
      roomManager.startGame(room);
      cb && cb({ ok: true });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('place_bid', async ({ bid }, cb) => {
    try {
      const room = roomManager.getRoom(socket.data.roomCode);
      if (!room || !room.game) throw new Error('No active game.');
      const seat = room.seats.find(s => s.userId === user.id);
      await roomManager.handleBid(room, seat.id, Number(bid));
      cb && cb({ ok: true });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('play_card', async ({ card }, cb) => {
    try {
      const room = roomManager.getRoom(socket.data.roomCode);
      if (!room || !room.game) throw new Error('No active game.');
      const seat = room.seats.find(s => s.userId === user.id);
      await roomManager.handlePlay(room, seat.id, card);
      cb && cb({ ok: true });
    } catch (e) {
      cb && cb({ ok: false, error: e.message });
    }
  });

  socket.on('leave_room', (_, cb) => {
    const room = roomManager.getRoom(socket.data.roomCode);
    if (room) {
      const seat = room.seats.find(s => s.userId === user.id);
      if (seat && room.status === 'waiting') roomManager.removeSeat(room, seat.id);
      else if (seat) seat.connected = false;
      socket.leave(room.code);
      roomManager.broadcastState(room);
    }
    socket.data.roomCode = null;
    cb && cb({ ok: true });
  });

  socket.on('disconnect', () => {
    const room = roomManager.getRoom(socket.data.roomCode);
    if (!room) return;
    const seat = room.seats.find(s => s.userId === user.id);
    if (seat) {
      if (room.status === 'waiting') roomManager.removeSeat(room, seat.id);
      else seat.connected = false;
      roomManager.broadcastState(room);
    }
  });
});

const PORT = process.env.PORT || 3000;
async function start() {
  await db.init();
  server.listen(PORT, '0.0.0.0', () => console.log(`German Bridge server listening on port ${PORT}`));
}
start().catch(error => { console.error('Database startup failed:', error); process.exit(1); });

function shutdown(signal) {
  console.log(`${signal} received; shutting down.`);
  io.close(() => {
    db.close().finally(() => process.exit(0));
  });
}

process.once('SIGTERM', () => shutdown('SIGTERM'));
process.once('SIGINT', () => shutdown('SIGINT'));
