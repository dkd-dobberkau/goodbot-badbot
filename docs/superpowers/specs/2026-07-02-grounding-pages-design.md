# Grounding Pages — Design

**Date:** 2026-07-02
**Status:** Approved (brainstorming), pending implementation plan

## Goal

Publish **grounding pages** on goodbot-badbot.com: factual, machine-readable
entity-definition pages that AI answer engines can extract and cite without
hallucinating, and — in keeping with the project's doctrine — that double as a
new **discovery measurement surface** (every read is logged as a positive
signal, exactly like `agents.md`). Ship two grounding pages plus an explanatory
blog post.

A grounding page is distinct from the site's existing agent signals:

- **llms.txt** decides *what* goes into an AI's retrieval pool (declaration).
- **Grounding** is the runtime step where a model uses that pool to answer.
- **A grounding page** is the citable factual source *inside* that pool: it
  states verifiable facts and leaves the conclusion to the model (unlike an
  `/ai-instructions/` page, which prescribes what the model should say).

Reference framework: the "Grounding Page Standard" v1.6 (groundingpage.com).
**Important caveat:** this is a GEO/SEO discipline, **not** an IETF or W3C
standard — the same status as llms.txt. We adopt its editorial rules, not a
formal protocol.

## Scope

Two entities:

1. **The experiment** — `content/facts/goodbot-badbot.md`, schema.org `Dataset`.
2. **The measured concept** — `content/facts/robots-txt-compliance.md`,
   schema.org `DefinedTerm`.

Plus one editorial blog post explaining the concept.

**Out of scope / explicitly rejected:** no fake agent manifest (same
compliance-theatre reasoning the README already applies to DNS-AID / ARD); the
grounding pages describe things that *actually exist*. No trailing-slash URL
scheme (stay consistent with `/blog/{slug}`).

## Architecture — approach A (content-driven, mirrors the blog)

Chosen over a code-defined variant (breaks "content = one file") and over
folding facts into the blog (would mix the *unlogged* editorial surface with
the *logged* measurement surface — a separation the project deliberately keeps).

### New files

| File | Purpose |
|---|---|
| `app/facts.py` | Loads `content/facts/*.md`, parses frontmatter (reuses `blog.parse_frontmatter`), renders HTML (+JSON-LD) and Markdown, builds schema.org from frontmatter |
| `content/facts/goodbot-badbot.md` | Experiment entity (`Dataset`) |
| `content/facts/robots-txt-compliance.md` | Concept entity (`DefinedTerm`) |
| `content/blog/grounding-pages.md` | Explanatory blog post |
| `test_facts.py` | Unit tests (frontmatter → JSON-LD, rendering) |

### Changed files

| File | Change |
|---|---|
| `templates/blog_base.html` | Add `__HEAD_EXTRA__` placeholder before `</head>`; add `/facts` footer link |
| `app/blog.py` | `_page()` gains `head_extra: str = ""` param (blog passes `""`) |
| `app/main.py` | Routes `/facts`, `/facts/{slug}`; logging; sitemap; llms.txt section; Link header; rate-limit rule; `_compute_stats` facts column |
| `templates/index.html` | Discovery table gains a "grounding" column; panel title/intro mention grounding pages; footer `/facts` link |

## Content format

Each fact is `content/facts/<slug>.md` with frontmatter:

```yaml
---
title: goodbot-badbot
entity: goodbot-badbot
entity_type: Dataset          # Dataset | DefinedTerm
segment: AI crawler robots.txt compliance measurement
summary: One-line factual definition (no marketing language).
canonical: https://goodbot-badbot.com/facts/goodbot-badbot
date_modified: 2026-07-02
---
```

Body follows Grounding Standard v1.6 editorial discipline:

- H2 headings prefixed with the entity name (chunk attribution), e.g.
  `## goodbot-badbot methodology`.
- Factual, verifiable, non-persuasive tone.
- Volatile facts (live violation counts) are **not** hard-coded — link to
  `/api/stats` with an "as of" note so the page never goes stale.
- Optional FAQ block.

The filename stem is the slug (same convention as the blog).

## schema.org JSON-LD (`build_jsonld`)

Generated deterministically from frontmatter so the visible text and the
structured facts can never diverge. Emitted as
`<script type="application/ld+json">` in `<head>` via the new `__HEAD_EXTRA__`
token. CSP already allows this (`script-src 'self' 'unsafe-inline'`).

