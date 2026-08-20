"""Stdlib-only smoke test for the UA classifier and the discovery aggregator.

Run with: python test_ua_classification.py
Exit 0 if all assertions pass, 1 otherwise.

Every user agent below was observed in production; the counts in the
aggregation cases mirror the real distribution that motivated the split.
"""
import sys

from app.bots import (
    CLASS_AI,
    CLASS_BROWSER_UA,
    CLASS_CRAWLER,
    CLASS_HTTP_CLIENT,
    CLASS_SELF,
    CLASS_UNKNOWN,
    classify_ua,
    is_self_tooling,
)
from app.main import (
    MAX_DISPLAYED_UA_LEN,
    TRAP_OVERLAP_ROW_LIMIT,
    _aggregate_discovery_rows,
    _aggregate_trap_rows,
)

CLASSIFY_CASES = [
    # (user_agent, expected class, label)
    # --- our own verification tooling ---
    ("goodbot-badbot-deploy-check/1.0", CLASS_SELF, "deploy check"),
    ("probe-split-check/1.0", CLASS_SELF, "probe split check"),
    # --- AI crawlers still win over everything else ---
    ("Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)", CLASS_AI, "GPTBot"),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", CLASS_AI, "ClaudeBot"),
    # DeepSeek was sitting in the unidentified bucket before this registry entry
    ("Mozilla/5.0 (compatible; DeepSeekBot/1.0; +https://www.deepseek.com/bot)", CLASS_AI, "DeepSeekBot"),
    # --- non-AI crawlers ---
    ("Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)", CLASS_CRAWLER, "SemrushBot"),
    ("Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", CLASS_CRAWLER, "AhrefsBot"),
    ("Mozilla/5.0 (compatible; SeznamBot/4.0; +https://o-seznam.cz/)", CLASS_CRAWLER, "SeznamBot"),
    ("Mozilla/5.0 (compatible; Dataprovider.com)", CLASS_CRAWLER, "Dataprovider"),
    # Crawlers that wrap themselves in a full browser string MUST NOT be read
    # as browsers — this is the ordering invariant of classify_ua().
    ("Mozilla/5.0 (Linux) Chrome/112.0.0.0 (compatible; mOptimizer/1.0)",
     CLASS_CRAWLER, "mOptimizer behind a Chrome string"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko; compatible; BuiltWith/1.4; rb.gy/xprgqj) Chrome/124.0.0.0 Safari/537.36",
     CLASS_CRAWLER, "BuiltWith behind a Chrome string"),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0.1938.76 Safari/537.36",
     CLASS_CRAWLER, "bingbot behind a Chrome string"),
    ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 mOptimizer/1.0/250303.095116",
     CLASS_CRAWLER, "mOptimizer suffix variant"),
    # --- generic HTTP clients ---
    ("curl/8.7.1", CLASS_HTTP_CLIENT, "curl"),
    ("Go-http-client/2.0", CLASS_HTTP_CLIENT, "Go-http-client"),
    ("Python/3.14 aiohttp/3.14.1", CLASS_HTTP_CLIENT, "aiohttp"),
    ("python-httpx2/2.9.1", CLASS_HTTP_CLIENT, "httpx"),
    # --- browser-shaped strings ---
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) Gecko/20100101 Firefox/152.0",
     CLASS_BROWSER_UA, "Firefox"),
    ("Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
     CLASS_BROWSER_UA, "Pixel 6 (claims browser; is a proxy-rotating scraper)"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
     CLASS_BROWSER_UA, "Safari"),
    # --- nothing to go on ---
    ("", CLASS_UNKNOWN, "empty UA"),
    ("Illico/0.1 (knowledge-base-builder; +https://github.com/illico)", CLASS_UNKNOWN, "unregistered named bot"),
]


def _row(user_agent, *, llms=0, facts=0, mcp=0, probes=0, last_seen="2026-08-20"):
    reads = llms + facts + mcp
    return {
        "user_agent": user_agent,
        "llms_reads": llms, "agents_reads": 0, "facts_reads": facts,
        "catalog_reads": 0, "ard_reads": 0, "mcp_calls": mcp,
        "total_reads": reads, "head_probes": probes, "last_seen": last_seen,
    }


def check(label, got, want, failures):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
    return failures + (0 if ok else 1)


