# Bot Catalog — Design

**Date:** 2026-11-17
**Status:** Approved 2026-11-17, pending implementation plan. Build after the 2026-11-19 signature check.
Build after the 2026-11-19 production check of Web Bot Auth results.

## Intent

There is no standard for a bot to describe itself. Each piece of a bot's
identity lives somewhere different:

- `robots.txt` (RFC 9309) holds the *site's* rules. The bot says nothing in it.
- The `+https://…` URL in a User-Agent is a convention. Nothing specifies it,
  and anyone can forge it.
- IP lists and reverse-DNS checks exist, but every operator does them its own way.
- Web Bot Auth (IETF, in progress) proves *who signed* a request. Its key
  directory holds keys only, with nothing about purpose or behaviour.
- Nothing standard covers *what the bot promises*: whether it obeys
  `robots.txt`, what the data is for, or how to opt out. Commercial registries
  (Cloudflare Radar, Dark Visitors) fill that gap with data *someone else*
  entered about the bot.

The catalog is **evidence of that gap**. For every named bot we have observed,
it lists what is claimed about the bot, **where each claim comes from**, and
what the bot actually did on this site. The source column is the content.
Where sources disagree or are missing, the page shows it. An empty cell is a
finding, not a defect.

Target sentence, roughly: *"For N bots, we collected every statement about who
they are and what they promise, from four places. On only M of them do the
sources agree with each other and with what the bot did here."*

## Goals

- One page, `/bots`, readable without JavaScript, plus `/bots.md` and
  `/api/bots` (JSON). Same three-format pattern as the grounding pages.
- Per bot, the same five questions, so rows compare across bots:
  1. **Who runs it, and what is it for?**
  2. **Does it obey `robots.txt`?**
  3. **How do you recognise it?** (UA patterns, published IP list, reverse DNS)
  4. **Does it sign its requests (Web Bot Auth)?**
  5. **Where is it documented, and how do you opt out?**
- Every answer is listed once per source. Possible sources:
  - `user-agent`: what the bot's own UA string says (info URL, name)
  - `cloudflare`: the vendored `app/cf_bots.json`
  - `operator-docs`: hand-recorded from the operator's own documentation
  - `signature-directory`: what the bot's Web Bot Auth key directory shows
- Every hand-recorded claim carries a link and a retrieval date. Without a date,
  "the docs say X" cannot be checked six months later.
- Per bot, measured on this site:
  - visits
  - honeypot hits (spoof-filtered, as on the scoreboard)
  - whether a client with that name fetched `/robots.txt` before its first
    honeypot hit
  - discovery reads
  - signed requests, split into verified and failed
  - times other clients used its name in a spoofing burst
- A claim that the measurements contradict is marked as such next to the claim.
  Example: "obeys robots.txt (cloudflare)" next to "3 honeypot hits".
- Reading `/bots`, `/bots.md` or `/api/bots` is logged as a discovery read, like
  the grounding pages. As a side effect this measures whether agents read
  statements about themselves.

## Non-goals

- No general bot registry. Only named bots that have visited this site.
- No HTTP clients (curl, httpx, Go) and no browser UAs. They state no
  identity, and a catalog entry would give them one.
- No per-bot pages (`/bots/<slug>`) in this iteration. They are a likely second
  step, with schema.org JSON-LD like the grounding pages.
- No automatic scraping of operator documentation.
- No standard proposal (for example a `/.well-known/` self-description file).
  The catalog may motivate one later; it is not part of this work.

## Anti-goals (agreed)

- **Never silently correct a source.** If Cloudflare says GoogleOther does not
  obey `robots.txt`, the page shows exactly that, attributed to Cloudflare. Our
  own measurement stands next to it.
- **Never link a URL taken from a User-Agent.** The string is attacker-controlled
  input. Show it as escaped text labelled "stated in UA". Only URLs from
  `cloudflare` or `operator-docs` become links.
- **Never present "stated" as "verified".** A name in a UA proves nothing; the
  spoofing section already shows this. The page uses the word "verified" only
  for Web Bot Auth signatures that passed.
- **Never conflate "not recorded yet" with "operator says nothing".** Bots whose
  docs have not been hand-recorded show "not yet recorded" in the
  `operator-docs` rows, distinct from "no statement found".
