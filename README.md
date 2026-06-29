# goodbot-badbot

> Live at **<https://goodbot-badbot.com>**

A small public experiment that measures whether AI crawlers actually respect
`robots.txt`. The site declares six honeypot paths as `Disallow`. Any request
to one of them — by any user-agent — is logged as a violation and shown on
the public dashboard in real time.

The rest of the site is open to all bots, so compliance with a single
`Disallow` rule can be measured cleanly: a respectful crawler hits the
homepage and stops; a non-respectful one keeps going into the honeypots.

## Honeypot paths

```
/do-not-crawl/             linked from homepage
/training-data-forbidden/  linked from homepage
/no-ai-allowed/            linked from homepage

/private/                  unlinked anywhere
/honeypot/                 unlinked anywhere
/robots-test/              unlinked anywhere
```

All six listed in [`/robots.txt`](https://goodbot-badbot.com/robots.txt)
as `Disallow`. Any hit on any of them is a violation, but the two
groups measure subtly different things:

- **Linked** (three paths, with visible `<a href>` on the homepage):
  catches crawlers that follow links and ignore the corresponding
  Disallow rule. The clearest possible signal of "didn't respect
  robots.txt."
- **Unlinked** (three paths, no `<a>` anywhere on the site): the only
  way to discover them is to read `/robots.txt` and either use the
  Disallow list as a seed for crawling ("treasure map" anti-pattern)
  or guess paths from common names. A hit here implies the bot
  actively used robots.txt as input.

Without the linked subset, the site would only catch the second
behaviour. Without the unlinked subset, the site couldn't distinguish
"used robots.txt as a seed" from "happened to find a link."

## Identified bots

Visits are tagged with the operator when a known user-agent substring is
recognised (GPTBot, ClaudeBot, CCBot, Bytespider, PerplexityBot,
Google-Extended, Applebot-Extended, Diffbot, cohere-ai, YouBot and others).
Unknown user-agents are still logged, just without attribution.

## Stack

- FastAPI (Python 3.12, async)
- aiomysql against MySQL 8.4
- Vanilla HTML / CSS / no JS framework
- Docker for both local dev and production
- Self-hosted Google Fonts, no external CDN at runtime

## Local dev

```bash
docker compose up -d --build
open http://localhost:8000
```

This brings up the FastAPI app and a `mysql:8.4` service with a healthcheck;
the app waits for the DB and creates its schema on startup. Connection
settings come from the `MYSQL_*` env vars in `docker-compose.yml`.

## API

```
GET /              # dashboard
GET /robots.txt    # the honeypot rules
GET /api/stats     # JSON: per-bot summary + recent violations
GET /favicon.ico   # 🤖
```

## Agent discoverability

The site implements the HTTP-layer agent-readiness signals: a sitemap
referenced from `robots.txt`, RFC 8288 `Link` headers on the homepage,
Content Signals declaring the AI-usage policy (`search=yes, ai-input=yes,
ai-train=no`), content negotiation for `Accept: text/markdown`, and a
JWKS at `/.well-known/http-message-signatures-directory` for Web Bot
Auth identity.

DNS for AI Discovery (DNS-AID) is intentionally **not** implemented.
DNS-AID exists to point agents at A2A / MCP / JSON-RPC endpoints;
goodbot-badbot has no such endpoint to advertise. Publishing a SVCB
record pointing at the HTML dashboard or the stats JSON would be
compliance theatre. The site is an observer of agents, not an agent.

For the same reason there is no `ai-catalog.json` (ARD) manifest: it
advertises agent/tool endpoints the site does not have. There **is** a
short `agents.md`, served at `/AGENTS.md`, `/agents.md`, and
`/.well-known/agents.md`, but only as a *measurement surface* — it
states plainly that the site has no callable endpoint, and every read is
logged (per probe location, so the three are distinguishable) to observe
which agents reach for it. This is not the repository
[`AGENTS.md`](AGENTS.md) coding-agent standard, which lives in the repo
root for tools working on this codebase.

## Privacy

IP addresses are SHA-256 hashed and truncated to the first 16 hex chars
before storage. The raw IP never touches disk.

## License

MIT
