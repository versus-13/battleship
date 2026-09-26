# Battleship — web

Browser game: human vs model (the AI runs in the browser via onnxruntime-web)
and human vs human online (the server is the referee). No login: the server
issues the player id and secret, the client keeps them in localStorage.

```
web/
  frontend/   Vite + React + TypeScript
  server/     FastAPI + Postgres (H2H referee, telemetry, API for the mobile app)
  fixtures/   references generated from model/ for cross-checking the engines (engine.json, onnx.json)
```

## Development

Requires: Node 20, Python 3.11, Postgres (locally on :5432).

```bash
# server
cd web/server
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest pytest-asyncio httpx
createdb battleship && createdb battleship_test
.venv/bin/alembic upgrade head
BS_DATABASE_URL=postgresql+asyncpg://localhost:5432/battleship_test .venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd web/frontend
npm install
npm run dev            # http://localhost:5173, /api and /ws are proxied to :8000
```

Server settings are `BS_*` environment variables (see `server/app/config.py`):
`BS_DATABASE_URL`, `BS_CORS_ORIGINS`, H2H timers, `BS_STATIC_DIR` to serve the built frontend.

## Tests

```bash
cd web/server && .venv/bin/pytest          # rules ≡ game.py, moderation, REST, WebSocket match
cd web/frontend && npm test                 # engine ≡ game.py, ONNX in wasm ≡ ORT in Python
cd web/frontend && node e2e/local.mjs       # a game vs the model in headless Chromium (both dev servers required)
cd web/frontend && node e2e/online.mjs      # two players: room by link, reconnect, end of game
cd web/frontend && node e2e/queue.mjs       # name moderation, random queue, surrender
```

Fixtures are regenerated from Python (`model/`):
`python -m battleship.fixtures` (engine.json) and `python -m battleship.export_onnx` (onnx.json + the model).

## Deploying to a VPS

The project ships only the containers, bound to localhost: `api` on 127.0.0.1:8000 and
`frontend` (static files) on 127.0.0.1:8080. Postgres is the `db` container, not exposed.
The reverse proxy with TLS is not part of the project and is set up separately; it must:

* route `/api`, `/ws`, `/healthz` → `127.0.0.1:8000`, everything else → `127.0.0.1:8080`;
* pass the WebSocket upgrade on `/ws` (`Upgrade`/`Connection` headers, HTTP/1.1) with a
  read timeout well above the match timers — otherwise H2H connections drop mid-game;
* set `X-Forwarded-Proto`/`X-Forwarded-For` (uvicorn runs with `--proxy-headers`);
* not cache `/` — `index.html` must be re-fetched after each deploy (the frontend already
  sends `Cache-Control: no-cache` for it and long-lived headers for `/assets/`, `/model/`).

Images are built by GitHub Actions (`.github/workflows/web.yml`): tests on every push and
PR, on a push to `master` — build and publish to GHCR:
`ghcr.io/versus-13/battleship-api` and `ghcr.io/versus-13/battleship-frontend`, tags
`latest` and `<sha>`. The VPS needs neither sources nor a build — only Docker and two
files.

Ubuntu 24.04, 1–2 vCPU, 2 GB RAM is enough. The image packages on GitHub must be public
(Package → Settings → Change visibility), otherwise the VPS needs `docker login ghcr.io`
with a `read:packages` token.

```bash
# 1. on the VPS: docker
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER   # re-login

# 2. two files from the repository (web/deploy/) — scp from the dev machine also works
sudo mkdir -p /opt/battleship && sudo chown $USER /opt/battleship && cd /opt/battleship
curl -fsSLO https://raw.githubusercontent.com/versus-13/battleship/master/web/deploy/docker-compose.prod.yml
curl -fsSLO https://raw.githubusercontent.com/versus-13/battleship/master/web/deploy/backup.sh
mv docker-compose.prod.yml docker-compose.yml && chmod +x backup.sh
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" > .env
# optional: UID/GID for api and frontend (default 10001). It must NOT belong to a real
# host user — especially not one in the docker group, which is root-equivalent.
# echo -e "APP_UID=10001\nAPP_GID=10001" >> .env

# name filters live on the host only (see "Name moderation"); the repository copies are a
# starting point. api refuses to start while these files are missing.
mkdir -p moderation && for f in stoplist allowlist; do
  curl -fsSL -o moderation/$f.txt https://raw.githubusercontent.com/versus-13/battleship/master/web/server/app/data/$f.txt
done && chmod 755 moderation && chmod 644 moderation/*.txt
# reports for manual review are written here by api (runs as APP_UID, default 10001)
mkdir -p reports && sudo chown 10001:10001 reports

# 3. containers (migrations run when api starts)
docker compose pull && docker compose up -d
curl -s localhost:8000/healthz        # {"ok":true,...}
curl -sI localhost:8080/ | head -1    # HTTP/1.1 200

# 4. backups (the reverse proxy and firewall are configured separately)
(crontab -l 2>/dev/null; echo "0 4 * * * /opt/battleship/backup.sh") | crontab -
```