- **Never show a rate without its count.** Many bots have one to three visits.

## Constraints

- Python 3.12 / FastAPI, async throughout. Parameterised SQL only. No new
  dependencies (the stack already has stdlib `json` and `markdown-it-py`).
- `app/main.py` is already ~1,700 lines. The catalog lives in its own module
  (for example `app/catalog.py`), like `facts.py` and `spoofing.py`.
- Non-AI crawlers (AhrefsBot, SeznamBot…) are stored with `bot_name` NULL. Their
  identity comes from `classify_ua` at read time, as the Discovery Reads table
  already does. AI bots have `bot_name` set at write time. The catalog must
  join both paths onto one list.
- Measurements have to be aggregated in SQL, not per row in Python. The visits
  table grows without bound within its retention window.
- Leave alone: `robots.txt`, the honeypot path list, and IP hashing.

## Approaches

**A. Server-rendered page, hand-recorded claims in one JSON file (chosen).**
The claims live in `app/bot_claims.json`: per bot, per question, a list of
claims with source, link, date and an optional short note. On request the
server merges that file with `cf_bots.json`, the UA-derived statements and one
aggregated measurement query, and caches the result for about 60 s. Renders HTML,
Markdown and JSON. Agents without JavaScript get the full content. JSON maps
"several sources per question, each with a date" directly. A test can enforce
that every hand-recorded claim has a source URL and a date.

**B. One Markdown file per bot (`content/bots/<slug>.md`).** Matches the blog and
facts pattern and makes prose notes pleasant to write. Rejected: the existing
front-matter parser is flat key/value. Several sources per question would need
either a YAML dependency or an invented format.

**C. Dashboard-style static page plus JS fetching `/api/bots`.** Rejected: bots
without JavaScript would see an empty table, and their reading is exactly what
we want to measure.

## How it works

### Claims file (`app/bot_claims.json`)

Shape (illustrative, not final field names):

```json
{
  "gptbot": {
    "name": "GPTBot",
    "match": ["gptbot"],
    "claims": {
      "robots_txt": [
        {"value": "obeys", "source": "operator-docs",
         "url": "https://platform.openai.com/docs/bots", "retrieved": "2026-11-20",
         "note": "…"}
      ],
      "opt_out": [ … ],
      "ip_list": [ … ]
    }
  }
}
```

- Keys are stable slugs. `match` ties a catalog entry to the identities the app
  already produces: `bot_name` for AI bots, the `classify_ua` name for non-AI
  crawlers.
- `user-agent` claims and the `cloudflare` fields other than `robots.txt` are not
  stored here. They are derived at render time, so they cannot drift from their
  source. The `cloudflare` `robots.txt` claim *is* stored here, hand-checked on
  Radar (see "Decisions after the builder check").
- `signature-directory` claims come from what we observed. A bot that sent a
  verified signature has a working directory; we do not crawl directories
  on page render.

### Which bots appear

Every named identity with at least one visit in the retention window, AI or not,
minus HTTP clients and browser UAs. Today that is roughly 40. Hand recording
starts with the ~25 with the most visits. The rest show "not yet recorded" for
`operator-docs`.

### Measurements

One aggregated query (or a small fixed number of them) per cache refresh,
grouped by identity. "Fetched `/robots.txt` before its first honeypot hit" uses
the per-`bot_name` rule from the 2026-11-13 analysis (any client with the same
bot name, earlier timestamp). For non-AI crawlers the identity grouping happens
over distinct UAs, as in the discovery query. Spoofed visits are excluded from
the bot they impersonated, using `spoofing.find_spoofed_visit_ids`, like the
scoreboard.

### Page layout (sketch)

```
/bots — Who bots say they are, and what they did here

GPTBot · OpenAI                                     124 visits · 3 honeypot hits
  obeys robots.txt     yes            cloudflare      ✕ contradicted: 3 honeypot hits
                       yes            operator docs (2026-11-20)
  signs requests       —              no source       0 signed requests
  info URL             openai.com/gptbot   stated in UA (not a link)
                       platform.openai.com/docs/gptbot   cloudflare
  opt out              robots.txt "User-agent: GPTBot"   operator docs (2026-11-20)
  …
```

