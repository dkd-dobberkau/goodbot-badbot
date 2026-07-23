---
title: An API catalog — an offer, not a trap
date: 2026-07-23
summary: We added a /.well-known/api-catalog so agents can discover our stats API instead of scraping the dashboard. It is the mirror image of a honeypot — a positive signal on a third axis — and, following Dries Buytaert's own experiment, we fully expect it to read zero for months. That silence is itself the measurement.
---

This site keeps learning new dialects of "please read me correctly": a
`robots.txt` with Content Signals, an `llms.txt` summary, an `agents.md` probe
surface, Web Bot Auth keys, and [grounding pages](/facts). This week it learned
one more, and it is the first one that is a genuine *offer* rather than a hint
or a boundary: a **`/.well-known/api-catalog`**.

## What it is

The idea comes straight from [Dries Buytaert's
experiment](https://dri.es/helping-agents-discover-my-site-search-with-an-api-catalog):
publish a machine-readable index of your site's APIs at a well-known path, so
an agent can find and call the interface instead of guessing at URLs or parsing
HTML. Ours is a small [RFC 9264](https://www.rfc-editor.org/rfc/rfc9264.html)
linkset with three relations, anchored at the site root:

- **`service-desc`** → `/openapi.json`, the OpenAPI description of the API.
- **`service-doc`** → `/llms.txt`, the prose an LLM would read first.
- **`item`** → `/api/stats`, the one genuinely useful machine endpoint we have:
  the live per-bot compliance numbers as JSON.

That is the whole point of the catalog test — we already *had* the API. The
`/api/stats` feed has been the distribution target of our
[goodbot-badbot Dataset](/facts/goodbot-badbot) grounding page for weeks, and
the homepage has advertised it in an RFC 8288 `Link` header the whole time. The
catalog just puts a signpost at the address agents are told to look for.

## Why it fits: a third axis

Regular readers know this project's discipline: three different things must not
be blurred together.

- A **honeypot** tests a *rule*. `/robots.txt` says *Disallow*; a crawler that
  visits anyway is logged as a violation. That feeds the good-bot/bad-bot
  verdict.
- A **discovery read** — `llms.txt`, `agents.md`, a grounding page — tests
  *curiosity*. Fetching one is the opposite of a violation: an agent
  deliberately doing discovery. It is logged, but it never touches the verdict.
- The **API catalog** tests an *offer*. Not "did the bot read a hint" but "did
  the bot use the interface we explicitly documented, instead of scraping the
  dashboard". That is a distinct, more demanding signal than curiosity.

So the catalog gets its own column in the
[Discovery Reads](/) table, next to llms.txt, agents.md and grounding pages —
and, critically, it stays **out of the verdict entirely**. Ignoring an offer is
not misbehaviour. A crawler that never touches the catalog is not a bad bot; it
just did not take us up on the invitation. Wiring an offer into the good/bad
score would quietly corrupt the one number this site exists to keep honest.

## The honest part

Here is where the intellectual honesty this project runs on has to kick in.
Dries' own conclusion, after months live, is that **almost nothing queries an
API catalog yet** — the same deflating result he got from `llms.txt`. If we are
truthful, we expect to see exactly that: `/.well-known/api-catalog` reading zero
for a long time.

For most sites that would be a reason not to bother. For this one it is the
opposite. "Six months live, N reads" is precisely the kind of negative evidence
we publish instead of vibes. A quiet column is not a failed feature — it is a
measurement of how far the agent ecosystem actually is from the future everyone
keeps announcing. When the first non-zero read lands, we will know which
operator got there first, and when.

## Keeping the trap out of the catalog

One subtlety worth writing down, because it is the kind of thing that quietly
undermines an experiment. FastAPI generates an OpenAPI document for *every*
route by default — which would have listed all six honeypot paths as ordinary,
callable endpoints. The honeypots are no secret (they are spelled out in
`robots.txt` and `llms.txt`), so this was never a leak. But a catalog is an
offer, and framing a trap as a normal endpoint in the offer muddies exactly the
line we just drew. So the honeypots are excluded from the schema: the catalog
describes only the real, public data API. An offer should contain only things
you actually mean to give.

So the site now hands agents a documented way in — and, true to form, writes
down whether anyone walks through it.

## Sources and further reading

- [Dries Buytaert — Helping agents discover my site search with an API catalog](https://dri.es/helping-agents-discover-my-site-search-with-an-api-catalog) — the experiment this post follows, including the sobering discovery numbers.
- [RFC 9264](https://www.rfc-editor.org/rfc/rfc9264.html) — Linkset: the media type (`application/linkset+json`) and link relation for a set of links, the format the catalog is served in.
- [RFC 9727](https://www.rfc-editor.org/rfc/rfc9727.html) — `api-catalog`: the well-known URI and `api-catalog` link relation for discovering a site's APIs.
- [RFC 8631](https://www.rfc-editor.org/rfc/rfc8631.html) — Link relation types for web services (`service-desc`, `service-doc`), used to point at the OpenAPI and the prose.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — the description format served at `/openapi.json`.
