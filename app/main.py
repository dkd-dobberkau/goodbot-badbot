"""
goodbot-badbot.com — AI Crawler robots.txt compliance monitor
"""

import hashlib
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiomysql
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

# Hard caps to keep oversized inputs from blowing past column limits or
# bloating the DB. VARCHAR(512) is the path column; UA TEXT is generous.
MAX_PATH_LEN = 500
MAX_UA_LEN = 1024

# Rate-limit rules: (path-prefix, requests-per-minute). First match wins.
# Honeypots and static-content routes are protected separately because a
# honeypot flood should not eat the budget for legit /robots.txt or /api/stats
# traffic from the same IP.
RATE_LIMIT_RULES = (
    ("/api/stats",              60),
    ("/robots.txt",             60),
    ("/do-not-crawl",           30),
    ("/private",                30),
    ("/honeypot",               30),
    ("/training-data-forbidden", 30),
    ("/no-ai-allowed",          30),
    ("/robots-test",            30),
)

# Known AI crawlers: (user-agent substring, display name, operator)
KNOWN_BOTS = {
    "gptbot":           ("GPTBot",            "OpenAI"),
    "chatgpt-user":     ("ChatGPT-User",       "OpenAI"),
    "oai-searchbot":    ("OAI-SearchBot",      "OpenAI"),
    "claudebot":        ("ClaudeBot",          "Anthropic"),
    "claude-web":       ("Claude-Web",         "Anthropic"),
    "ccbot":            ("CCBot",              "Common Crawl"),
    "bytespider":       ("Bytespider",         "ByteDance"),
    "amazonbot":        ("Amazonbot",          "Amazon"),
    "applebot":         ("Applebot-Extended",  "Apple"),
    "diffbot":          ("Diffbot",            "Diffbot"),
    "facebookbot":      ("FacebookBot",        "Meta"),
    "meta-externalagent": ("Meta-ExternalAgent", "Meta"),
    "google-extended":  ("Google-Extended",    "Google"),
    "googleother":      ("GoogleOther",        "Google"),
    "perplexitybot":    ("PerplexityBot",      "Perplexity"),
    "youbot":           ("YouBot",             "You.com"),
    "cohere-ai":        ("cohere-ai",          "Cohere"),
    "anthropic-ai":     ("anthropic-ai",       "Anthropic"),
    "omgili":           ("Omgili",             "Webz.io"),
    "iaskspider":       ("IaskSpider",         "iAsk"),
}

# Honeypot paths (blocked in robots.txt)
HONEYPOT_PATHS = [
    "/do-not-crawl",
    "/private",
    "/honeypot",
    "/training-data-forbidden",
    "/no-ai-allowed",
    "/robots-test",
]


