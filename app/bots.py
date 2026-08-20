"""
User-agent taxonomy for goodbot-badbot.

Everything that turns a raw User-Agent string into an identity lives here:
the curated AI-crawler registry, the Cloudflare Radar additions, the non-AI
crawler registry, and the classifier that assigns every request to exactly one
class for the Discovery Reads dashboard.

Why a classifier at all: the dashboard used to lump every unmatched UA into a
single "Unidentified" row, which grew to 92 % of all discovery reads and made
the panel unreadable — SEO crawlers, scrapers wearing browser UAs, and this
site's own verification curls all landed in the same bucket. Splitting them is
purely a presentation concern derived from the UA string, so it happens at
query time rather than in a stored column: changing a registry entry here
immediately reclassifies the whole history, with no migration and no backfill.
"""

import json
from pathlib import Path

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
    # DeepSeek — absent from both the CF Radar dataset and every public list we
    # vendor, but observed here fetching /openapi.json. Without this entry it
    # falls through to the unidentified bucket, which is exactly the kind of
    # misclassification the Discovery Reads split exists to remove.
    "deepseekbot":                     ("DeepSeekBot",         "DeepSeek"),
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


# Self-tooling: verification requests this project makes against its own
# production site (deploy smoke checks, one-off probes). They are our own
# traffic, not a visitor, so they are dropped at log time and — for the rows
# already in the table from before this existed — hidden from the dashboard by
# the classifier.
#
# Convention: any curl/script that probes goodbot-badbot.com as part of
# developing or deploying it MUST send one of these markers in its UA, and new
# markers belong in this tuple. Generic clients (curl/8.7.1, python-httpx) are
# deliberately NOT listed: we cannot tell our own bare curl apart from a
# stranger's, and silently claiming ambiguous traffic as our own would hide
# real signal. Those stay visible under the "HTTP client" class instead.
SELF_TOOLING_UA_MARKERS = (
    "goodbot-badbot-deploy-check",
    "probe-split-check",
)

# Non-AI crawlers: SEO/backlink indexers, classic search engines, market
# intelligence, and internet-wide scanners. These are legitimate, self-declared
# crawlers — they simply are not the AI agents this site measures, and mixing
# them into the AI numbers is what made the dashboard misleading.
#
# Matched only after KNOWN_BOTS, so an AI crawler always wins a substring tie.
NON_AI_CRAWLERS = {
    # SEO / backlink industry
    "semrushbot":                ("SemrushBot",              "Semrush"),
    "ahrefsbot":                 ("AhrefsBot",               "Ahrefs"),
    "mj12bot":                   ("MJ12bot",                 "Majestic"),
    "dotbot":                    ("DotBot",                  "Moz"),
    "serankingbacklinksbot":     ("SERankingBacklinksBot",   "SE Ranking"),
    "seranking":                 ("SERanking",               "SE Ranking"),
    "moptimizer":                ("mOptimizer",              "unknown"),
    "screaming frog":            ("Screaming Frog",          "Screaming Frog"),
    # Classic search engines
    "googlebot":                 ("Googlebot",               "Google"),
    "bingbot":                   ("bingbot",                 "Microsoft"),
    "baiduspider":               ("Baiduspider",             "Baidu"),
    "yandexbot":                 ("YandexBot",               "Yandex"),
    "seznambot":                 ("SeznamBot",               "Seznam"),
    "duckduckbot":               ("DuckDuckBot",             "DuckDuckGo"),
    "petalbot":                  ("PetalBot",                "Huawei"),
    "sogou":                     ("Sogou Spider",            "Sogou"),
    # Market intelligence / tech profiling
    "builtwith":                 ("BuiltWith",               "BuiltWith"),
    "dataprovider":              ("Dataprovider",            "Dataprovider.com"),
    # Archiving / scanning frameworks. Operator is the framework, not the
    # party running it — heritrix in particular is run by many operators.
    "heritrix":                  ("Heritrix",                "various"),
    "censysinspect":             ("CensysInspect",           "Censys"),
    "internetmeasurement":       ("InternetMeasurement",     "Driftnet"),
}

