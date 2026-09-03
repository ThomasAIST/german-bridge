# German Bridge Online — Prototype

A working, single-process playground for the trick-taking card game **German
Bridge**: accounts, matchmaking, private rooms, bots, and game history — the
same shape as chess.com's lobby, scoped down to something you can run on your
laptop in one command.

## Stack (and why)

- **Node.js + Express** — REST endpoints for register/login and profile/history.
- **Socket.IO** — realtime table state (bids, cards played, turn order) pushed
  to every seat as it happens.
- **better-sqlite3** — zero-setup embedded database for accounts and finished
  games. No separate DB server to run.
- **Vanilla JS + Tailwind (CDN) frontend** — no build step. Open the page and
  it works. Swapping this for React/Vite later is a contained, optional step
  (see "Extend" below) once the game logic itself isn't in question.

This is a deliberate choice for a *prototype*: one server process, in-memory
room/game state, SQLite for anything that must survive a restart (accounts,
history). It'll comfortably hold a few dozen concurrent tables. Scaling past
that is a real extension, not a rewrite — see below.

## Rules implemented

- 2–7 players, standard 52-card deck, Aces high.
- Round *n* deals *n* cards to each player (round 1 = 1 card, round 2 = 2
  cards, …) up to `floor(52 / players)` rounds.
- Trump suit is drawn at random each round.
- Starting left of the dealer, everyone bids an exact trick count — no
  passing, 0 is legal.
- Must follow suit if able. Highest trump wins the trick; otherwise highest
  card of the suit led. Trick winner leads next.
- Scoring per round: bid met exactly → `10 + tricks²`. Missed → `-(diff²)`.
- Highest total after the final round wins.

This is the core commonly-cited German Bridge ruleset. I did not implement
the "dealer can't bid to make the total equal the hand size" restriction some
house rules use — see "Extend" if you want it.

## Running it

You'll need Node.js 18+ (built and tested on Node 22).

```bash
cd german-bridge
npm install
cp .env.example .env      # optional: set a real JWT_SECRET
npm start
```

Open `http://localhost:3000`. Register an account, then from the lobby you
can:

- **Quick Match** — joins an open table (default size 4); if it isn't full
  after 15 seconds, remaining seats fill with bots automatically.
- **Practice vs Bots** — instantly starts a private table filled with bots.
- **Private Room** — creates a room code to share, or joins one you were
  given. The host can add bots to empty seats and starts the game manually.

To actually test multiplayer locally, open the app in two browser
windows/profiles (or two devices on the same network using your machine's
LAN IP instead of `localhost`), register two accounts, and use a private room
code to seat them both.

Data persists in `data.sqlite` in the project root (accounts + finished game
history). Delete that file to reset everything.

## Project layout

```
server/
  index.js       Express app + Socket.IO wiring (the "glue")
  db.js          SQLite schema (users, games, game_players)
  auth.js        register/login/JWT
  gameEngine.js  Pure game rules — deal, bid, play, score. No I/O.
  bot.js         Heuristic bot: bid estimate + card selection
  rooms.js       Room/lobby/matchmaking manager, ties engine + bots + sockets
public/
  index.html
  css/style.css  Felt table, card visuals, animations
  js/api.js      REST + socket connection helpers
  js/cards.js    Card render helpers
  js/views.js    HTML templates per screen
  js/app.js      Client state + routing + event wiring
```

`gameEngine.js` has no dependency on Express, Socket.IO, or the database —
it's plain functions over a state object, which is what let me sanity-check
it directly: I ran full simulated games (bots on both sides) for every
player count from 2–7 and asserted every round's tricks summed correctly
with zero illegal moves, before wiring it to any networking code.

## What I'd extend first

Roughly in the order I'd actually do it:

1. **Reconnection handling.** Right now a disconnect mid-game just marks a
   seat `connected: false`; there's no grace-period auto-bot-takeover or
   reconnect-and-resume UI. For a real product this is priority #1 — people's
   wifi drops mid-hand.
2. **Turn timers.** No time limit on human turns yet. Add a per-turn clock
   (e.g. 20s) that auto-plays a random legal card / auto-bids 0 on timeout,
   both to keep games moving and to make quick-match viable with strangers.
3. **A smarter bot.** The current bot is a hand-strength heuristic — decent
   for bidding, greedy-but-reasonable for play. A real upgrade is Monte Carlo
   playouts for bidding (deal out plausible opponent hands many times, count
   average tricks) and basic card-counting during play (track which cards of
   each suit are still out).
4. **Elo/rating and a leaderboard.** The `game_players` table already has
   everything needed (placement, score, timestamps) — add a `rating` column
   on `users`, update it after `persistGame()`, and add a `/api/leaderboard`
   route + lobby widget.
5. **Chat and emotes** in the room/table — cheap to add as another Socket.IO
   event, high value for a "playground" product.
6. **Horizontal scaling.** Move room/game state from the in-process `Map` in
   `rooms.js` into Redis (or Postgres + a pub/sub layer) once you need more
   than one server process; Socket.IO's Redis adapter handles cross-process
   broadcast with minimal code change since the room code is already the
   Socket.IO room name.
7. **The dealer bid restriction house rule** (if you want it): in
   `gameEngine.placeBid`, when the current bidder is the dealer, disallow the
   one bid value that would make total bids equal the hand size.
8. **Swap the frontend to a component framework** once the UI grows past what
   template strings can comfortably manage — the socket/API layer in
   `api.js` is already framework-agnostic, so this is a `views.js`/`app.js`
   rewrite, not a backend change.
9. **Spectator mode** for finished/in-progress private rooms, reusing
   `viewFor()` with a null hand.
