const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const db = require('./db');

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me';

function register(username, password) {
  username = String(username || '').trim();
  if (username.length < 3 || username.length > 20) {
    throw new Error('Username must be 3-20 characters.');
  }
  if (!password || password.length < 4) {
    throw new Error('Password must be at least 4 characters.');
  }
  const existing = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (existing) throw new Error('That username is already taken.');

  const hash = bcrypt.hashSync(password, 10);
  const info = db.prepare('INSERT INTO users (username, password_hash) VALUES (?, ?)').run(username, hash);
  return makeToken({ id: info.lastInsertRowid, username });
}

function login(username, password) {
  const user = db.prepare('SELECT * FROM users WHERE username = ?').get(String(username || '').trim());
  if (!user) throw new Error('Invalid username or password.');
  if (!bcrypt.compareSync(password || '', user.password_hash)) {
    throw new Error('Invalid username or password.');
  }
  return makeToken({ id: user.id, username: user.username });
}

function makeToken(payload) {
  const token = jwt.sign(payload, JWT_SECRET, { expiresIn: '30d' });
  return { token, user: payload };
}

function verifyToken(token) {
  try {
    return jwt.verify(token, JWT_SECRET);
  } catch (e) {
    return null;
  }
}

// Express middleware: requires Authorization: Bearer <token>
function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  const payload = token && verifyToken(token);
  if (!payload) return res.status(401).json({ error: 'Not authenticated.' });
  req.user = payload;
  next();
}

module.exports = { register, login, verifyToken, requireAuth, JWT_SECRET };
