# Bot Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/bots` and `/api/bots`. For every named bot observed here, they list each claim about the bot with its source, next to what the bot did on this site.

**Architecture:**
- New module `app/catalog.py`. It holds pure functions that load claims, derive the extra sources, combine the measurements and render the page, plus one async SQL fetch.
- Hand-recorded claims live in `app/bot_claims.json`.
- `app/main.py` only wires the routes, a single-flight cache, logging and links.

**Tech Stack:** Python 3.12, FastAPI, aiomysql, stdlib `json`/`re`/`dataclasses`. Tests are plain scripts with a `check()` helper, run as `python test_x.py`.

**Spec:** `docs/superpowers/specs/2026-11-17-bot-catalog-design.md`

**Start condition:** Do not start before the 2026-11-19 production check of
`signature_status` (memory `web-bot-auth-friday-check`). Task 1 needs its UA strings.

## Global Constraints

- Async all the way, with `%s` placeholders only. No new dependencies.
- Timestamps are naive UTC. Use `datetime.now(timezone.utc).replace(tzinfo=None)`.
- Do not touch `robots.txt`, the honeypot paths or IP hashing.
- Source names are exactly `user-agent`, `cloudflare`, `operator-docs` and `signature-directory`.
- Questions are exactly `operator`, `robots_txt`, `recognition`, `signing` and `docs_opt_out`.
- `robots_txt` values are exactly `obeys`, `does-not-obey` and `no-statement`.
- Never use `followsRobotsTxt` from `app/cf_bots.json`. The Cloudflare `robots_txt` claim comes only from a hand-checked Radar entry in `bot_claims.json`.
- A URL derived from a User-Agent is never rendered as a link, in HTML or in Markdown.
- The word "verified" appears only for Web Bot Auth signatures that passed.
- Every rate is shown with its count.
- `SIGNING_COUNT_SINCE = datetime(2026, 11, 17, 9, 30)` (UTC). The f9873f9 image was pushed at 09:24:34Z, so this is just after it went live.
- Signed rows before that time count only as `signed_before_fix`.

## Review Focus

- A bot with visits but no `bot_claims.json` entry still appears, as a stub with "not yet recorded". Test in Task 4.
- A UA containing `<script>`, `</script>`, `](javascript:` or backticks renders inert in HTML and in Markdown. Tests in Task 2 and Task 5.
- An empty `visits` table gives a page that says no bots were observed, not an error or an empty table. Test in Task 5.
- A non-AI crawler with honeypot hits whose claims say `obeys` gets no "contradicted" verdict, because it is not spoof-filtered. Test in Task 4.
- A bot that only signed before `SIGNING_COUNT_SINCE` shows "signed before our verifier fix", never "verified" or "failed". Test in Task 3.

---

### Task 1: Name the bots that sign

**Files:**
- Modify: `app/bots.py` (`NON_AI_CRAWLERS`, the comment block above it)
- Test: `test_ua_classification.py` (`CLASSIFY_CASES`)

**Interfaces:**
- Produces: `classify_ua()` returns `CLASS_CRAWLER` with these names: `IbouBot` (ibou), `Barkrowler` (Babbar), `GeedoShopProductFinder`, `ExaSearchBot`, `RiverBot`.

- [ ] **Step 1: Get the real UA strings.** Run a read-only production query through `mw container exec` (see memory `goodbot-badbot-prod-db-queries`):
  `SELECT user_agent, COUNT(*) FROM visits WHERE signature_status IS NOT NULL GROUP BY user_agent`.
  Take the operator names from each UA's info URL. Cross-check `cf_bots.json` slugs `iboubot-3` and `babbar-barkrowler`. If a UA names no operator, use `"unknown"`, as for mOptimizer.
