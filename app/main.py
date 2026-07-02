"""
goodbot-badbot.com — AI Crawler robots.txt compliance monitor
"""

import asyncio
import base64
import hashlib
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiomysql
import http_sfv
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from http_message_signatures import (
    HTTPMessageVerifier,
    HTTPSignatureKeyResolver,
    algorithms,
)

from app import blog, facts

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
    ("/sitemap.xml",            60),
    ("/llms.txt",               60),
    ("/blog",                   60),
    ("/facts",                  60),
    ("/AGENTS.md",              60),
    ("/agents.md",              60),
    ("/.well-known/agents.md",  60),
    ("/.well-known/http-message-signatures-directory", 60),
    ("/do-not-crawl",           30),
    ("/private",                30),
    ("/honeypot",               30),
    ("/training-data-forbidden", 30),
    ("/no-ai-allowed",          30),
    ("/robots-test",            30),
)

SITE_BASE_URL = "https://goodbot-badbot.com"

# Known AI crawlers: (user-agent substring, display name, operator).
# Substring match runs in insertion order — longer/more-specific keys MUST
# come before shorter ones that they contain (applebot-extended before
# applebot, etc.).
KNOWN_BOTS = {
    # OpenAI
    "gptbot":                          ("GPTBot",              "OpenAI"),
    "chatgpt-agent":                   ("ChatGPT-Agent",       "OpenAI"),
    "chatgpt-user":                    ("ChatGPT-User",        "OpenAI"),
    "oai-searchbot":                   ("OAI-SearchBot",       "OpenAI"),
    # Anthropic
    "claudebot":                       ("ClaudeBot",           "Anthropic"),
    "claude-user":                     ("Claude-User",         "Anthropic"),
    "claude-code":                     ("Claude-Code",         "Anthropic"),
    "claude-web":                      ("Claude-Web",          "Anthropic"),
    "anthropic-ai":                    ("anthropic-ai",        "Anthropic"),
    # Google
    "google-extended":                 ("Google-Extended",     "Google"),
    "googleother":                     ("GoogleOther",         "Google"),
    "gemini-deep-research":            ("Gemini-Deep-Research", "Google"),
    "google-notebooklm":               ("NotebookLM",          "Google"),
    # Apple — extended MUST come before the generic applebot match
    "applebot-extended":               ("Applebot-Extended",   "Apple"),
    "applebot":                        ("Applebot",            "Apple"),
    # Meta
    "meta-externalagent":              ("Meta-ExternalAgent",  "Meta"),
    "meta-externalfetcher":            ("Meta-ExternalFetcher", "Meta"),
    "facebookbot":                     ("FacebookBot",         "Meta"),
    # Perplexity
    "perplexitybot":                   ("PerplexityBot",       "Perplexity"),
    "perplexity-user":                 ("Perplexity-User",     "Perplexity"),
    # Amazon
    "amazonbot":                       ("Amazonbot",           "Amazon"),
    "novaact":                         ("Nova Act",            "Amazon"),
    # ByteDance
    "bytespider":                      ("Bytespider",          "ByteDance"),
    # Cohere — full crawler name MUST come before the generic cohere-ai match
    "cohere-training-data-crawler":    ("Cohere-Training-Data-Crawler", "Cohere"),
    "cohere-ai":                       ("cohere-ai",           "Cohere"),
    # Mistral
    "mistralai-user":                  ("MistralAI-User",      "Mistral"),
    # DuckDuckGo
    "duckassistbot":                   ("DuckAssistBot",       "DuckDuckGo"),
    # Common Crawl / data crawlers
    "ccbot":                           ("CCBot",               "Common Crawl"),
    "diffbot":                         ("Diffbot",             "Diffbot"),
    "omgili":                          ("Omgili",              "Webz.io"),
    "webzio-extended":                 ("Webzio-Extended",     "Webz.io"),
    # Other AI search / fetchers
    "youbot":                          ("YouBot",              "You.com"),
    "iaskspider":                      ("IaskSpider",          "iAsk"),
    "phindbot":                        ("PhindBot",            "Phind"),
    "bravebot":                        ("BraveBot",            "Brave"),
    "kagi-fetcher":                    ("Kagi-Fetcher",        "Kagi"),
    "linerbot":                        ("LinerBot",            "Liner"),
    "exabot":                          ("ExaBot",              "Exa"),
    "tavilybot":                       ("TavilyBot",           "Tavily"),
    "firecrawlagent":                  ("FirecrawlAgent",      "Firecrawl"),
    "chatglm-spider":                  ("ChatGLM-Spider",      "Zhipu AI"),
    # Agentic frameworks / IDE tools
    "devin":                           ("Devin",               "Cognition"),
    "manus-user":                      ("Manus-User",          "Manus"),
    "apifybot":                        ("ApifyBot",            "Apify"),
}