**Updating** (once the workflow on `master` is green):

```bash
cd /opt/battleship && docker compose pull && docker compose up -d
```

Restarting `api` drops H2H matches in progress: they live in memory and are not saved (this
includes a winner still clearing the board after a walk-out) — update during quiet hours. Roll back to a specific commit: `TAG=<sha> docker compose up -d`.
Frontend only: `docker compose pull frontend && docker compose up -d frontend`.

Useful: `docker compose logs -f api`, `docker compose exec db psql -U battleship`,
restore from a backup — `docker compose exec -T db pg_restore -U battleship -d battleship -c < backups/file.dump`.

Local image build without a registry — `docker compose up -d --build` from `web/`
(the `docker-compose.yml` in `web/` builds from sources).

**A single worker is mandatory**: H2H matches live in the memory of the `api` process.
Scaling beyond one machine would require Redis for the match registry.

## API (for the mobile app)

Authentication: `POST /api/players` → `{player_id, secret}`; then
`Authorization: Bearer <secret>`. The secret lives on the device, there is no recovery —
losing the storage = a new identity.

| | |
|---|---|
| `GET /api/players/me` | profile and stats |
| `PUT /api/players/me/name` `{name}` | 422 `{detail:{code}}`: `too_short, too_long, invalid_chars, rejected_profanity, rate_limited` |
| `GET /api/players/{id}/stats` | player stats |
| `GET /api/leaderboard?min_games=&limit=` | human-vs-human games only |
| `GET /api/model` | ONNX model version and URL (`obs` float32 [1,8,10,10] → `logits` [1,10,10]) |
| `POST /api/games` | telemetry of a game vs the model, 1–2 logs (see `schemas.GamesIn`); the response is a receipt `{accepted:[id], rejected:[{index, code}]}` |
| `POST /api/rooms` → `{code, match_id, ws_url}` | room by link |
| `GET /api/rooms/{code}`, `POST /api/rooms/{code}/join` | info and join |
| `POST /api/queue` → `queued \| matched` | random queue (poll every 2 s); `DELETE /api/queue` |
| `GET /api/matches/current`, `GET /api/matches/{id}` | current match and its snapshot |
| `POST /api/matches/{id}/report` `{reason}` | a report on the opponent of this match, see "Reports"; always 204 |
| `WS /ws/matches/{id}` | first message `{"t":"hello","token":secret}` |

WebSocket, client → server: `place{ships, mode}`, `shoot{cell}`, `leave`, `ping`, `state`.
Server → client: `state` (full snapshot, on every connection), `opponent_joined`,
`opponent_ready`, `opponent_left{grace_s, reconnect_deadline_ts}`, `opponent_back`, `placed`,
`start{your_turn, deadline_ts}`,
`shot_result` / `opponent_shot` `{cell, result 0|1|2, sunk_cells, revealed, your_turn, alive, deadline_ts, auto, auto_streak}`,
`game_over{winner, you_won, reason, enemy_ships, solo, n_shots, cleared}`, `error{code}`.

Time rules (the server keeps every clock; `*_ts` are unix seconds of the server, the client
only displays them):

* **Move timer** `BS_MOVE_S` = 30 s. When it runs out, the server shoots a random unopened cell
  for the player (`auto: true`); there is no forfeit, the idle player simply plays worse.
  `BS_IDLE_MOVES_LIMIT` = 5 auto-moves in a row ends the match: `reason: idle`.
* **Reconnect budget** `BS_RECONNECT_BUDGET_S` = 90 s per player **per match**, spent while
  offline (from placement on, including never opening the socket). While it lasts, the
  offline player's move timer waits (`deadline_ts: null`), and the opponent sees
  `opponent.reconnect_deadline_ts` in `state`. When the budget is spent, auto-moves resume, and
  `BS_DISCONNECT_AFTER_BUDGET_S` = 120 s more offline ends the match: `reason: disconnect`.
* **Surrender** — `leave` → `reason: resigned`.
* A match left early (`resigned | idle | disconnect`) is a loss for the leaver. The winner gets
  `game_over{solo: true}` without the enemy ships and may keep shooting (`your_turn` stays true,
  no move timer, `BS_SOLO_IDLE_S` = 5 min of inactivity or `leave` ends it). The board is static,
  so clearing it counts towards the winner's average shots. The logs are written after the solo;
  the final `game_over{solo: false, cleared, n_shots}` reveals the ships.