- [ ] **Step 2: Write the failing tests.** Add one `CLASSIFY_CASES` row per bot, using the observed UA verbatim. Expected class is `CLASS_CRAWLER` and the name is as above.
- [ ] **Step 3: Run them to make sure they fail.** Run `.venv/bin/python test_ua_classification.py`. Expected: 5 FAIL.
- [ ] **Step 4: Add the five entries to `NON_AI_CRAWLERS`.** Use the lowercase substring patterns `iboubot`, `barkrowler`, `geedoshopproductfinder`, `exasearchbot` and `riverbot`, adjusted to the real UAs. Put them in a new group comment: `# Signers: self-declared crawlers seen sending Web Bot Auth signatures`.
- [ ] **Step 5: Run all tests.** Run `for t in test_*.py; do .venv/bin/python "${t}" >/dev/null || echo "FAIL ${t}"; done`. Expected: no output.
- [ ] **Step 6: Commit.** Message: `feat(bots): name the crawlers that sign their requests`

### Task 2: Claims file, its validation, and the derived sources

**Files:**
- Create: `app/catalog.py`, `app/bot_claims.json`
- Test: `test_catalog.py` (new; plain script with `check(label, got, want)` like `test_signature_verification.py`)

**Interfaces:**
- Produces, in `app/catalog.py`:
  - `QUESTIONS: tuple[str, ...]`, `SOURCES: tuple[str, ...]`, `ROBOTS_VALUES: tuple[str, ...]`, all as in Global Constraints.
  - `@dataclass(frozen=True) class Claim: question: str; value: str; source: str; url: str | None; retrieved: str | None; note: str = ""`
  - `@dataclass(frozen=True) class BotClaims: slug: str; name: str; match: tuple[str, ...]; cloudflare_slug: str | None; docs_recorded: bool; claims: tuple[Claim, ...]`
  - `def validate_claims(raw: dict, cf_slugs: set[str], today: date) -> list[str]`: returns readable errors, and an empty list means valid.
  - `def load_claims(path: Path, cf_slugs: set[str]) -> dict[str, BotClaims]`: keyed by every name in `match`. Raises `ValueError` listing all errors if validation fails.
  - `def ua_info_url(user_agent: str) -> str | None`
  - `def derived_claims(name: str, cf_entry: dict | None, top_user_agent: str | None) -> list[Claim]`

Shape of `bot_claims.json` (top-level object keyed by slug):

```json
{"gptbot": {"name": "GPTBot", "match": ["GPTBot"], "cloudflare_slug": "gptbot",
  "docs_recorded": false, "claims": {}}}
```

`claims` maps a question to a list of `{"value", "source", "url", "retrieved", "note"?}`. For this task, ship the file with stub entries only (`docs_recorded: false`, empty `claims`) for:
- every name in the current `/api/stats` `summary`
- every non-AI crawler in the discovery table
- the five bots from Task 1

Look up each `cloudflare_slug` in `cf_bots.json` by hand, or set it to `null`.

- [ ] **Step 1: Write the failing tests** in `test_catalog.py`:
  - `validate_claims` returns errors for each of these:
    - a `source` not in `operator-docs`/`cloudflare` (stored claims may only use these two)
    - a missing `url`
    - a `url` not starting with `https://`
    - `retrieved` missing, not ISO `YYYY-MM-DD`, or after `today`
    - an unknown question key
    - a `robots_txt` value outside `ROBOTS_VALUES`
    - the same name in two entries' `match`
    - a `cloudflare_slug` not in `cf_slugs`
  - A valid file returns `[]`.
  - `validate_claims(json.load(open("app/bot_claims.json")), <slugs from cf_bots.json>, date.today()) == []`. This guards the real file from now on.
  - `ua_info_url`:
    - `"Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"` → `"https://openai.com/gptbot"`
    - `"curl/8.7.1"` → `None`
    - a UA with `+https://x.test/a)<script>` → `"https://x.test/a"`, so the match stops at `)`, whitespace, `;` and `<`
  - `derived_claims("GPTBot", cf_entry, ua)`:
    - yields a `cloudflare` claim for `operator` with `cf_entry["operatorUrl"]`, and a `user-agent` claim for `docs_opt_out` with the UA URL
    - when `signatureAgentUrl` is set, yields `Claim("signing", "publishes a key directory", "cloudflare", <that url>, None)`
    - never yields a `robots_txt` claim, even if `cf_entry["followsRobotsTxt"]` is `True`
