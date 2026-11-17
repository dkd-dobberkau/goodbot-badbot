"""Tests for the bot catalog (app/catalog.py).

The catalog lists every claim about a bot with its source, next to what the
bot did here. These tests pin the rules the page depends on: stored claims
must be dated and sourced, Cloudflare's followsRobotsTxt is never used, and
a URL taken from a User-Agent is never trusted.

Run with: python test_catalog.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

from app import catalog

TODAY = date(2026, 11, 20)
CF_SLUGS = {"gptbot", "ahrefsbot"}
CF_BOTS = json.loads(Path("app/cf_bots.json").read_text(encoding="utf-8"))


def _valid_raw() -> dict:
    return {
        "gptbot": {
            "name": "GPTBot",
            "match": ["GPTBot"],
            "cloudflare_slug": "gptbot",
            "docs_recorded": True,
            "claims": {
                "robots_txt": [
                    {"value": "obeys", "source": "operator-docs",
                     "url": "https://platform.openai.com/docs/bots", "retrieved": "2026-11-20"},
                    {"value": "no-statement", "source": "cloudflare",
                     "url": "https://radar.cloudflare.com/bots/gptbot", "retrieved": "2026-11-19"},
                ],
            },
        },
        "ahrefsbot": {
            "name": "AhrefsBot",
            "match": ["AhrefsBot"],
            "cloudflare_slug": None,
            "docs_recorded": False,
            "claims": {},
        },
    }


def _with_claim(**override) -> dict:
    raw = _valid_raw()
    claim = raw["gptbot"]["claims"]["robots_txt"][0]
    for key, value in override.items():
        if value is None:
            claim.pop(key, None)
        else:
            claim[key] = value
    return raw


def main() -> int:
    failures = 0
    total = 0

    def check(label, got, want):
        nonlocal failures, total
        total += 1
        ok = got == want
        print(("PASS " if ok else "FAIL ") + f"{label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    def has_error(label, raw, cf_slugs=CF_SLUGS):
        check(label, bool(catalog.validate_claims(raw, cf_slugs, TODAY)), True)

    # ── validate_claims ─────────────────────────────────────────────────────
    check("valid claims file has no errors", catalog.validate_claims(_valid_raw(), CF_SLUGS, TODAY), [])
    has_error("source other than operator-docs/cloudflare", _with_claim(source="user-agent"))
    has_error("missing url", _with_claim(url=None))
    has_error("url not https", _with_claim(url="http://platform.openai.com/docs/bots"))
    has_error("missing retrieved", _with_claim(retrieved=None))
    has_error("retrieved not ISO", _with_claim(retrieved="20.11.2026"))
    has_error("retrieved in the future", _with_claim(retrieved="2026-11-21"))
    has_error("robots_txt value outside the allowed set", _with_claim(value="sometimes"))

    raw = _valid_raw()
    raw["gptbot"]["claims"]["favourite_colour"] = []
    has_error("unknown question key", raw)

    raw = _valid_raw()
    raw["ahrefsbot"]["match"] = ["GPTBot"]
    has_error("same name in two entries", raw)

    raw = _valid_raw()
    raw["ahrefsbot"]["cloudflare_slug"] = "no-such-slug"
    has_error("cloudflare_slug not in cf_bots.json", raw)

    # The real file is guarded from now on: every edit must keep it valid.
    real = json.loads(Path("app/bot_claims.json").read_text(encoding="utf-8"))
    check("app/bot_claims.json is valid",
          catalog.validate_claims(real, {b["slug"] for b in CF_BOTS}, date.today()), [])

    # ── load_claims ─────────────────────────────────────────────────────────
    loaded = catalog.load_claims(Path("app/bot_claims.json"), {b["slug"] for b in CF_BOTS})
    check("load_claims keys entries by match name", "GPTBot" in loaded, True)
    check("load_claims returns BotClaims", isinstance(loaded["GPTBot"], catalog.BotClaims), True)

    # ── ua_info_url ─────────────────────────────────────────────────────────
    check("ua_info_url GPTBot",
          catalog.ua_info_url("Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"),
          "https://openai.com/gptbot")
    check("ua_info_url none", catalog.ua_info_url("curl/8.7.1"), None)
    check("ua_info_url stops at ) and <",
          catalog.ua_info_url("Evil/1.0 (+https://x.test/a)<script>alert(1)</script>"),
          "https://x.test/a")
    check("ua_info_url stops at ;",
          catalog.ua_info_url("Bot/1.0 (+https://x.test/b; more)"), "https://x.test/b")

    # ── derived_claims ──────────────────────────────────────────────────────
    cf_entry = {
        "slug": "gptbot", "name": "GPTBot", "operator": "OpenAI",
        "operatorUrl": "https://platform.openai.com/docs/gptbot",
        "category": "AI_CRAWLER", "followsRobotsTxt": True,
        "signatureAgentUrl": "https://chatgpt.com/.well-known/http-message-signatures-directory",
    }
    derived = catalog.derived_claims(
        "GPTBot", cf_entry, "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)")
    as_tuples = {(c.question, c.source, c.url) for c in derived}
    check("cloudflare operator claim",
          ("operator", "cloudflare", "https://platform.openai.com/docs/gptbot") in as_tuples, True)
    check("user-agent docs claim",
          ("docs_opt_out", "user-agent", "https://openai.com/gptbot") in as_tuples, True)
    check("cloudflare key directory claim",
          catalog.Claim("signing", "publishes a key directory", "cloudflare",
                        "https://chatgpt.com/.well-known/http-message-signatures-directory", None)
          in derived, True)
    check("followsRobotsTxt never becomes a claim",
          [c for c in derived if c.question == "robots_txt"], [])
    check("no cloudflare entry, no UA url → no claims",
          catalog.derived_claims("X", None, "curl/8.7.1"), [])

    # ── combine_measurements ────────────────────────────────────────────────
    t = lambda h, m=0: datetime(2026, 11, 10, h, m)  # noqa: E731

    def agg(ua, visits, honeypot=0, discovery=0, verified=0, failed=0, before=0,
            first_hit=None, first_robots=None, **named):
        row = {"user_agent": ua, "visits": visits, "honeypot": honeypot, "discovery": discovery,
               "verified_since": verified, "failed_since": failed, "signed_before": before,
               "first_honeypot_ts": first_hit, "first_robots_ts": first_robots}
        row.update(named)
        return row

    gpt_a = "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"
    gpt_b = "Mozilla/5.0 (compatible; GPTBot/1.1)"
    named_rows = [
        agg(gpt_a, 10, honeypot=2, first_hit=t(9), first_robots=t(8), bot_name="GPTBot", operator="OpenAI"),
        agg(gpt_b, 3, first_robots=t(12), bot_name="GPTBot", operator="OpenAI"),
        agg("ClaudeBot/1.0", 4, honeypot=2, first_hit=t(7), bot_name="ClaudeBot", operator="Anthropic"),
        agg("PetalBot", 2, honeypot=1, first_hit=t(6), first_robots=t(11), bot_name="PetalBot", operator="Huawei"),
        agg("YouBot/1.0", 1, before=2, bot_name="YouBot", operator="You.com"),
    ]
    # One address claims ClaudeBot and GPTBot within 60 s: both visits are spoofed.
    named_visits = [
        {"id": 1, "ts": t(7), "ip_hash": "aa", "bot_name": "ClaudeBot", "operator": "Anthropic",
         "path": "/private/.env", "is_honeypot": 1},
        {"id": 2, "ts": t(7), "ip_hash": "aa", "bot_name": "GPTBot", "operator": "OpenAI",
         "path": "/", "is_honeypot": 0},
        {"id": 3, "ts": t(9), "ip_hash": "bb", "bot_name": "ClaudeBot", "operator": "Anthropic",
         "path": "/private/.env", "is_honeypot": 1},
    ]
    crawler_rows = [
        agg("Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", 30, failed=3),
        agg("Mozilla/5.0 (compatible; AhrefsBot/7.1; +http://ahrefs.com/robot/)", 5, honeypot=1,
            first_hit=t(5)),
        agg("curl/8.7.1", 9, honeypot=4),
    ]
    measured = catalog.combine_measurements(named_rows, named_visits, crawler_rows)

    check("two GPTBot UAs sum", measured["GPTBot"].visits, 13)
    check("top UA is the busier one", measured["GPTBot"].top_user_agent, gpt_a)
    check("spoofed honeypot hit is not charged to ClaudeBot", measured["ClaudeBot"].honeypot_hits, 1)
    check("ClaudeBot name used in one spoofed visit", measured["ClaudeBot"].spoofed_by_others, 1)
    check("AI bots are spoof-filtered", measured["ClaudeBot"].spoof_filtered, True)
    check("AhrefsBot UAs merge", measured["AhrefsBot"].visits, 35)
    check("crawlers are not spoof-filtered", measured["AhrefsBot"].spoof_filtered, False)
    check("crawler class", measured["AhrefsBot"].bot_class, "crawler")
    check("crawler operator", measured["AhrefsBot"].operator, "Ahrefs")
    check("HTTP clients are not catalogued", "curl" in measured, False)
    check("robots.txt read before the first hit", measured["GPTBot"].robots_read_before_first_hit, True)
    check("robots.txt read only after the first hit", measured["PetalBot"].robots_read_before_first_hit, False)
    check("hit without any robots.txt read", measured["AhrefsBot"].robots_read_before_first_hit, False)
    check("no hits at all → None", catalog.combine_measurements(
        [agg("X", 1, bot_name="GPTBot", operator="OpenAI")], [], [])["GPTBot"].robots_read_before_first_hit, None)
    check("signed before the fix only", (measured["YouBot"].signed_before_fix,
          measured["YouBot"].signed_verified, measured["YouBot"].signed_failed), (2, 0, 0))
    check("crawler failed signatures sum", measured["AhrefsBot"].signed_failed, 3)
    check("empty inputs", catalog.combine_measurements([], [], []), {})

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
