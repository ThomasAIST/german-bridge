const Api = (() => {
  const TOKEN_KEY = 'gb_token';
  const USER_KEY = 'gb_user';

  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; }
  }
  function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  async function req(method, url, body) {
    const res = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed.');
    return data;
  }

  async function register(username, password) {
    const data = await req('POST', '/api/register', { username, password });
    setSession(data.token, data.user);
    return data;
  }
  async function login(username, password) {
    const data = await req('POST', '/api/login', { username, password });
    setSession(data.token, data.user);
    return data;
  }
  function logout() { clearSession(); }
  function profile() { return req('GET', '/api/profile'); }
  function gameDetail(id) { return req('GET', `/api/games/${id}`); }

  return { getToken, getUser, setSession, clearSession, register, login, logout, profile, gameDetail };
})();

const Sockets = (() => {
  let socket = null;
  function connect() {
    if (socket) return socket;
    socket = io({ auth: { token: Api.getToken() } });
    return socket;
  }
  function get() { return socket; }
  function disconnect() {
    if (socket) { socket.disconnect(); socket = null; }
  }
  return { connect, get, disconnect };
})();