- [ ] **Step 2: Run** `.venv/bin/python test_catalog.py`. Expected: ImportError, then FAILs.
- [ ] **Step 3: Implement** the interfaces above. `ua_info_url` uses `re.search(r"\+(https?://[^\s;)<>\"']+)", ua)`. The stub `bot_claims.json` comes as described.
- [ ] **Step 4: Run** `.venv/bin/python test_catalog.py`. Expected: all PASS.
- [ ] **Step 5: Commit.** Message: `feat(catalog): add the claims file and the derived sources`

### Task 3: Measurements

**Files:**
- Modify: `app/catalog.py`
- Test: `test_catalog.py`

**Interfaces:**
- Consumes: `app.bots.classify_ua`, `CLASS_AI`, `CLASS_CRAWLER`; `app.spoofing.find_spoofed_visit_ids`
- Produces:
  - `SIGNING_COUNT_SINCE: datetime`
  - `@dataclass class Measurements: name: str; bot_class: str; operator: str; visits: int; honeypot_hits: int; spoof_filtered: bool; robots_read_before_first_hit: bool | None; discovery_reads: int; signed_verified: int; signed_failed: int; signed_before_fix: int; spoofed_by_others: int; top_user_agent: str | None`
  - `def combine_measurements(named_rows: list[dict], named_visits: list[dict], crawler_ua_rows: list[dict]) -> dict[str, Measurements]`. This is pure.
  - `async def fetch_measurements(cur, discovery_paths: tuple[str, ...], discovery_prefixes: tuple[str, ...]) -> dict[str, Measurements]`. It runs the SQL and calls `combine_measurements`.

Row shapes that `fetch_measurements` produces and `combine_measurements` consumes:
- `named_rows` holds one row per (`bot_name`, `operator`, `user_agent`) for `bot_name IS NOT NULL`:
  - `visits`, `honeypot`, `discovery`
  - `verified_since`, `failed_since` (`ts >= SIGNING_COUNT_SINCE`), `signed_before` (`ts < SIGNING_COUNT_SINCE AND signature_status IS NOT NULL`)
  - `first_honeypot_ts`, `first_robots_ts`
- `named_visits` uses the exact columns `_compute_stats` already selects for spoofing (`id, ts, ip_hash, bot_name, operator, path, is_honeypot`).
- `crawler_ua_rows` holds the same aggregate columns grouped by `user_agent` for `bot_name IS NULL`, `LIMIT 500`. The limit mirrors `DISCOVERY_UA_GROUP_LIMIT`.

Rules:
- **Spoofing:** for AI names, subtract spoofed honeypot visits from `honeypot_hits`, with `spoof_filtered=True`. `spoofed_by_others` is the number of spoofed visits claiming the name.
- **Crawlers:** classify each *distinct* UA with `classify_ua`. Keep only `CLASS_CRAWLER` and sum by name, with `spoof_filtered=False`.
- **robots.txt before the first hit:** `robots_read_before_first_hit` is `None` without honeypot hits. Otherwise it is `min(first_robots_ts) < min(first_honeypot_ts)` across the name's UAs. This is the per-name rule from the 2026-11-13 analysis.
- **Top UA:** `top_user_agent` is the UA with the most visits for that name.

- [ ] **Step 1: Write the failing tests** with hand-built rows:
  - Two GPTBot UAs sum correctly, and `top_user_agent` is the busier one.
  - A spoofed honeypot visit claiming ClaudeBot lowers ClaudeBot's `honeypot_hits` by 1 and sets `spoofed_by_others == 1`.
  - Two AhrefsBot UA rows and one curl row give one `AhrefsBot` entry with `spoof_filtered is False`, and no curl entry.
  - `robots_read_before_first_hit` is `True`, `False` and `None` in the three cases.
  - A row with only `signed_before=2` gives `signed_before_fix == 2`, `signed_verified == 0` and `signed_failed == 0`.
  - Empty inputs give `{}`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `combine_measurements`, then `fetch_measurements`.
  - Discovery reads are `path IN (discovery_paths) OR path LIKE prefix%` for each prefix, with `method <> 'HEAD'`. Escape `%` in prefixes as `%%` because pymysql formats.
  - `/robots.txt` counts as the robots fetch.
