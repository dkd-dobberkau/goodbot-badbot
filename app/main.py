"""
goodbot-badbot.com — AI Crawler robots.txt compliance monitor
"""

import hashlib
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = Path("data/crawls.db")

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


def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                path        TEXT NOT NULL,
                user_agent  TEXT,
                bot_key     TEXT,
                bot_name    TEXT,
                operator    TEXT,
                ip_hash     TEXT,
                is_honeypot INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def identify_bot(user_agent: str) -> tuple[str | None, str | None, str | None]:
    if not user_agent:
        return None, None, None
    ua_lower = user_agent.lower()
    for key, (name, operator) in KNOWN_BOTS.items():
        if key in ua_lower:
            return key, name, operator
    return None, None, None


def log_visit(path: str, user_agent: str, ip: str, is_honeypot: bool):
    bot_key, bot_name, operator = identify_bot(user_agent)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
    with get_db() as conn:
        conn.execute(
            """INSERT INTO visits (ts, path, user_agent, bot_key, bot_name, operator, ip_hash, is_honeypot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.utcnow().isoformat(), path, user_agent,
             bot_key, bot_name, operator, ip_hash, int(is_honeypot))
        )
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


# ── robots.txt ──────────────────────────────────────────────────────────────

ROBOTS_TXT = """User-agent: *
Disallow: /do-not-crawl/
Disallow: /private/
Disallow: /honeypot/
Disallow: /training-data-forbidden/
Disallow: /no-ai-allowed/
Disallow: /robots-test/

# This site monitors whether AI crawlers respect robots.txt.
# Every request to the paths above is logged as a violation.
# Results are published at https://goodbot-badbot.com/results

User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: OAI-SearchBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: cohere-ai
Disallow: /
"""

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    log_visit("/robots.txt", ua, ip, is_honeypot=False)
    return ROBOTS_TXT


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
    log_visit(str(request.url.path), ua, ip, is_honeypot=True)
    return PlainTextResponse("", status_code=200)


# ── API: results ─────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    with get_db() as conn:
        # Summary per bot
        rows = conn.execute("""
            SELECT bot_name, operator,
                   COUNT(*) as total_visits,
                   SUM(is_honeypot) as violations,
                   MAX(ts) as last_seen
            FROM visits
            WHERE bot_name IS NOT NULL
            GROUP BY bot_name, operator
            ORDER BY violations DESC, total_visits DESC
        """).fetchall()

        # Recent violations
        recent = conn.execute("""
            SELECT ts, path, bot_name, operator, user_agent
            FROM visits
            WHERE is_honeypot = 1
            ORDER BY ts DESC
            LIMIT 20
        """).fetchall()

        total_violations = conn.execute(
            "SELECT COUNT(*) FROM visits WHERE is_honeypot = 1"
        ).fetchone()[0]

        total_bots = conn.execute(
            "SELECT COUNT(DISTINCT bot_name) FROM visits WHERE bot_name IS NOT NULL"
        ).fetchone()[0]

    return {
        "summary": [dict(r) for r in rows],
        "recent_violations": [dict(r) for r in recent],
        "total_violations": total_violations,
        "total_bots_seen": total_bots,
    }


# ── Frontend ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html") as f:
        return f.read()
