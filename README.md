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
GET  /              # dashboard
GET  /robots.txt    # the honeypot rules
GET  /api/stats     # JSON: per-bot summary + recent violations
GET  /favicon.ico   # 🤖
POST /mcp           # MCP server (revision 2026-07-28), see below
```

### MCP endpoint

`POST /mcp` is a stateless Model Context Protocol server. Revision
`2026-07-28` removed the `initialize` handshake and protocol-level
sessions, so every request is self-contained and the whole server is a
pure function over the already-cached `/api/stats` snapshot
([`app/mcp.py`](app/mcp.py)). It answers the three methods the spec
requires — `server/discover`, `tools/list`, `tools/call` — and exposes
two read-only tools: `get_compliance_stats` (the full scoreboard) and
`check_bot` (one crawler, by display name or User-Agent string). There
are no write operations.

```bash
curl -sX POST https://goodbot-badbot.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/list' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

`GET` and `DELETE` return `405` — this revision has no GET stream and no
session teardown.

## Agent discoverability

The site implements the HTTP-layer agent-readiness signals: a sitemap
referenced from `robots.txt`, RFC 8288 `Link` headers on the homepage,
Content Signals declaring the AI-usage policy (`search=yes, ai-input=yes,
ai-train=no`), content negotiation for `Accept: text/markdown`, and a
JWKS at `/.well-known/http-message-signatures-directory` for Web Bot
Auth identity.

Beyond those, five surfaces are logged as **Discovery Reads** — the
inverse of a honeypot hit, an agent deliberately doing discovery rather
than ignoring a rule: `/llms.txt`, `agents.md` (served at `/AGENTS.md`,
`/agents.md` and `/.well-known/agents.md`, logged per probe location so
the three are distinguishable), the grounding pages under `/facts`, the
RFC 9264 catalog at `/.well-known/api-catalog`, the ARD manifest at
`/.well-known/ai-catalog.json`, and calls to `/mcp`. Reading or calling
any of them is never a violation.

`/mcp` is the only one that is an *invocation* surface rather than a
document, and the only one with no discovery standard behind it: nothing
in any spec tells an agent that path exists. So it is announced in the
ARD manifest, `llms.txt` and `agents.md`, and deliberately left **out**
of the homepage `Link` header. A bot that calls `/mcp` having never read
a discovery file guessed the path; one that reads `ai-catalog.json`
first followed an advertisement. Both land in the same log, so the two
cases separate by query rather than by schema — which is the open
question [Dries Buytaert flagged][dries] when he shipped an MCP endpoint
with nowhere to advertise it.

[dries]: https://dri.es/helping-agents-discover-my-site-search-with-mcp

DNS for AI Discovery (DNS-AID) is still intentionally **not**
implemented. A SVCB record would have to be maintained in DNS by hand
and cannot be observed the way an HTTP fetch can, so it adds a
maintenance surface without adding a measurement.

Note that the site's `agents.md` is not the repository
[`AGENTS.md`](AGENTS.md) coding-agent standard, which lives in the repo
root for tools working on this codebase.

## Privacy

IP addresses are SHA-256 hashed and truncated to the first 16 hex chars
before storage. The raw IP never touches disk.

## License

MIT