- [ ] **Step 4: Run** `test_catalog.py`. Expected: PASS.
- [ ] **Step 5: Commit.** Message: `feat(catalog): measure what each bot did here`

### Task 4: Assemble the entries and apply the contradiction rule

**Files:**
- Modify: `app/catalog.py`
- Test: `test_catalog.py`

**Interfaces:**
- Consumes: `BotClaims`, `Claim`, `derived_claims`, `Measurements`
- Produces:
  - `@dataclass(frozen=True) class ShownClaim: claim: Claim; is_link: bool; contradicted: bool; reason: str`
  - `@dataclass class CatalogEntry: name: str; operator: str; bot_class: str; docs_recorded: bool; claims: list[ShownClaim]; measurements: Measurements`
  - `@dataclass(frozen=True) class CatalogSummary: bots: int; docs_recorded: int; with_contradiction: int`
  - `def build_catalog(claims: dict[str, BotClaims], cf_by_slug: dict[str, dict], measurements: dict[str, Measurements]) -> tuple[list[CatalogEntry], CatalogSummary]`

Rules:
- **Which entries:** one entry per name in `measurements` with `visits >= 1`, so claims entries without visits are dropped.
- **Missing claims entry:** an entry with no claims entry gets `docs_recorded=False` and only derived claims.
- **Contradiction:**
  - `contradicted=True` only for `question == "robots_txt" and value == "obeys"`, on a `CLASS_AI` entry with `honeypot_hits >= 1`.
  - `reason` is then `f"{n} honeypot hit(s)"`, with the count.
  - It applies to every source carrying that claim.
- **Links:** `is_link=False` for every `user-agent` claim.
- **Order:** honeypot hits descending, then visits descending.

- [ ] **Step 1: Write the failing tests:**
  - Stub fallback: a measured name with no claims entry appears, with `docs_recorded False`.
  - An unmeasured claims entry is absent.
  - An AI bot with 3 hits and `obeys` from two sources gets two contradicted claims, both with `reason "3 honeypot hits"`.
  - An AI bot with 0 hits gets no contradiction.
  - A crawler with 5 hits and an `obeys` claim gets no contradiction.
  - `user-agent` claims have `is_link False`.
  - The summary counts match the fixture.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `build_catalog`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.** Message: `feat(catalog): assemble entries and mark contradicted claims`

### Task 5: Render HTML, Markdown and JSON

**Files:**
- Modify: `app/catalog.py`
- Test: `test_catalog.py`

**Interfaces:**
- Consumes: `CatalogEntry`, `CatalogSummary`; `app.facts._page` (reuse; do not add a third copy of the page shell)
- Produces:
  - `def render_html(entries, summary) -> str`
  - `def render_markdown(entries, summary) -> str`
  - `def to_json(entries, summary) -> dict`

Layout:
- **Intro:** the gap paragraph from the spec's Intent, in English like the rest of the site, plus a summary line: `N bots · M with operator docs recorded · K with at least one contradicted claim`.
- **Per bot:** a heading `Name · Operator`, a measurement line, and the claims grouped by question, with source and date.
- **Wording:**
  - "not yet recorded" where `docs_recorded` is False.
  - "not checked for spoofing" next to crawler counts.
  - Signing: "N verified, M failed since 2026-11-17", plus "K signed before our verifier fix" when K > 0.
  - Only the word "verified" before the verified count.
- **Escaping:**
  - HTML: every value goes through `html.escape`.
  - Markdown: UA-derived text goes inside a code span with backticks stripped, and is never written as `[..](..)` or `<..>`.
- **JSON:** `to_json` returns plain dicts with ISO date strings and no datetimes.

- [ ] **Step 1: Write the failing tests:**
  - Fixture UA URL `https://x.test/a`, and a top UA containing `</script><img src=x>` and a backtick. Check:
    - The HTML has no `<script` and no `<img`.
    - The HTML has no `href="https://x.test/a"`.
    - The Markdown has no `](https://x.test/a)`.
  - A contradicted claim renders `contradicted: 3 honeypot hits` in both formats.
  - `render_html([], CatalogSummary(0, 0, 0))` contains `No bots observed yet`.
  - `json.dumps(to_json(...))` succeeds.
  - A bot with only `signed_before_fix` renders `signed before our verifier fix` and not `verified`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the three renderers.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.** Message: `feat(catalog): render the catalog as HTML, Markdown and JSON`