def main() -> int:
    failures = 0

    for ua, want_class, label in CLASSIFY_CASES:
        got_class, _, _ = classify_ua(ua)
        failures = check(f"classify {label}", got_class, want_class, failures)

    failures = check("is_self_tooling(deploy check)",
                     is_self_tooling("goodbot-badbot-deploy-check/1.0"), True, failures)
    failures = check("is_self_tooling(bare curl)",
                     is_self_tooling("curl/8.7.1"), False, failures)

    # --- aggregation ---
    rows = [
        _row("goodbot-badbot-deploy-check/1.0", llms=10, mcp=3),
        _row("Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)", facts=9),
        _row("Mozilla/5.0 (compatible; SemrushBot/7~bl)", facts=12),
        _row("Mozilla/5.0 (compatible; AhrefsBot/7.0)", facts=10),
        _row("curl/8.7.1", llms=3, facts=3),
        _row("curl/8.5.0", llms=1),
        _row("Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36", facts=25, probes=1),
        _row("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) Gecko/20100101 Firefox/152.0", facts=5),
        _row("Illico/0.1 (knowledge-base-builder)", facts=3),
    ]
    out = _aggregate_discovery_rows(rows)
    by_name = {row["bot_name"]: row for row in out}

    failures = check("self-test rows dropped",
                     any(r["bot_class"] == CLASS_SELF for r in out), False, failures)
    failures = check("AI class ranks first", out[0]["bot_class"], CLASS_AI, failures)
    failures = check("GPTBot facts", by_name["GPTBot"]["facts_reads"], 9, failures)
    failures = check("SemrushBot classed as crawler",
                     by_name["SemrushBot"]["bot_class"], CLASS_CRAWLER, failures)
    # Two curl builds must fold into one named HTTP-client row.
    failures = check("curl builds merged", by_name["curl"]["ua_count"], 2, failures)
    failures = check("curl reads summed", by_name["curl"]["total_reads"], 7, failures)
    # Browser-shaped UAs collapse into a single row carrying its own probes.
    failures = check("browser UAs collapsed", by_name["Browser UA"]["ua_count"], 2, failures)
    failures = check("browser UA reads summed", by_name["Browser UA"]["facts_reads"], 30, failures)
    failures = check("browser UA probes kept", by_name["Browser UA"]["head_probes"], 1, failures)
    failures = check("unidentified survives as its own row",
                     by_name["Unidentified"]["facts_reads"], 3, failures)
    # The self-test row contributed 13 reads; none of them may show up.
    failures = check("no self-test reads leak into totals",
                     sum(r["total_reads"] for r in out), 9 + 12 + 10 + 7 + 30 + 3, failures)

    # --- invitation vs trap overlap ---
    PIXEL = ("Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36")
    IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) "
              "AppleWebKit/605.1.15 Version/13.0.3 Mobile/15E148 Safari/604.1")

    def trap_row(ua, grounding, honeypots, ips):
        return {"user_agent": ua, "grounding_reads": grounding,
                "honeypot_hits": honeypots, "distinct_ips": ips}

    trap_rows = [
        # Two mOptimizer strings: one tool, must merge into a single caller.
        trap_row("Mozilla/5.0 (Linux) Chrome/112.0.0.0 (compatible; mOptimizer/1.0)", 56, 192, 20),
        trap_row("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/148.0.0.0 Safari/537.36 mOptimizer/1.0/250303.095116", 11, 32, 9),
        # Two distinct browser strings: must NOT merge — the string is the identity.
        trap_row(PIXEL, 25, 123, 25),
        trap_row(IPHONE, 24, 47, 23),
        # Clean readers: read the invitation, never touched a trap.
        trap_row("Mozilla/5.0 (compatible; SeznamBot/4.0; +https://o-seznam.cz/)", 21, 0, 13),
        trap_row("Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)", 9, 0, 4),
        # Self-test must not appear at all.
        trap_row("goodbot-badbot-deploy-check/1.0", 40, 5, 1),
    ]
    trap_display, trap_totals = _aggregate_trap_rows(trap_rows)
    by_caller = {r["caller"]: r for r in trap_display}

    failures = check("mOptimizer strings merged into one caller",
                     by_caller["mOptimizer"]["grounding_reads"], 67, failures)
    failures = check("merged caller sums honeypot hits",
                     by_caller["mOptimizer"]["honeypot_hits"], 224, failures)
    failures = check("browser strings stay separate",
                     sum(1 for r in trap_display if r["bot_class"] == CLASS_BROWSER_UA),
                     2, failures)
    failures = check("self-test excluded from trap table",
                     any("deploy-check" in r["user_agent"] for r in trap_display), False, failures)
    failures = check("clean reader kept with zero hits",
                     by_caller["SeznamBot"]["honeypot_hits"], 0, failures)
    failures = check("ranked by grounding reads",
                     trap_display[0]["caller"], "mOptimizer", failures)
    # Totals must ignore the self-test row: 67+25+24+21+9 = 146 reads,
    # of which 67+25+24 = 116 come from callers that also tripped a trap.
    failures = check("total grounding reads", trap_totals["grounding_reads"], 146, failures)
    failures = check("reads from violators", trap_totals["reads_from_violators"], 116, failures)
    failures = check("violator share", trap_totals["violator_share"], 79.5, failures)
    failures = check("violator caller count", trap_totals["violator_callers"], 3, failures)
    failures = check("caller count", trap_totals["callers"], 5, failures)
    # Long anonymous strings are truncated for display; named callers are not.
    failures = check("long UA truncated",
                     len(by_caller[[c for c in by_caller if c.endswith("…")][0]]["caller"]),
                     MAX_DISPLAYED_UA_LEN, failures)
    failures = check("truncated row keeps full UA for the title attribute",
                     any(r["user_agent"] == PIXEL for r in trap_display), True, failures)

    # Row limit must bound the table without touching the totals.
    many = [trap_row(f"Bot{i}Crawler/1.0", 1, 1, 1) for i in range(TRAP_OVERLAP_ROW_LIMIT + 10)]
    limited, limited_totals = _aggregate_trap_rows(many)
    failures = check("display bounded by row limit", len(limited), TRAP_OVERLAP_ROW_LIMIT, failures)
    failures = check("totals count every caller, not just displayed ones",
                     limited_totals["callers"], TRAP_OVERLAP_ROW_LIMIT + 10, failures)

    total = len(CLASSIFY_CASES) + 27
    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