DB_CONFIG = {
    "host":     os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
    "db":       os.getenv("MYSQL_DB", "goodbot"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "charset":  "utf8mb4",
    "autocommit": True,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id          BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    ts          DATETIME(6) NOT NULL,
    path        VARCHAR(512) NOT NULL,
    user_agent  TEXT,
    bot_key     VARCHAR(64),
    bot_name    VARCHAR(64),
    operator    VARCHAR(64),
    ip_hash     CHAR(16),
    is_honeypot TINYINT(1) NOT NULL DEFAULT 0,
    KEY idx_visits_bot_name (bot_name),
    KEY idx_visits_is_honeypot_ts (is_honeypot, ts)
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def identify_bot(user_agent: str) -> tuple[str | None, str | None, str | None]:
    if not user_agent:
        return None, None, None
    ua_lower = user_agent.lower()
    for key, (name, operator) in KNOWN_BOTS.items():
        if key in ua_lower:
            return key, name, operator
    return None, None, None


async def log_visit(pool, path: str, user_agent: str, ip: str, is_honeypot: bool):
    path = (path or "")[:MAX_PATH_LEN]
    user_agent = (user_agent or "")[:MAX_UA_LEN]
    bot_key, bot_name, operator = identify_bot(user_agent)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
    ts = datetime.now(timezone.utc).replace(tzinfo=None)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO visits
                   (ts, path, user_agent, bot_key, bot_name, operator, ip_hash, is_honeypot)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (ts, path, user_agent, bot_key, bot_name, operator, ip_hash, int(is_honeypot)),
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await aiomysql.create_pool(minsize=2, maxsize=20, **DB_CONFIG)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SCHEMA)
    app.state.db_pool = pool
    yield
    pool.close()
    await pool.wait_closed()


app = FastAPI(lifespan=lifespan)
app.mount("/vendor", StaticFiles(directory="vendor"), name="vendor")


# In-memory sliding-window rate limiter, keyed on (client IP, matched prefix).
# Survives only for the life of one container, which is fine: each new container
# gets a fresh window, and a bad actor still has to start over.
_rate_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _rate_check(key: tuple[str, str], limit: int, window_s: int = 60) -> bool:
    now = time.monotonic()
    cutoff = now - window_s
    q = _rate_windows[key]
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    for prefix, limit in RATE_LIMIT_RULES:
        if path == prefix or path.startswith(prefix + "/"):
            ip = (request.client.host if request.client else None) or "unknown"
            if not _rate_check((ip, prefix), limit):
                return PlainTextResponse("Too Many Requests", status_code=429)
            break
    return await call_next(request)


# ── robots.txt ──────────────────────────────────────────────────────────────

ROBOTS_TXT = """# This site monitors whether crawlers respect robots.txt.
# The paths listed below as Disallow are honeypots.
# Any request to them is logged as a violation, regardless of
# user-agent. The rest of the site is open to all bots so that
# compliance can actually be measured.
# Results are published at https://goodbot-badbot.com

User-agent: *
Disallow: /do-not-crawl/
Disallow: /private/
Disallow: /honeypot/
Disallow: /training-data-forbidden/
Disallow: /no-ai-allowed/
Disallow: /robots-test/
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    await log_visit(app.state.db_pool, "/robots.txt", ua, ip, is_honeypot=False)
    return ROBOTS_TXT


# ── llms.txt (llmstxt.org standard) ──────────────────────────────────────────

LLMS_TXT = """# goodbot-badbot

> Live monitor of AI crawler robots.txt compliance. Six honeypot paths are
> listed as Disallow in /robots.txt. Any crawler that visits one of them is
> logged as a violation, regardless of user-agent. Results are published in
> real time on the public dashboard.

## How it works

The site is open to all crawlers. Only six honeypot paths are blocked via
the global `User-agent: *` Disallow rule. A compliant crawler hits the
homepage and stops at the boundary; a non-compliant crawler keeps going and
trips a honeypot, where its visit is recorded.

## Live data

- [Public dashboard](https://goodbot-badbot.com/): per-bot scoreboard and live violation feed
- [JSON stats](https://goodbot-badbot.com/api/stats): machine-readable summary
- [robots.txt](https://goodbot-badbot.com/robots.txt): the honeypot rules

## Honeypot paths

- `/do-not-crawl/`
- `/private/`
- `/honeypot/`
- `/training-data-forbidden/`
- `/no-ai-allowed/`
- `/robots-test/`

## Source code

- [GitHub repository](https://github.com/dkd-dobberkau/goodbot-badbot): MIT-licensed, FastAPI + MySQL

## Privacy

Logged IPs are SHA-256 hashed and truncated to 16 hex chars before storage.
The raw IP is never written to disk.
"""


@app.get("/llms.txt")
async def llms_txt():
    return Response(content=LLMS_TXT, media_type="text/markdown; charset=utf-8")


# ── Honeypot endpoints ───────────────────────────────────────────────────────

@app.get("/do-not-crawl/{rest:path}")
@app.get("/private/{rest:path}")
@app.get("/honeypot/{rest:path}")
@app.get("/training-data-forbidden/{rest:path}")
@app.get("/no-ai-allowed/{rest:path}")
@app.get("/robots-test/{rest:path}")
async def honeypot(request: Request, rest: str = ""):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    await log_visit(app.state.db_pool, str(request.url.path), ua, ip, is_honeypot=True)
    return PlainTextResponse("", status_code=200)


# ── API: results ─────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats(request: Request):
    async with app.state.db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT bot_name, operator,
                       COUNT(*) AS total_visits,
                       CAST(SUM(is_honeypot) AS UNSIGNED) AS violations,
                       MAX(ts) AS last_seen
                FROM visits
                WHERE bot_name IS NOT NULL
                GROUP BY bot_name, operator
                ORDER BY violations DESC, total_visits DESC
            """)
            summary = await cur.fetchall()

            await cur.execute("""
                SELECT ts, path, bot_name, operator, user_agent
                FROM visits
                WHERE is_honeypot = 1
                ORDER BY ts DESC
                LIMIT 20
            """)
            recent = await cur.fetchall()

            await cur.execute("SELECT COUNT(*) AS c FROM visits WHERE is_honeypot = 1")
            total_violations = (await cur.fetchone())["c"]

            await cur.execute("SELECT COUNT(DISTINCT bot_name) AS c FROM visits WHERE bot_name IS NOT NULL")
            total_bots = (await cur.fetchone())["c"]

    return {
        "summary": summary,
        "recent_violations": recent,
        "total_violations": total_violations,
        "total_bots_seen": total_bots,
    }


# ── Favicon ──────────────────────────────────────────────────────────────────

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<text x="50%" y="54%" font-size="26" text-anchor="middle" '
    'dominant-baseline="central">🤖</text></svg>'
)


@app.get("/favicon.ico")
async def favicon():
    return Response(
        content=FAVICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Frontend ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html") as f:
        return f.read()