### Task 6: Routes, cache, logging and links

**Files:**
- Modify: `app/main.py`
  - routes next to the `/facts` routes
  - `RATE_LIMIT_RULES`
  - sitemap builder
  - llms.txt "Grounding pages" section
- Modify: `templates/index.html` (footer, after `facts`)
- Test: `test_catalog.py` (route-level checks via `fastapi.testclient.TestClient`, with the cached builder stubbed, the way `test_mcp_route.py` stubs the DB)

**Interfaces:**
- Consumes: `catalog.load_claims`, `fetch_measurements`, `build_catalog`, `render_html`, `render_markdown`, `to_json`
- Produces:
  - `GET /bots`: HTML, or Markdown when `_wants_markdown(accept)`.
  - `GET /api/bots`: JSON.
  - Both are logged with `_should_log_meta_visit` and `log_visit(..., is_honeypot=False)` under their own path.
  - Rate limit `("/bots", 60)` and `("/api/bots", 60)`.
  - Single-flight cache `CATALOG_TTL_S = 60`, the same pattern as `_get_stats_cached`.
  - Claims load once at startup. A validation error fails startup loudly, the same way a missing `POW_SECRET` would.

- [ ] **Step 1: Write the failing route tests:**
  - `/bots` returns 200 `text/html`.
  - `/bots` with `Accept: text/markdown` returns `text/markdown`.
  - `/api/bots` returns JSON with `summary` and `bots` keys.
  - `/sitemap.xml` contains `/bots`.
  - `/llms.txt` contains `https://goodbot-badbot.com/bots`.
- [ ] **Step 2: Run.** Expected: FAIL (404).
- [ ] **Step 3: Implement** the routes, cache, rate limits and links.
- [ ] **Step 4: Run all tests.** Run `for t in test_*.py; do .venv/bin/python "${t}" >/dev/null || echo "FAIL ${t}"; done`. Expected: no output.
- [ ] **Step 5: Check it locally.** Run `docker compose up -d --build`, seed visits with bot UAs as in the 2026-11-17 session, then open `http://localhost:8000/bots` at 390 px and 1440 px in both themes. Expected: stubs render, there is no horizontal page scroll, and no UA URL is a link.
- [ ] **Step 6: Test inside the built image** (memory `goodbot-badbot-dependency-drift`). Mount `test_catalog.py` into `goodbot-badbot-web`. Expected: all PASS.
- [ ] **Step 7: Commit.** Message: `feat(catalog): serve /bots and /api/bots`

### Task 7: Record the sources by hand

**Files:**
- Modify: `app/bot_claims.json`
- Test: the `validate_claims` guard from Task 2

- [ ] **Step 1:** For the ~25 bots with the most visits on production `/api/bots`, read the operator's own documentation. Record `operator`, `robots_txt`, `recognition`, `signing` and `docs_opt_out` claims with `source: "operator-docs"`, the exact page URL and today's date. Set `docs_recorded: true`. If the docs say nothing on a question, record `no-statement` for `robots_txt` and leave the other questions out.
- [ ] **Step 2:** For **every** catalog bot, open its Cloudflare Radar bot page. Record the `robots_txt` claim with `source: "cloudflare"`, the Radar URL and the date. If Radar states nothing, use `no-statement`.
- [ ] **Step 3: Run** `.venv/bin/python test_catalog.py`. Expected: PASS. The real-file validation is part of it.
- [ ] **Step 4: Commit.** Message: `content(catalog): record operator docs and Radar statements`

### Task 8: Deploy and verify

- [ ] **Step 1:** Run `./deploy.sh`. Expected: `live version: <sha>`.
- [ ] **Step 2:** `curl -s https://goodbot-badbot.com/api/bots | python3 -m json.tool | head`. Expected: `summary.bots` > 0.
- [ ] **Step 3:** Check `https://goodbot-badbot.com/bots` at 390 px and 1440 px. Expected: GeedoShopProductFinder and AhrefsBot appear, and the signing rows match the 2026-11-19 DB check.
