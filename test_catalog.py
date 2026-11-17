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
from datetime import date
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

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
