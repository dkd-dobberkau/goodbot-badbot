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
/do-not-crawl/
/private/
/honeypot/
/training-data-forbidden/
/no-ai-allowed/
/robots-test/
```

All listed in [`/robots.txt`](https://goodbot-badbot.com/robots.txt) as
`Disallow`. Any hit on these paths = violation.

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

## Privacy

IP addresses are SHA-256 hashed and truncated to the first 16 hex chars
before storage. The raw IP never touches disk.

## License

MIT