Two numbers per player: the match record (`wins`/`games`, walk-outs count as losses) and skill —
`avg_shots` over **cleared boards only** (`null` if none), which the opponent cannot spoil.
In the logs the server-made moves are `client_info.auto_moves` (indices into `shots`);
`battleship.analysis.compare_moves` skips them. Export outcomes: `finished | lost | resigned | abandoned`.

Placement — `[[idx,…] × 10]`, cells 0..99, `idx = row*10 + col`. Columns А…К, rows 1–10:
"Д6" = col 4, row 5.

### Telemetry

The unit is one attacker against one board; a game vs the model = two logs. Body of
`POST /api/games`:

```json
{"client_game_id": "uuid", "mode": "h2m", "client": "web", "client_version": "web-0.1.0",
 "client_info": {"platform": "MacIntel", "screen": [1440, 900], "touch": false,
                 "placement": "random|manual", "model_backend": "int8-35d9f084"},
 "logs": [
   {"attacker": {"kind": "player"}, "defender": {"kind": "model_board"},
    "ships": [[0,1,2,3], …], "shots": [44, 45, …], "think_ms": [1200, 800, …],
    "started_at": 1800000000.5, "fleet_cleared": true, "won": true},
   {"attacker": {"kind": "model", "version": "int8-35d9f084"}, "defender": {"kind": "player"}, …}
 ]}
```

`think_ms` — time per move (for the model — inference latency), the only thing replay
cannot restore; `client_info` — a whitelist of keys only, no personal data. An unfinished
game is sent on leaving the page with `won: null`. In H2H the server records `think_ms`
and the placement mode (`place{ships, mode}`) itself.

Export: `python -m scripts.export_logs --out logs.jsonl [--all]` → JSONL in the
`model/battleship/telemetry.GameLog` format (`outcome`: `finished` — board cleared,
`lost` — played to the end but the opponent cleared first, `abandoned` — not finished).
Analysis: `cd model && python -m battleship.analyze --logs logs.jsonl --ckpt battleship/net.pt`.

## Name moderation

`server/app/moderation.py` + `data/stoplist.txt` (`=word` — exact match, `~root` —
substring) and `data/allowlist.txt` for false positives. Normalization strips case,
homoglyphs, digit-letters, separators and repeats. Rejected names are not stored, only
a counter of reasons in `name_rejects`.

In production the lists come from the host, `/opt/battleship/moderation/*.txt`, bind-mounted
read-only over the copies in the image, so they are edited without being published. The
repository copies serve the tests and local runs. The lists are read once at startup: after
editing, run `docker compose restart api` (this aborts H2H matches in progress).
Names that are already saved are not re-checked.

Besides the stop-list, `data/reserved.txt` (same format, code `reserved`) rejects names that
pretend to be staff (admin, модератор, поддержка, …), the placeholder word «Игрок»/«Player»
and link tokens (www, com, ru, vk, tg, telegram…); a run of 5+ digits or 6+ digits in total is
`contacts` (phones, messenger ids). `reserved.txt` ships in the image, it is not mounted.
A `~root` shorter than 3 letters after collapsing repeats (`~xxx` → `x`) is checked as a whole
word, otherwise it would reject every name containing that letter.

## Reports

`POST /api/matches/{id}/report {reason}`, `reason` ∈ `name | impersonation | cheating | stalling | bug`.
A report is always about a match: the reporter must have played it (the live match in memory,
otherwise the `h2h_matches` row), the reported player is the opponent — the server decides.
One report per match per reporter (`reports.uq_report_match_reporter`). The answer is always
204 with no body — also for a duplicate or a stranger: the reporter only sees "thanks".

* `name`, `impersonation` — `BS_NAME_REPORT_THRESHOLD` = 3 **different** players reporting the
  **current** name hide it: `name` becomes null (shown as «Игрок#ab12»), `/me` returns
  `name_hidden: true` and the home screen asks for a new one; the same name is refused with
  `name_hidden`, and reports on an old name do not affect a new one.
* `stalling` — stored only: the move timer already punishes it, the logs hold the facts.
* `cheating`, `bug` — stored and written as a text file into `BS_REPORTS_DIR`
  (`/opt/battleship/reports` in production), one file per report, with the match, both
  players, the reported player's move times and the commands to check the match
  (`export_logs --match <id>` → `battleship.analyze`). Review them and delete the files.
  Cheating is never acted on automatically: losers are often sure the winner cheated.