# Extend KNOWN_BOTS with Cloudflare Radar's verified-bots directory, scoped to
# the three AI categories. The dataset is vendored next to this file; refresh
# with: curl -sL https://raw.githubusercontent.com/microlinkhq/cloudflare-bot-directory/master/src/index.json -o app/cf_bots.json
# Patterns that overlap with the curated entries above are dropped so the
# longer-first matching invariant (e.g. applebot-extended before applebot) holds.
_CF_BOTS_FILE = Path(__file__).parent / "cf_bots.json"
_CF_AI_CATEGORIES = {"AI_CRAWLER", "AI_ASSISTANT", "AI_SEARCH"}


def _load_cf_bot_additions(known: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    try:
        entries = json.loads(_CF_BOTS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    additions: dict[str, tuple[str, str]] = {}
    for bot in entries:
        if bot.get("category") not in _CF_AI_CATEGORIES:
            continue
        name = bot.get("name") or bot.get("slug")
        operator = bot.get("operator") or "Unknown"
        for raw in bot.get("userAgentPatterns") or []:
            pattern = raw.lower().strip().rstrip("/")
            if not pattern or pattern in known:
                continue
            if any(k in pattern or pattern in k for k in known):
                continue
            additions.setdefault(pattern, (name, operator))
    return dict(sorted(additions.items(), key=lambda kv: -len(kv[0])))


KNOWN_BOTS.update(_load_cf_bot_additions(KNOWN_BOTS))

# Honeypot paths (blocked in robots.txt)
HONEYPOT_PATHS = [
    "/do-not-crawl",
    "/private",
    "/honeypot",
    "/training-data-forbidden",
    "/no-ai-allowed",
    "/robots-test",
]

# Agent/LLM discovery files an agent deliberately fetches to learn how to use
# the site — distinct from honeypots (violations) and from robots/sitemap
# (generic crawler meta). Reads here are the "Discovery Reads" dashboard
# signal. AGENTS_MD_PATHS is the subset served by the agents_md handler; the
# three probe locations are kept separate so we can see which one agents reach
# for, but the dashboard sums them under one "agents.md" column.
AGENTS_MD_PATHS = ("/AGENTS.md", "/agents.md", "/.well-known/agents.md")
DISCOVERY_PATHS = ("/llms.txt", *AGENTS_MD_PATHS)


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
    id               BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    ts               DATETIME(6) NOT NULL,
    path             VARCHAR(512) NOT NULL,
    user_agent       TEXT,
    bot_key          VARCHAR(64),
    bot_name         VARCHAR(64),
    operator         VARCHAR(64),
    ip_hash          CHAR(16),
    is_honeypot      TINYINT(1) NOT NULL DEFAULT 0,
    signature_status VARCHAR(16) NULL,
    KEY idx_visits_bot_name (bot_name),
    KEY idx_visits_is_honeypot_ts (is_honeypot, ts)
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

# MySQL has no ADD COLUMN IF NOT EXISTS, so probe information_schema before
# attempting the ALTER. This is the idempotent way to evolve the schema for
# DBs that pre-date the column (the production DB volume persists across
# deploys; fresh dev DBs get the column via SCHEMA above).
async def _ensure_signature_status_column(cur):
    await cur.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'visits'
          AND COLUMN_NAME = 'signature_status'
        """
    )
    if (await cur.fetchone())[0] == 0:
        await cur.execute("ALTER TABLE visits ADD COLUMN signature_status VARCHAR(16) NULL")


def identify_bot(user_agent: str) -> tuple[str | None, str | None, str | None]:
    if not user_agent:
        return None, None, None
    ua_lower = user_agent.lower()
    for key, (name, operator) in KNOWN_BOTS.items():
        if key in ua_lower:
            return key, name, operator
    return None, None, None


async def log_visit(
    pool,
    path: str,
    user_agent: str,
    ip: str,
    is_honeypot: bool,
    signature_status: str | None = None,
):
    path = (path or "")[:MAX_PATH_LEN]
    user_agent = (user_agent or "")[:MAX_UA_LEN]
    bot_key, bot_name, operator = identify_bot(user_agent)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
    ts = datetime.now(timezone.utc).replace(tzinfo=None)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO visits
                   (ts, path, user_agent, bot_key, bot_name, operator, ip_hash, is_honeypot, signature_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (ts, path, user_agent, bot_key, bot_name, operator, ip_hash, int(is_honeypot), signature_status),
            )


# Dedup meta-visits (robots.txt, sitemap.xml) per (path, bot-identity) within
# a TTL window so an HN-hug doesn't fill the table with identical rows. Honey-
# pot hits stay untouched — every violation is independent signal.
_visit_dedup: dict[tuple[str, str], float] = {}
META_DEDUP_TTL_S = 600


def _should_log_meta_visit(path: str, user_agent: str) -> bool:
    bot_key, _, _ = identify_bot(user_agent)
    identity = bot_key or hashlib.sha256((user_agent or "").encode()).hexdigest()[:16]
    now = time.monotonic()
    last = _visit_dedup.get((path, identity))
    if last is not None and (now - last) < META_DEDUP_TTL_S:
        return False
    _visit_dedup[(path, identity)] = now
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await aiomysql.create_pool(minsize=2, maxsize=20, **DB_CONFIG)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SCHEMA)
            await _ensure_signature_status_column(cur)
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


# ── Web Bot Auth: incoming signature verification ───────────────────────────

# Per-URL JWKS cache. Web Bot Auth says caches should be short-lived because
# operators rotate keys; 1 h is the conservative default.
_jwks_cache: dict[str, tuple[float, dict]] = {}
# One lock per URL so a slow fetch for operator A does not serialise the
# cache double-check for operator B. The locks dict is only mutated by
# synchronous get/setdefault (no await in between), so it is safe to grow
# from concurrent coroutines on the single-threaded event loop.
_jwks_locks: dict[str, asyncio.Lock] = {}
JWKS_CACHE_TTL_S = 3600
JWKS_FETCH_TIMEOUT_S = 3.0


def _jwks_lock_for(url: str) -> asyncio.Lock:
    lock = _jwks_locks.get(url)
    if lock is None:
        lock = _jwks_locks.setdefault(url, asyncio.Lock())
    return lock


async def _get_jwks(url: str) -> dict | None:
    now = time.monotonic()
    entry = _jwks_cache.get(url)
    if entry and (now - entry[0]) < JWKS_CACHE_TTL_S:
        return entry[1]
    async with _jwks_lock_for(url):
        entry = _jwks_cache.get(url)
        if entry and (time.monotonic() - entry[0]) < JWKS_CACHE_TTL_S:
            return entry[1]
        try:
            async with httpx.AsyncClient(timeout=JWKS_FETCH_TIMEOUT_S) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                jwks = resp.json()
        except Exception:
            return None
        _jwks_cache[url] = (time.monotonic(), jwks)
        return jwks


class _JWKSKeyResolver(HTTPSignatureKeyResolver):
    """Resolves a key id to an Ed25519 public key from a fetched JWKS set."""

    def __init__(self, jwks: dict):
        self.keys: dict[str, Ed25519PublicKey] = {}
        for jwk in (jwks or {}).get("keys", []):
            if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
                continue
            kid = jwk.get("kid")
            x_b64 = jwk.get("x") or ""
            if not kid or not x_b64:
                continue
            padded = x_b64 + "=" * (-len(x_b64) % 4)
            try:
                x_bytes = base64.urlsafe_b64decode(padded)
                self.keys[kid] = Ed25519PublicKey.from_public_bytes(x_bytes)
            except Exception:
                continue

    def resolve_public_key(self, key_id: str):
        if key_id not in self.keys:
            raise KeyError(f"key id {key_id!r} not in JWKS")
        return self.keys[key_id]


def _parse_signature_agent(raw: str) -> str | None:
    # Signature-Agent is an sf-string per the Web Bot Auth draft.
    try:
        item = http_sfv.Item()
        item.parse(raw.encode())
        value = item.value
        return value if isinstance(value, str) else None
    except Exception:
        return None


async def _verify_request_signature(request: Request) -> str | None:
    # Returns 'verified' | 'failed' | None (unsigned). Cheap on unsigned.
    headers = request.headers
    if "signature" not in headers or "signature-input" not in headers:
        return None
    agent_raw = headers.get("signature-agent")
    if not agent_raw:
        return "failed"
    agent_url = _parse_signature_agent(agent_raw)
    if not agent_url:
        return "failed"
    jwks = await _get_jwks(agent_url)
    if not jwks:
        return "failed"
    resolver = _JWKSKeyResolver(jwks)
    if not resolver.keys:
        return "failed"
    verifier = HTTPMessageVerifier(
        signature_algorithm=algorithms.ED25519,
        key_resolver=resolver,
    )
    httpx_req = httpx.Request(
        method=request.method,
        url=str(request.url),
        headers=dict(headers),
    )
    try:
        results = verifier.verify(httpx_req)
    except Exception:
        return "failed"

    # Web Bot Auth draft §4: at minimum @authority and signature-agent MUST
    # be covered.  covered_components keys use the sf-string serialisation
    # produced by http_sfv.List, so the required keys are the literals
    # '"@authority"' and '"signature-agent"' (with embedded quotes).
    # We accept the signature as verified only when at least one label
    # satisfies both constraints.
    _REQUIRED_COMPONENTS = {'"@authority"', '"signature-agent"'}
    if not any(
        _REQUIRED_COMPONENTS.issubset(result.covered_components)
        for result in results
    ):
        return "failed"

    return "verified"


# Declared before rate_limit_middleware so rate_limit wraps it from outside —
# a 429 short-circuits BEFORE we spend a possible JWKS fetch on a request the
# server is about to reject anyway.
@app.middleware("http")
async def signature_verification_middleware(request: Request, call_next):
    request.state.signature_status = await _verify_request_signature(request)
    return await call_next(request)


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


# CSP keeps 'unsafe-inline' because the template ships inline script/style;
# stored values are escaped at render time, so this layer blocks external
# script injection as defense-in-depth.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
}


# Declared after rate_limit_middleware so it wraps the chain and the 429
# response from rate-limiting also carries the security headers.
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


# ── robots.txt ──────────────────────────────────────────────────────────────

ROBOTS_TXT = f"""# This site monitors whether crawlers respect robots.txt.
# The paths listed below as Disallow are honeypots.
# Any request to them is logged as a violation, regardless of
# user-agent. The rest of the site is open to all bots so that
# compliance can actually be measured.
# Results are published at https://goodbot-badbot.com

User-agent: *
Content-Signal: ai-input=yes, ai-train=no, search=yes
Disallow: /do-not-crawl/
Disallow: /private/
Disallow: /honeypot/
Disallow: /training-data-forbidden/
Disallow: /no-ai-allowed/
Disallow: /robots-test/

Sitemap: {SITE_BASE_URL}/sitemap.xml
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    if _should_log_meta_visit("/robots.txt", ua):
        await log_visit(
            app.state.db_pool, "/robots.txt", ua, ip, is_honeypot=False,
            signature_status=request.state.signature_status,
        )
    return ROBOTS_TXT


# ── sitemap.xml ─────────────────────────────────────────────────────────────

# lastmod freezes at import time, which equals container start = deploy time.
# That's the right semantic: content only changes when a new image ships.
SITEMAP_LASTMOD = datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _build_sitemap() -> str:
    urls = [
        f"  <url>\n    <loc>{SITE_BASE_URL}/</loc>\n    <lastmod>{SITEMAP_LASTMOD}</lastmod>\n  </url>",
        f"  <url>\n    <loc>{SITE_BASE_URL}/blog</loc>\n    <lastmod>{SITEMAP_LASTMOD}</lastmod>\n  </url>",
    ]
    for post in blog.list_posts():
        lastmod = post.date or SITEMAP_LASTMOD
        urls.append(
            f"  <url>\n    <loc>{SITE_BASE_URL}/blog/{post.slug}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>"
        )
    body = "\n".join(urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


@app.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    if _should_log_meta_visit("/sitemap.xml", ua):
        await log_visit(
            app.state.db_pool, "/sitemap.xml", ua, ip, is_honeypot=False,
            signature_status=request.state.signature_status,
        )
    return Response(content=_build_sitemap(), media_type="application/xml")


# ── Web Bot Auth: JWKS for outbound identity ────────────────────────────────

# Ed25519 public key, published per the IETF WebBotAuth WG draft so receiving
# sites could verify any future signed requests originating from this domain.
# The matching private key was generated offline and discarded; we don't
# emit signed requests today. To start signing later, generate a new keypair
# and replace kid + x — consumers refetch on cache miss.
WEB_BOT_AUTH_JWKS = {
    "keys": [
        {
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": "goodbot-badbot-2026-06-03",
            "x": "wJJd5OF5MmtXEkauhmjaLIgNSkX_CQlBd7g-pPSyJ1s",
            "use": "sig",
            "alg": "EdDSA",
        }
    ]
}


@app.get("/.well-known/http-message-signatures-directory")
async def web_bot_auth_directory():
    return JSONResponse(
        content=WEB_BOT_AUTH_JWKS,
        media_type="application/jwk-set+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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

## Writing

- [Blog](https://goodbot-badbot.com/blog): methodology notes and findings

## Source code

- [GitHub repository](https://github.com/dkd-dobberkau/goodbot-badbot): MIT-licensed, FastAPI + MySQL

## Privacy

Logged IPs are SHA-256 hashed and truncated to 16 hex chars before storage.
The raw IP is never written to disk.
"""


@app.get("/llms.txt")
async def llms_txt(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    if _should_log_meta_visit("/llms.txt", ua):
        await log_visit(
            app.state.db_pool, "/llms.txt", ua, ip, is_honeypot=False,
            signature_status=request.state.signature_status,
        )
    return Response(content=LLMS_TXT, media_type="text/markdown; charset=utf-8")


# ── agents.md (agent-discovery probe surface) ─────────────────────────────────

# This is NOT the AGENTS.md coding-agent standard (that lives in the repo root
# for tools working ON this codebase). It is served purely as a measurement
# surface: some agents probe /AGENTS.md or /.well-known/agents.md at runtime to
# discover how to use a site. We answer honestly — the site exposes no callable
# agent endpoint, so there is nothing to advertise (publishing a fake manifest
# would be the same compliance theatre we reject for DNS-AID) — and log who
# asked, exactly like robots.txt / sitemap.xml / llms.txt. The point is to
# observe agent discovery behaviour, not to participate in it.
AGENTS_MD = """# goodbot-badbot — agents.md

> This site is an *observer* of AI agents and crawlers, not an agent itself.
> It exposes no callable agent, tool, or API endpoint to act on. There is
> nothing here to invoke — only something to read.

## What this is

goodbot-badbot.com measures whether crawlers respect robots.txt. Six honeypot
paths are listed as `Disallow` in /robots.txt. Any request to one of them is
logged as a violation, regardless of user-agent, and published live.

## What an agent can read here

- [Live scoreboard](https://goodbot-badbot.com/)
- [Machine-readable stats](https://goodbot-badbot.com/api/stats)
- [LLM-oriented summary](https://goodbot-badbot.com/llms.txt)
- [Crawl rules](https://goodbot-badbot.com/robots.txt)

Please honour /robots.txt. The `Disallow` list is the entire experiment.

## No agent endpoints

There is no MCP server, A2A endpoint, or JSON-RPC tool to discover here. This
file exists so that agent *discovery behaviour* can itself be observed.

## Transparency

Requests to this file are logged (user-agent plus a SHA-256-truncated IP hash,
the same privacy model as the rest of the site) so we can measure which agents
probe for it.
"""


@app.get("/AGENTS.md")
@app.get("/agents.md")
@app.get("/.well-known/agents.md")
async def agents_md(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    # Log under the exact path requested so the three probe locations are
    # distinguishable in the data — which one an agent reaches for is signal.
    path = request.url.path
    if _should_log_meta_visit(path, ua):
        await log_visit(
            app.state.db_pool, path, ua, ip, is_honeypot=False,
            signature_status=request.state.signature_status,
        )
    return Response(content=AGENTS_MD, media_type="text/markdown; charset=utf-8")


# ── Blog ──────────────────────────────────────────────────────────────────────

@app.get("/blog")
async def blog_index(request: Request):
    if _wants_markdown(request.headers.get("accept", "")):
        return Response(
            content=blog.render_index_markdown(),
            media_type="text/markdown; charset=utf-8",
        )
    return HTMLResponse(content=blog.render_index_html())


@app.get("/blog/{slug}")
async def blog_post(request: Request, slug: str):
    post = blog.get_post(slug)
    if post is None:
        return PlainTextResponse("Not Found", status_code=404)
    if _wants_markdown(request.headers.get("accept", "")):
        return Response(content=post.md, media_type="text/markdown; charset=utf-8")
    return HTMLResponse(content=blog.render_post_html(post))


# ── Grounding pages ────────────────────────────────────────────────────────────

# Grounding pages are factual entity definitions (see app/facts.py). Unlike the
# blog, reads ARE logged — they are a positive discovery signal, exactly like
# agents.md: an agent fetching a citable fact source, the opposite of a honeypot
# violation. Each page is logged under its exact path so individual pages are
# distinguishable in the data.

@app.get("/facts")
async def facts_index(request: Request):
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    if _should_log_meta_visit("/facts", ua):
        await log_visit(
            app.state.db_pool, "/facts", ua, ip, is_honeypot=False,
            signature_status=request.state.signature_status,
        )
    if _wants_markdown(request.headers.get("accept", "")):
        return Response(
            content=facts.render_index_markdown(),
            media_type="text/markdown; charset=utf-8",
        )
    return HTMLResponse(content=facts.render_index_html())


@app.get("/facts/{slug}")
async def facts_page(request: Request, slug: str):
    fact = facts.get_fact(slug)
    if fact is None:
        return PlainTextResponse("Not Found", status_code=404)
    path = request.url.path
    ip = request.client.host
    ua = request.headers.get("user-agent", "")
    if _should_log_meta_visit(path, ua):
        await log_visit(
            app.state.db_pool, path, ua, ip, is_honeypot=False,
            signature_status=request.state.signature_status,
        )
    if _wants_markdown(request.headers.get("accept", "")):
        return Response(content=fact.md, media_type="text/markdown; charset=utf-8")
    return HTMLResponse(content=facts.render_fact_html(fact))


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
    await log_visit(
        app.state.db_pool, str(request.url.path), ua, ip, is_honeypot=True,
        signature_status=request.state.signature_status,
    )
    return PlainTextResponse("", status_code=200)


# ── API: results ─────────────────────────────────────────────────────────────

# Single-flight TTL cache: under HN-spike concurrency, the first request
# computes and any others arriving within the TTL share the result instead
# of fanning out N copies of the same four-query bundle to MySQL. TTL is
# shorter than the dashboard's 30s poll cadence, so a single client never
# sees an artefact of the cache; the win is purely at concurrency.
STATS_TTL_S = 5
_stats_cache: dict = {"ts": 0.0, "data": None}
_stats_lock = asyncio.Lock()


async def _compute_stats() -> dict:
    async with app.state.db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT bot_name, operator,
                       COUNT(*) AS total_visits,
                       CAST(SUM(is_honeypot) AS UNSIGNED) AS violations,
                       CAST(SUM(signature_status = 'verified') AS UNSIGNED) AS verified_visits,
                       CAST(SUM(signature_status = 'failed') AS UNSIGNED) AS failed_sigs,
                       MAX(ts) AS last_seen
                FROM visits
                WHERE bot_name IS NOT NULL
                GROUP BY bot_name, operator
                ORDER BY violations DESC, total_visits DESC
            """)
            summary = await cur.fetchall()

            await cur.execute("""
                SELECT ts, path, bot_name, operator, user_agent, signature_status
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

            await cur.execute("SELECT COUNT(*) AS c FROM visits WHERE signature_status = 'verified'")
            total_verified = (await cur.fetchone())["c"]

            # Discovery reads: per known bot, how many times it fetched the
            # LLM/agent discovery files. llms.txt and the three agents.md probe
            # locations are reported as two columns. Placeholders are built from
            # the path tuples so the value list stays parameterised.
            agents_ph = ",".join(["%s"] * len(AGENTS_MD_PATHS))
            discovery_ph = ",".join(["%s"] * len(DISCOVERY_PATHS))
            await cur.execute(
                f"""
                SELECT bot_name, operator,
                       CAST(SUM(path = '/llms.txt') AS UNSIGNED) AS llms_reads,
                       CAST(SUM(path IN ({agents_ph})) AS UNSIGNED) AS agents_reads,
                       COUNT(*) AS total_reads,
                       MAX(ts) AS last_seen
                FROM visits
                WHERE path IN ({discovery_ph})
                  AND bot_name IS NOT NULL
                GROUP BY bot_name, operator
                ORDER BY total_reads DESC, last_seen DESC
                LIMIT 50
                """,
                (*AGENTS_MD_PATHS, *DISCOVERY_PATHS),
            )
            discovery = await cur.fetchall()

            await cur.execute(
                f"SELECT COUNT(*) AS c FROM visits WHERE path IN ({discovery_ph})",
                DISCOVERY_PATHS,
            )
            total_discovery = (await cur.fetchone())["c"]

    return {
        "summary": summary,
        "recent_violations": recent,
        "total_violations": total_violations,
        "total_bots_seen": total_bots,
        "total_verified": total_verified,
        "discovery_reads": discovery,
        "total_discovery_reads": total_discovery,
    }


async def _get_stats_cached() -> dict:
    now = time.monotonic()
    if _stats_cache["data"] is not None and (now - _stats_cache["ts"]) < STATS_TTL_S:
        return _stats_cache["data"]
    async with _stats_lock:
        now = time.monotonic()
        if _stats_cache["data"] is not None and (now - _stats_cache["ts"]) < STATS_TTL_S:
            return _stats_cache["data"]
        data = await _compute_stats()
        _stats_cache["ts"] = time.monotonic()
        _stats_cache["data"] = data
        return data


@app.get("/api/stats")
async def stats(response: Response):
    response.headers["Cache-Control"] = f"public, max-age={STATS_TTL_S}"
    return await _get_stats_cached()


# Build-time SHA baked into the image via the Dockerfile ARG. deploy.sh
# polls this after a stack-deploy to confirm the new code is actually
# serving requests — Mittwald's reported deployedState.image is unreliable
# (it can report the new tag while the container still runs old code).
BUILD_VERSION = os.getenv("BUILD_VERSION", "unknown")


@app.get("/api/version")
async def version(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"version": BUILD_VERSION}


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

# RFC 8288 Link headers for agent discovery. Comma-separated single header is
# equivalent to multiple Link headers per the RFC and simpler to inspect.
HOMEPAGE_LINK_HEADER = ", ".join((
    '</api/stats>; rel="service-desc"; type="application/json"',
    '</llms.txt>; rel="service-doc"; type="text/markdown"',
    '</sitemap.xml>; rel="sitemap"',
))


def _wants_markdown(accept_header: str) -> bool:
    # Substring match is enough — anything that names text/markdown in Accept
    # is opting in; browsers send */* or text/html and get HTML by default.
    return "text/markdown" in accept_header.lower()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    base_headers = {
        "Link": HOMEPAGE_LINK_HEADER,
        "Vary": "Accept",
    }
    if _wants_markdown(request.headers.get("accept", "")):
        # ~4 chars/token is the standard rough estimate for English prose.
        tokens = max(1, len(LLMS_TXT) // 4)
        return Response(
            content=LLMS_TXT,
            media_type="text/markdown; charset=utf-8",
            headers={**base_headers, "X-Markdown-Tokens": str(tokens)},
        )
    with open("templates/index.html") as f:
        html = f.read()
    return HTMLResponse(content=html, headers=base_headers)