Above the list, a short intro states the gap (from Intent) and a summary line:
how many bots have operator-docs coverage, and how many have at least one
contradicted claim.

### Contradiction rules

Kept explicit and few, so the page never over-claims:

- `robots_txt = obeys` is contradicted by ≥ 1 non-spoofed honeypot hit. This
  applies to AI bots only; non-AI crawlers are not spoof-filtered and get no verdict.
- There is no rule for signing (see "Decisions after the builder check").
- A claim with no rule is shown without a verdict.

## Decisions after the builder check

Calls made by the designer (marked so the user can check them):

- **Signing measurements start at f9873f9 (2026-11-17).** Every signed request was
  logged `failed` until 66e5b56, and bare-origin agents failed until f9873f9,
  both because of our verifier. `verified`/`failed` counts only use rows after
  the f9873f9 deploy. Older signed rows count as "signed (before our verifier
  fix)" with a one-line note. *(designer's call)*
- **No contradiction rule for signing.** Anyone who borrows a name produces
  unsigned visits, and spoof filtering only catches rotation. So "signs, but
  sent unsigned requests" would mark nearly every signer as contradicted. The
  signing row shows counts only, never a verdict. The only contradiction rule
  left is the `robots.txt` one. *(designer's call; replaces the second rule
  under "Contradiction rules")*
- **Non-AI crawlers are not spoof-filtered.** Their rows have `bot_name` NULL,
  and filtering them would mean classifying every crawler row in Python. Their
  counts are shown unfiltered, labelled "not checked for spoofing", and they
  get no "contradicted" verdict. *(designer's call)*
- **Bots that signed are added to `NON_AI_CRAWLERS` if they are not known yet.**
  These are ibou-search, Barkrowler, GeedoShopProductFinder, ExaSearchBot and
  RiverBot. This is read-time classification only, so the scoreboard does not
  change. Without it, question 4 would be almost empty, and the only bot ever
  verified would be missing. *(designer's call)*
- **No schema change.** The `signature-directory` source is "a signature from
  this bot verified at least once here". A non-null `signatureAgentUrl` in
  `cf_bots.json` becomes a `cloudflare` claim: "publishes a key directory".
  That is not "signs every request". *(designer's call)*
- **UA source = the most frequent UA per identity only**, with the info URL
  extracted as escaped text. Showing every distinct UA would publish
  spoofer-chosen strings as claims about a real bot. *(designer's call)*
- **Cloudflare matching is explicit.** Every catalog entry in `bot_claims.json`
  carries a `cloudflare_slug` (or `null`). That includes stub entries for bots
  with no hand-recorded docs yet, so all ~40 bots have an entry. No fuzzy
  name matching: our "Googlebot" is "GoogleBot" there, and ClaudeBot is
  missing. *(designer's call)*

**Cloudflare's `followsRobotsTxt` (decided by the user: check Radar by hand).**
The vendored `cf_bots.json` has `false` for 560 of 607 bots, including GoogleBot
and AhrefsBot, which both obey `robots.txt` (Ahrefs is clean here). It is a
third-party copy (microlinkhq), and `false` almost certainly means "no value".
So the catalog does **not** use the file's `followsRobotsTxt`. For every catalog
bot, the `robots.txt` answer on Cloudflare Radar is looked up by hand and recorded
in `bot_claims.json` as source `cloudflare`, with the Radar URL and the retrieval
date, like an `operator-docs` claim. If Radar states nothing, the record says
"no statement on Radar". Other fields from the file (`operatorUrl`, `category`,
`signatureAgentUrl`) are still derived at render time. This adds about 40 hand
lookups to the content work under "Left to the builder".

## Left to the builder

- Exact JSON field names and validation (a test that every `operator-docs`
  claim has `url` and `retrieved`).
- Cache mechanism and TTL (match the existing `/api/stats` approach if there is one).
- How `/bots` is linked: footer, llms.txt, sitemap, api-catalog. Probably all
  four, matching how `/facts` is wired.
- Markdown rendering of the same content for `/bots.md`.
- Recording the operator docs for the first ~25 bots. This is content work and
  can ship after the code, behind "not yet recorded".