- `entity_type: Dataset` →
  `{"@context":"https://schema.org","@type":"Dataset", name, description,
  url, dateModified,
  creator:{"@type":"Organization","name":"dkd Internet Service GmbH",
  "url":"https://www.dkd.de"},
  isAccessibleForFree:true, license:"https://opensource.org/licenses/MIT",
  distribution:{"@type":"DataDownload","encodingFormat":"application/json",
  "contentUrl":"https://goodbot-badbot.com/api/stats"}}`

The organization identity (`dkd Internet Service GmbH`, `https://www.dkd.de`)
is a shared constant in `app/facts.py`, reused for the `creator` field.
- `entity_type: DefinedTerm` →
  `{"@context":"https://schema.org","@type":"DefinedTerm", name, description,
  url, inDefinedTermSet:"https://goodbot-badbot.com/facts"}`
- Unknown `entity_type` → fall back to a bare `Thing` with name/description/url
  (never crash the render).

## Routing & content negotiation

- `GET /facts` — index listing both entities.
  `Accept: text/markdown` → Markdown index; otherwise HTML.
- `GET /facts/{slug}` — HTML with JSON-LD; `Accept: text/markdown` → raw `.md`
  body; unknown slug → `404 Not Found` (`PlainTextResponse`, as the blog does).
- No trailing slash (consistent with `/blog/{slug}`); `canonical` matches.
- New rate-limit rule `("/facts", 60)` in `RATE_LIMIT_RULES`.

## Discovery logging & dashboard (the measurement surface)

- Every `/facts` and `/facts/{slug}` read is logged via
  `_should_log_meta_visit(path, ua)` + `log_visit(..., is_honeypot=False,
  signature_status=request.state.signature_status)`, logged under the exact
  requested path (so individual grounding pages are distinguishable, like the
  three agents.md probe locations). This is the **positive** discovery signal,
  the opposite of a honeypot violation. The blog stays **unlogged** (editorial,
  not a measurement surface).
- `_compute_stats` discovery query gains a `facts_reads` column
  (`CAST(SUM(path='/facts' OR path LIKE '/facts/%') AS UNSIGNED)`), and the
  `WHERE`/`total_discovery_reads` include `/facts` and `/facts/%`.
- `templates/index.html`: the Discovery Reads table adds a **"grounding"**
  column (colspan 6→7, new `th`, `cell(facts)` in the row template); the panel
  title/intro mention grounding pages alongside llms.txt & agents.md.

## Wiring into existing discovery signals

- **sitemap.xml** (`_build_sitemap`): add `/facts` and each `/facts/{slug}`
  with `lastmod = date_modified` (fallback to `SITEMAP_LASTMOD`).
- **llms.txt**: new `## Grounding pages` section linking both pages (llms.txt is
  the retrieval-pool declaration — the correct place to surface them).
- **Link header** (homepage): append
  `</facts>; rel="describedby"; type="text/html"` to `HOMEPAGE_LINK_HEADER`.
- **Footer** (`index.html` + `blog_base.html`): add a `/facts` link.
- **robots.txt**: unchanged (facts are allowed; sitemap already referenced) —
  respects the "things to leave alone" rule.

## Initial content

- **`goodbot-badbot.md`** (`Dataset`): what the experiment is; methodology
  (linked vs unlinked honeypots); policy (`ai-input=yes, ai-train=no,
  search=yes`); operator dkd; FAQ. Live numbers only as a link to `/api/stats`.
- **`robots-txt-compliance.md`** (`DefinedTerm`): definition of robots.txt
  (RFC 9309); what "compliance" means and how it is measured here; linked vs
  unlinked Disallow; the "treasure map" anti-pattern.
- **`grounding-pages.md`** (blog): grounding pages vs llms.txt vs runtime
  grounding; why we built two; the honest caveat that groundingpage.com is a
  GEO framework, not an IETF/W3C standard; and that — unlike a fake ARD
  manifest — these pages describe real things *and* are a measurement surface.
  Links to `/facts`.

## Testing

`test_facts.py` (stdlib-only for the core, no markdown-it needed):

- `build_jsonld` for `Dataset` and `DefinedTerm` produces the expected shape.
- Unknown `entity_type` falls back to `Thing` without raising.
- Emitted JSON-LD parses as valid JSON.
- Index and single-fact Markdown rendering produce expected structure.
- Existing test suites (`test_blog.py`, bot/signature/jwks) stay green.

## Non-goals

- No new runtime dependency (reuse markdown-it-py and stdlib).
- No changes to honeypot paths, robots.txt content, or IP hashing.
- No dynamic/live figures embedded in page text (only via `/api/stats` link).