# Generic HTTP client libraries. A scripted client is the most interesting
# residual bucket on this site: an LLM agent driving httpx looks exactly like
# this, and so does a shell script. We name the library and claim nothing more.
HTTP_CLIENT_AGENTS = {
    "go-http-client":  "Go-http-client",
    "python-requests": "python-requests",
    "python-urllib":   "python-urllib",
    "python-httpx":    "httpx",
    "httpx":           "httpx",
    "aiohttp":         "aiohttp",
    "okhttp":          "OkHttp",
    "guzzlehttp":      "Guzzle",
    "node-fetch":      "node-fetch",
    "axios":           "axios",
    "libwww-perl":     "libwww-perl",
    "scrapy":          "Scrapy",
    "postmanruntime":  "Postman",
    "curl":            "curl",
    "wget":            "Wget",
    "java/":           "Java",
}

# Tokens that mean "this UA claims to be a browser". Checked only after both
# crawler registries, because crawlers routinely wrap themselves in a full
# Mozilla/Chrome string — mOptimizer and bingbot both do.
_BROWSER_TOKENS = (
    "firefox/", "samsungbrowser/", "edg/", "opr/", "chrome/",
    "safari/", "msie ", "trident/",
)

# Classes, in dashboard display order.
CLASS_AI = "ai"
CLASS_CRAWLER = "crawler"
CLASS_HTTP_CLIENT = "http_client"
CLASS_BROWSER_UA = "browser_ua"
CLASS_UNKNOWN = "unknown"
CLASS_SELF = "self"

# Labels are deliberately worded as *claims*, not verdicts. "Browser UA" says
# the string looks like a browser; it does not say a human was driving. On this
# site that distinction is load-bearing: the three heaviest "browser UA"
# grounding readers each rotate through 20+ IPs at roughly one request per IP
# and also walk into the honeypots.
CLASS_LABELS = {
    CLASS_AI:          "AI crawler",
    CLASS_CRAWLER:     "Non-AI crawler",
    CLASS_HTTP_CLIENT: "HTTP client",
    CLASS_BROWSER_UA:  "Browser UA",
    CLASS_UNKNOWN:     "Unidentified",
    CLASS_SELF:        "Self-test",
}

CLASS_ORDER = (
    CLASS_AI,
    CLASS_CRAWLER,
    CLASS_HTTP_CLIENT,
    CLASS_BROWSER_UA,
    CLASS_UNKNOWN,
)


def identify_bot(user_agent: str) -> tuple[str | None, str | None, str | None]:
    """Match a UA against the AI-crawler registry. (key, name, operator)."""
    if not user_agent:
        return None, None, None
    ua_lower = user_agent.lower()
    for key, (name, operator) in KNOWN_BOTS.items():
        if key in ua_lower:
            return key, name, operator
    return None, None, None


def is_self_tooling(user_agent: str) -> bool:
    """True for this project's own verification requests against production."""
    if not user_agent:
        return False
    ua_lower = user_agent.lower()
    return any(marker in ua_lower for marker in SELF_TOOLING_UA_MARKERS)


def classify_ua(user_agent: str) -> tuple[str, str, str]:
    """Assign a UA to exactly one class. Returns (class, display name, operator).

    Precedence is deliberate: self-tooling first (it is ours regardless of what
    it claims), then AI crawlers, then non-AI crawlers, then generic clients,
    then anything merely *shaped* like a browser. Crawlers must outrank the
    browser check because so many of them ship a full Mozilla/Chrome string.
    """
    ua = (user_agent or "").strip()
    if not ua:
        return CLASS_UNKNOWN, "No user agent", "—"

    if is_self_tooling(ua):
        return CLASS_SELF, "Self-test", "goodbot-badbot"

    _, name, operator = identify_bot(ua)
    if name is not None:
        return CLASS_AI, name, operator or "—"

    ua_lower = ua.lower()
    for key, (crawler_name, crawler_operator) in NON_AI_CRAWLERS.items():
        if key in ua_lower:
            return CLASS_CRAWLER, crawler_name, crawler_operator

    for key, client_name in HTTP_CLIENT_AGENTS.items():
        if key in ua_lower:
            return CLASS_HTTP_CLIENT, client_name, "—"

    if any(token in ua_lower for token in _BROWSER_TOKENS):
        return CLASS_BROWSER_UA, "Browser UA", "—"

    return CLASS_UNKNOWN, "Unidentified", "—"
