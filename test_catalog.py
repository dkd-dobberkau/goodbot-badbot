"""Tests for the bot catalog (app/catalog.py).

The catalog lists every claim about a bot with its source, next to what the
bot did here. These tests pin the rules the page depends on: stored claims
must be dated and sourced, Cloudflare's followsRobotsTxt is never used, and
a URL taken from a User-Agent is never trusted.

Run with: python test_catalog.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import asyncio
import json
import sys
from datetime import date, datetime, timezone
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
        agg("ClaudeBot/1.0", 4, honeypot=1, first_hit=t(9), bot_name="ClaudeBot", operator="Anthropic"),
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
    check("named rows are taken as already spoof-filtered", measured["ClaudeBot"].honeypot_hits, 1)
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

    # ── fetch_measurements (SQL shape, against a recording cursor) ─────────
    class RecordingCursor:
        def __init__(self, results):
            self.results, self.queries = list(results), []

        async def execute(self, sql, params=None):
            self.queries.append((sql, tuple(params or ())))

        async def fetchall(self):
            return self.results.pop(0)

    cur = RecordingCursor([named_visits, named_rows, crawler_rows])
    asyncio.run(catalog.fetch_measurements(cur, ("/llms.txt",), ("/facts/",)))
    check("verified counts at any time; only failures before the fix are set aside",
          ("signature_status = 'verified' AND ts >=" not in cur.queries[1][0]
           and "signature_status = 'failed' AND ts < %s" in cur.queries[1][0]), True)
    check("every query has as many %s as parameters",
          [sql.count("%s") == len(params) for sql, params in cur.queries], [True, True, True])
    named_sql, named_params = cur.queries[1]
    check("spoofed visits are excluded from every AI measurement",
          "id NOT IN" in named_sql and {1, 2} <= set(named_params), True)
    crawler_sql, crawler_params = cur.queries[2]
    check("crawler query is narrowed to named crawler patterns",
          "%ahrefsbot%" in crawler_params and "%barkrowler%" in crawler_params, True)
    check("no LIKE wildcard leaks from a pattern",
          all(p.count("%") == 2 for p in crawler_params if isinstance(p, str) and p.startswith("%")), True)
    check("claims are dated against UTC", catalog._utc_today(), datetime.now(timezone.utc).date())

    # ── build_catalog ───────────────────────────────────────────────────────
    def m(name, bot_class="ai", visits=5, hits=0, **kw):
        return catalog.Measurements(name, bot_class, kw.pop("operator", "Op"), visits=visits,
                                    honeypot_hits=hits, spoof_filtered=bot_class == "ai",
                                    top_user_agent=kw.pop("ua", None), **kw)

    obeys = lambda source: catalog.Claim("robots_txt", "obeys", source,  # noqa: E731
                                         "https://example.test/docs", "2026-11-20")
    claims = {
        "GPTBot": catalog.BotClaims("gptbot", "GPTBot", ("GPTBot",), "gptbot", True,
                                    (obeys("operator-docs"), obeys("cloudflare"))),
        "ClaudeBot": catalog.BotClaims("claudebot", "ClaudeBot", ("ClaudeBot",), None, True,
                                       (obeys("operator-docs"),)),
        "AhrefsBot": catalog.BotClaims("ahrefsbot", "AhrefsBot", ("AhrefsBot",), None, True,
                                       (obeys("operator-docs"),)),
        "NeverSeen": catalog.BotClaims("neverseen", "NeverSeen", ("NeverSeen",), None, True, ()),
    }
    cf_by_slug = {"gptbot": cf_entry}
    measurements = {
        "GPTBot": m("GPTBot", visits=124, hits=3, ua=gpt_a),
        "ClaudeBot": m("ClaudeBot", visits=1438),
        "AhrefsBot": m("AhrefsBot", bot_class="crawler", visits=40, hits=5),
        "PetalBot": m("PetalBot", visits=147, hits=6),
    }
    entries, summary = catalog.build_catalog(claims, cf_by_slug, measurements)
    by_name = {e.name: e for e in entries}

    check("measured bot without a claims entry appears", "PetalBot" in by_name, True)
    check("…as not yet recorded", by_name["PetalBot"].docs_recorded, False)
    check("claims entry without visits is dropped", "NeverSeen" in by_name, False)
    gpt_robots = [c for c in by_name["GPTBot"].claims if c.claim.question == "robots_txt"]
    check("both sources contradicted", [c.contradicted for c in gpt_robots], [True, True])
    check("reason carries the count", {c.reason for c in gpt_robots}, {"3 honeypot hits"})
    check("no hits → not contradicted",
          [c.contradicted for c in by_name["ClaudeBot"].claims], [False])
    check("crawler with hits is never contradicted",
          [c.contradicted for c in by_name["AhrefsBot"].claims], [False])
    check("user-agent claims are never links",
          [c.is_link for c in by_name["GPTBot"].claims if c.claim.source == "user-agent"], [False])
    check("other claims with a URL are links",
          all(c.is_link for c in by_name["GPTBot"].claims if c.claim.source == "operator-docs"), True)
    check("order: hits desc, then visits desc",
          [e.name for e in entries], ["PetalBot", "AhrefsBot", "GPTBot", "ClaudeBot"])
    check("summary", summary, catalog.CatalogSummary(bots=4, docs_recorded=3, with_contradiction=1))
    check("1 hit is singular", catalog.build_catalog(
        claims, {}, {"GPTBot": m("GPTBot", hits=1)})[0][0].claims[0].reason, "1 honeypot hit")

    # Cloudflare's file is a third-party copy: only plain http(s) URLs may link.
    def operator_link(url):
        entry = {**cf_entry, "operatorUrl": url, "signatureAgentUrl": None}
        built = catalog.build_catalog(
            {"GPTBot": claims["GPTBot"]}, {"gptbot": entry}, {"GPTBot": m("GPTBot")})[0][0]
        return [c.is_link for c in built.claims if c.claim.question == "operator"]
    check("javascript: URL is not a link", operator_link("javascript:alert(4)"), [False])
    check("scheme-less URL is not a link", operator_link("authory.com"), [False])
    check("URL with a space is not a link", operator_link(" https://www.bnf.fr"), [False])
    check("http URL links", operator_link("http://ahrefs.com/robot/"), [True])
    js_html = catalog.render_html(*catalog.build_catalog(
        {"GPTBot": claims["GPTBot"]},
        {"gptbot": {**cf_entry, "operatorUrl": "javascript:alert(4)"}}, {"GPTBot": m("GPTBot")}))
    check("no javascript: href in HTML", 'href="javascript:' in js_html, False)
    link_md = catalog.render_markdown(*catalog.build_catalog(
        {"GPTBot": claims["GPTBot"]},
        {"gptbot": {**cf_entry, "operatorUrl": "https://example.test/a_(b)"}}, {"GPTBot": m("GPTBot")}))
    check("markdown link uses the <url> form", "](<https://example.test/a_(b)>)" in link_md, True)

    # ── render_html / render_markdown / to_json ─────────────────────────────
    evil_ua = "Evil/1.0 (+https://x.test/a)</script><img src=x>`rm` | x"
    evil = catalog.build_catalog(
        claims, cf_by_slug,
        {"GPTBot": m("GPTBot", visits=124, hits=3, ua=evil_ua),
         "YouBot": m("YouBot", visits=3, signed_before_fix=2)})
    html_out = catalog.render_html(*evil)
    md_out = catalog.render_markdown(*evil)
    check("html: no raw </script> from the UA", "</script><img" in html_out, False)
    check("html: the UA is shown escaped", "&lt;/script&gt;&lt;img" in html_out, True)
    check("html: no img tag from the UA", "<img" in html_out, False)
    check("html: UA URL is not a link", 'href="https://x.test/a"' in html_out, False)
    check("markdown: UA URL is not a link", "](https://x.test/a)" in md_out, False)
    check("markdown: no raw backtick from the UA", "`rm`" in md_out, False)
    check("html: contradiction shown", "contradicted: 3 honeypot hits" in html_out, True)
    check("markdown: contradiction shown", "contradicted: 3 honeypot hits" in md_out, True)
    youbot_html = html_out.split("YouBot")[1]
    check("failures before the fix are labelled", "failed before our verifier fix" in youbot_html, True)
    check("…and never as verified", "verified" in youbot_html.replace("verifier", ""), False)
    check("empty catalog says so",
          "No bots observed yet" in catalog.render_html([], catalog.CatalogSummary(0, 0, 0)), True)
    check("html: one table", html_out.count("<table"), 1)
    check("html: one row per bot", html_out.split("<tbody>")[1].count("<tr"), 2)
    check("html: robots.txt claims column", "Obeys robots.txt?" in html_out, True)
    md_table = [line for line in md_out.splitlines() if line.startswith("|")]
    cells = lambda line: len(line.replace("\\|", "").split("|"))  # noqa: E731
    check("markdown: header, separator and one row per bot", len(md_table), 4)
    check("markdown: a pipe in the UA does not add a column",
          {cells(line) for line in md_table}, {cells(md_table[0])})
    as_json = catalog.to_json(*evil)
    check("json serialises", isinstance(json.dumps(as_json), str), True)
    check("json has summary and bots", sorted(as_json), ["bots", "summary"])
    check("json keeps the contradiction",
          any(c["contradicted"] for c in as_json["bots"][0]["claims"]), True)

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
