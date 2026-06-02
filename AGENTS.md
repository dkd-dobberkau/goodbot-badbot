# AGENTS.md

Guidance for AI coding agents (Claude, Cursor, Aider, Copilot, etc.) working
on this repository. Human contributors can skim this for a quick orientation
too.

## What this project is

A FastAPI app that publishes honeypot paths via `robots.txt` and logs every
crawler that visits them anyway. The data is exposed as a live dashboard and
a JSON API at <https://goodbot-badbot.com>.

The point of the experiment is to measure compliance with a single
`Disallow` rule, so the rest of the site is intentionally open to all bots.
Do not "harden" `robots.txt` by adding per-user-agent blocks — that breaks
the measurement.

## Stack

- Python 3.12, FastAPI, async throughout
- `aiomysql` connection pool against MySQL 8.4
- Vanilla HTML / inline CSS; no frontend build step
- Docker for local dev and production
- Mittwald container hosting + managed MySQL service for production

## Layout

```
app/main.py                       single-file FastAPI app (routes, DB, schema)
templates/index.html              dashboard, vanilla JS that polls /api/stats
vendor/css, vendor/fonts          self-hosted Google Fonts (no CDN at runtime)
docker-compose.yml                local dev: web + mysql 8.4
docker-compose.mittwald.yml       production stack definition
deploy.sh                         build → push → mw stack deploy → recreate
.deploy.env / .deploy.env.example template + gitignored real secrets
```

Schema lives inside `app/main.py` (`SCHEMA` constant). It is created with
`CREATE TABLE IF NOT EXISTS` on startup; no Alembic / migration tool. If you
change the schema in a way that needs a migration, write an ad-hoc SQL
statement and call it explicitly.

## Local dev

```bash
docker compose up -d --build
curl http://localhost:8000/api/stats
```

The web container waits for the MySQL healthcheck before starting. Iterating
on `app/main.py` requires a rebuild (`docker compose up -d --build`) — the
code is COPYd into the image, not bind-mounted.

## Conventions

- Async all the way. New endpoints must be `async def` and must not block on
  sync I/O.
- Parameterised SQL only. `%s` placeholders, never string interpolation.
- Timestamps stored as naive UTC `DATETIME(6)`. Use
  `datetime.now(timezone.utc).replace(tzinfo=None)` — never `utcnow()`
  (deprecated) and never local time.
- Comments only where the *why* is non-obvious. Identifier names should
  carry the *what*.
- No new dependencies without a clear reason. The whole stack is intentionally
  small (FastAPI + uvicorn + aiomysql + cryptography).

## Deploy

`./deploy.sh` (with `.deploy.env` populated) builds an immutable
`ghcr.io/dkd-dobberkau/goodbot-badbot:<git-sha>` image, pushes it, deploys
the Mittwald stack via `mw stack deploy`, then forces a container recreate
(stack deploy alone does not always trigger a pull). A smoke test against
`https://goodbot-badbot.com/api/stats` runs at the end.

Do not commit anything from `.deploy.env`. Secrets only travel through that
file or through env vars.

## Things to leave alone

- `/robots.txt` content (intentional; see top of file)
- The honeypot path list — those URLs are part of the experiment's contract
- IP hashing (SHA-256 → first 16 chars) — changing it breaks privacy guarantees
