# Grounding Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish two factual, machine-readable grounding pages (schema.org `Dataset` + `DefinedTerm`) plus an explanatory blog post, serving them content-driven like the blog and logging every read as a positive discovery signal.

**Architecture:** New `app/facts.py` mirrors `app/blog.py` — it loads `content/facts/*.md`, parses frontmatter (reusing `blog.parse_frontmatter`), renders HTML (with JSON-LD injected into `<head>`) and raw Markdown, and builds schema.org JSON-LD deterministically from frontmatter. `app/main.py` gains `/facts` + `/facts/{slug}` routes that log reads exactly like the `agents.md` probe surface, plus wiring into sitemap, llms.txt, the homepage Link header, and the dashboard's Discovery Reads table.

**Tech Stack:** Python 3.12, FastAPI (async), aiomysql, markdown-it-py (already a dependency), vanilla HTML/JS. Tests are stdlib smoke scripts run with `python test_<name>.py` (no pytest).

## Global Constraints

- Async all the way: new endpoints are `async def` and must not block on sync I/O.
- Parameterised SQL only (`%s` placeholders); literal `%` in SQL passed with args must be doubled to `%%` (PyMySQL/aiomysql applies `query % args` when args are present).
- Timestamps: naive UTC `DATETIME(6)` via `datetime.now(timezone.utc).replace(tzinfo=None)`.
- No new runtime dependency. Reuse markdown-it-py and stdlib.
- UTF-8 everywhere; no ASCII workarounds for special characters.
- Do NOT modify `/robots.txt` content, honeypot paths, or IP hashing.
- Comments only where the *why* is non-obvious.
- No trailing slash on grounding-page URLs (consistent with `/blog/{slug}`).
- Organization identity constant: name `dkd Internet Service GmbH`, url `https://www.dkd.de`.
- Site base URL: `https://goodbot-badbot.com`.
- Tests are plain scripts with a `main()` returning an exit code, run as `python test_facts.py` — NOT pytest.

---

### Task 1: `app/facts.py` core — frontmatter → schema.org JSON-LD + Fact loading

**Files:**
- Create: `app/facts.py`
- Create: `test_facts.py`

**Interfaces:**
- Consumes: `app.blog.parse_frontmatter(text) -> tuple[dict[str,str], str]`
- Produces:
  - `build_jsonld(meta: dict) -> dict` — schema.org dict from a frontmatter meta dict.
  - `Fact` dataclass with fields: `slug, title, entity, entity_type, segment, summary, canonical, date_modified, html, md, jsonld` (all `str`).
  - `_fact_from_source(raw: str, slug: str) -> Fact | None`
  - `list_facts() -> list[Fact]`, `get_fact(slug: str) -> Fact | None`
  - Module constants: `SITE`, `ORG`, `DEFINED_TERM_SET`, `MIT_LICENSE`, `STATS_URL`

- [ ] **Step 1: Write the failing test** (`test_facts.py`)

```python
"""Stdlib smoke test for app.facts.build_jsonld and _fact_from_source.

Run with: python test_facts.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import json
import sys

from app.facts import build_jsonld, _fact_from_source

DATASET_META = {
    "title": "goodbot-badbot",
    "entity": "goodbot-badbot",
    "entity_type": "Dataset",
    "segment": "AI crawler robots.txt compliance measurement",
    "summary": "A public experiment measuring robots.txt compliance.",
    "canonical": "https://goodbot-badbot.com/facts/goodbot-badbot",
    "date_modified": "2026-07-02",
}
TERM_META = {
    "title": "robots.txt compliance",
    "entity": "robots.txt compliance",
    "entity_type": "DefinedTerm",
    "summary": "How far a crawler obeys robots.txt Disallow rules.",
    "canonical": "https://goodbot-badbot.com/facts/robots-txt-compliance",
    "date_modified": "2026-07-02",
}


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures += 1

    ds = build_jsonld(DATASET_META)
    check("dataset @type", ds["@type"] == "Dataset")
    check("dataset @context", ds["@context"] == "https://schema.org")
    check("dataset name", ds["name"] == "goodbot-badbot")
    check("dataset description = summary", ds["description"] == DATASET_META["summary"])
    check("dataset url = canonical", ds["url"] == DATASET_META["canonical"])
    check("dataset dateModified", ds["dateModified"] == "2026-07-02")
    check("dataset creator name", ds["creator"]["name"] == "dkd Internet Service GmbH")
    check("dataset creator url", ds["creator"]["url"] == "https://www.dkd.de")
    check("dataset free", ds["isAccessibleForFree"] is True)
    check("dataset license MIT", "MIT" in ds["license"])
    check("dataset distribution url",
          ds["distribution"]["contentUrl"] == "https://goodbot-badbot.com/api/stats")
    check("dataset distribution format",
          ds["distribution"]["encodingFormat"] == "application/json")

    dt = build_jsonld(TERM_META)
    check("term @type", dt["@type"] == "DefinedTerm")
    check("term inDefinedTermSet",
          dt["inDefinedTermSet"] == "https://goodbot-badbot.com/facts")
    check("term has no distribution", "distribution" not in dt)

    fallback = build_jsonld({"title": "x", "entity_type": "Nonsense"})
    check("unknown type falls back to Thing", fallback["@type"] == "Thing")

    # JSON-LD must serialise to valid JSON.
    check("dataset json valid", json.loads(json.dumps(ds))["@type"] == "Dataset")

    # _fact_from_source needs markdown-it-py; skip gracefully if absent.
    try:
        import markdown_it  # noqa: F401
        raw = (
            "---\ntitle: goodbot-badbot\nentity: goodbot-badbot\n"
            "entity_type: Dataset\nsegment: seg\nsummary: A summary.\n"
            "canonical: https://goodbot-badbot.com/facts/goodbot-badbot\n"
            "date_modified: 2026-07-02\n---\n"
            "## goodbot-badbot is\n\ngoodbot-badbot is a test.\n"
        )
        fact = _fact_from_source(raw, "goodbot-badbot")
        check("fact slug", fact.slug == "goodbot-badbot")
        check("fact entity_type", fact.entity_type == "Dataset")
        check("fact html rendered", "<h2>" in fact.html)
        check("fact md is raw source", fact.md == raw)
        check("fact jsonld is a string", isinstance(fact.jsonld, str))
        check("fact jsonld parses", json.loads(fact.jsonld)["@type"] == "Dataset")

        missing_type = _fact_from_source("---\ntitle: x\n---\nbody", "x")
        check("missing entity_type -> None", missing_type is None)
    except ImportError:
        print("SKIP _fact_from_source tests (markdown-it-py not installed)")

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python test_facts.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.facts'`

- [ ] **Step 3: Write minimal implementation** (`app/facts.py`)

```python
"""Grounding pages: factual, machine-readable entity-definition pages.

Each page is content/facts/<slug>.md with frontmatter carrying the machine
fields (entity, entity_type, segment, summary, canonical, date_modified). The
Markdown body carries the editorial grounding discipline (H2 headings prefixed
with the entity name, factual tone, volatile facts linked to /api/stats rather
than hard-coded). schema.org JSON-LD is derived deterministically from the
frontmatter so the visible text and the structured facts never diverge.

Mirrors app/blog.py: posts/facts are parsed once on first access into an
in-memory registry. parse_frontmatter is reused from app.blog.
"""

from __future__ import annotations

import html as _html
import json
from dataclasses import dataclass
from pathlib import Path

from app.blog import parse_frontmatter

_CONTENT_DIR = Path(__file__).parent.parent / "content" / "facts"
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

SITE = "https://goodbot-badbot.com"
STATS_URL = f"{SITE}/api/stats"
DEFINED_TERM_SET = f"{SITE}/facts"
MIT_LICENSE = "https://opensource.org/licenses/MIT"
ORG = {
    "@type": "Organization",
    "name": "dkd Internet Service GmbH",
    "url": "https://www.dkd.de",
}


@dataclass(frozen=True)
class Fact:
    slug: str
    title: str
    entity: str
    entity_type: str
    segment: str
    summary: str
    canonical: str
    date_modified: str
    html: str    # rendered body
    md: str      # raw source (full file, incl. frontmatter)
    jsonld: str  # serialised schema.org JSON-LD


def build_jsonld(meta: dict) -> dict:
    """Derive a schema.org node from a fact's frontmatter.

    Dataset for the experiment (links its distribution to /api/stats),
    DefinedTerm for a measured concept. Unknown types fall back to a bare
    Thing rather than raising, so a typo in content never breaks the render.
    """
    entity_type = (meta.get("entity_type") or "").strip()
    name = meta.get("entity") or meta.get("title", "")
    description = meta.get("summary", "")
    url = meta.get("canonical", "")
    if entity_type == "Dataset":
        return {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": name,
            "description": description,
            "url": url,
            "dateModified": meta.get("date_modified", ""),
            "creator": ORG,
            "isAccessibleForFree": True,
            "license": MIT_LICENSE,
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": STATS_URL,
            },
        }
    if entity_type == "DefinedTerm":
        return {
            "@context": "https://schema.org",
            "@type": "DefinedTerm",
            "name": name,
            "description": description,
            "url": url,
            "inDefinedTermSet": DEFINED_TERM_SET,
        }
    return {
        "@context": "https://schema.org",
        "@type": "Thing",
        "name": name,
        "description": description,
        "url": url,
    }


_md = None


def _renderer():
    global _md
    if _md is None:
        from markdown_it import MarkdownIt
        _md = MarkdownIt("commonmark")
    return _md


def _fact_from_source(raw: str, slug: str) -> Fact | None:
    """Build a Fact from raw file text. Returns None if title/entity_type
    are missing (a malformed page is skipped rather than crashing the set)."""
    meta, body = parse_frontmatter(raw)
    title = meta.get("title")
    entity_type = meta.get("entity_type")
    if not title or not entity_type:
        return None
    return Fact(
        slug=slug,
        title=title,
        entity=meta.get("entity", title),
        entity_type=entity_type,
        segment=meta.get("segment", ""),
        summary=meta.get("summary", ""),
        canonical=meta.get("canonical", f"{SITE}/facts/{slug}"),
        date_modified=meta.get("date_modified", ""),
        html=_renderer().render(body),
        md=raw,
        jsonld=json.dumps(build_jsonld(meta), ensure_ascii=False, indent=2),
    )


def _load_fact(path: Path) -> Fact | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _fact_from_source(raw, path.stem)


def _load_all() -> dict[str, Fact]:
    if not _CONTENT_DIR.is_dir():
        return {}
    facts: dict[str, Fact] = {}
    for path in sorted(_CONTENT_DIR.glob("*.md")):
        fact = _load_fact(path)
        if fact:
            facts[fact.slug] = fact
    return facts


_FACTS: dict[str, Fact] | None = None


def _registry() -> dict[str, Fact]:
    global _FACTS
    if _FACTS is None:
        _FACTS = _load_all()
    return _FACTS


def list_facts() -> list[Fact]:
    """All grounding pages, ordered by title for a stable index."""
    return sorted(_registry().values(), key=lambda f: f.title)


def get_fact(slug: str) -> Fact | None:
    return _registry().get(slug)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python test_facts.py`
Expected: PASS — `0 failures` (the `_fact_from_source` block runs if markdown-it-py is installed, otherwise prints `SKIP`).

- [ ] **Step 5: Commit**

```bash
git add app/facts.py test_facts.py
git commit -m "feat(facts): grounding-page loader and schema.org JSON-LD builder"
```

---

### Task 2: HTML/Markdown renderers + `__HEAD_EXTRA__` head-injection seam

**Files:**
- Modify: `templates/blog_base.html` (add `__HEAD_EXTRA__` placeholder before `</head>`; add `/facts` footer link)
- Modify: `app/blog.py:130-136` (`_page` gains `head_extra` param, replaces the new token with `""`)
- Modify: `app/facts.py` (add renderers)
- Modify: `test_facts.py` (add index/fact markdown render checks)

**Interfaces:**
- Consumes: `Fact`, `list_facts()` from Task 1.
- Produces:
  - `render_index_html() -> str`, `render_index_markdown() -> str`
  - `render_fact_html(fact: Fact) -> str`, `render_fact_markdown(fact: Fact) -> str`

- [ ] **Step 1: Add the head-injection token to the shared shell**

In `templates/blog_base.html`, insert a placeholder on its own line immediately before `</head>` (line 17):

```html
__HEAD_EXTRA__
</head>
```

And add a grounding link to the footer (line 42), between `blog` and `source`:

```html
<footer>
  <span>goodbot-badbot.com — personal experiment by Olivier Dobberkau · <a href="/blog">blog</a> · <a href="/facts">facts</a> · <a href="https://github.com/dkd-dobberkau/goodbot-badbot" target="_blank" rel="noopener noreferrer">source on GitHub</a></span>
</footer>
```

- [ ] **Step 2: Update `blog._page` to consume the new token** (`app/blog.py:130-136`)

Replace the existing `_page` function with:

```python
def _page(title: str, content_html: str, head_extra: str = "") -> str:
    # Replace content first; titles/content never contain the literal tokens.
    return (
        _base_template()
        .replace("__CONTENT__", content_html)
        .replace("__TITLE__", _html.escape(title))
        .replace("__HEAD_EXTRA__", head_extra)
    )
```

- [ ] **Step 3: Write the failing test** — append inside `main()` in `test_facts.py`, before the final `print(f"\n{failures} failures")`:

```python
    try:
        import markdown_it  # noqa: F401
        from app.facts import (
            render_index_html, render_index_markdown,
            render_fact_html, render_fact_markdown,
        )
        raw = (
            "---\ntitle: goodbot-badbot\nentity: goodbot-badbot\n"
            "entity_type: Dataset\nsegment: seg\nsummary: A summary.\n"
            "canonical: https://goodbot-badbot.com/facts/goodbot-badbot\n"
            "date_modified: 2026-07-02\n---\n## goodbot-badbot is\n\nBody.\n"
        )
        fact = _fact_from_source(raw, "goodbot-badbot")

        fh = render_fact_html(fact)
        check("fact html has jsonld script", 'application/ld+json' in fh)
        check("fact html has back link", 'href="/facts"' in fh)
        check("fact html has title", "goodbot-badbot" in fh)
        check("fact html injected via head token", "__HEAD_EXTRA__" not in fh)

        fm = render_fact_markdown(fact)
        check("fact markdown is raw source", fm == raw)

        im = render_index_markdown()
        check("index markdown heading", im.startswith("# Grounding pages"))

        ih = render_index_html()
        check("index html no leftover token", "__CONTENT__" not in ih)
    except ImportError:
        print("SKIP renderer tests (markdown-it-py not installed)")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python test_facts.py`
Expected: FAIL with `ImportError: cannot import name 'render_index_html'`

- [ ] **Step 5: Add the renderers** (append to `app/facts.py`)

```python
def _base_template() -> str:
    return (_TEMPLATE_DIR / "blog_base.html").read_text(encoding="utf-8")


def _page(title: str, content_html: str, head_extra: str = "") -> str:
    return (
        _base_template()
        .replace("__CONTENT__", content_html)
        .replace("__TITLE__", _html.escape(title))
        .replace("__HEAD_EXTRA__", head_extra)
    )


def _jsonld_head(fact: Fact) -> str:
    # CSP allows inline ld+json (script-src 'unsafe-inline'). The payload is
    # our own serialised dict, not user input, so no escaping is needed.
    return f'<script type="application/ld+json">\n{fact.jsonld}\n</script>'


def render_fact_html(fact: Fact) -> str:
    content = (
        '<main class="article">'
        '<a class="back-link" href="/facts">← all grounding pages</a>'
        f'<h1 class="article-title">{_html.escape(fact.title)}</h1>'
        f'<div class="article-date">Last updated {_html.escape(fact.date_modified)}</div>'
        f"{fact.html}"
        "</main>"
    )
    return _page(fact.title, content, head_extra=_jsonld_head(fact))


def render_index_html() -> str:
    facts = list_facts()
    if not facts:
        items = '<p class="empty">No grounding pages yet.</p>'
    else:
        rows = "".join(
            f'<li class="post-link">'
            f'<a href="/facts/{_html.escape(f.slug)}">'
            f'<span class="post-title">{_html.escape(f.title)}</span></a>'
            f'<div class="post-meta">{_html.escape(f.entity_type)} · {_html.escape(f.segment)}</div>'
            f'<p class="post-summary">{_html.escape(f.summary)}</p>'
            f"</li>"
            for f in facts
        )
        items = f'<ul class="post-list">{rows}</ul>'
    intro = (
        '<p class="post-summary">Factual, machine-readable definitions of the '
        'entities this site is about — structured so AI systems can cite them '
        'without guessing. Reads are logged as a discovery signal.</p>'
    )
    content = (
        f'<main class="article"><h1 class="article-title">Grounding pages</h1>'
        f'{intro}{items}</main>'
    )
    return _page("Grounding pages", content)


def render_fact_markdown(fact: Fact) -> str:
    # Serve the raw source verbatim, same contract as the blog.
    return fact.md


def render_index_markdown() -> str:
    facts = list_facts()
    lines = ["# Grounding pages", ""]
    if not facts:
        lines.append("No grounding pages yet.")
    for f in facts:
        lines.append(f"- [{f.title}](/facts/{f.slug}) — {f.summary}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python test_facts.py`
Expected: PASS — `0 failures`.

- [ ] **Step 7: Verify the blog still renders (token change is backward-compatible)**

Run: `python test_blog.py`
Expected: PASS — `8/8 checks passed` (blog uses `_page` with the new default `head_extra=""`).

- [ ] **Step 8: Commit**

```bash
git add app/facts.py app/blog.py templates/blog_base.html test_facts.py
git commit -m "feat(facts): HTML/Markdown renderers with JSON-LD head injection"
```

---

### Task 3: Grounding-page content files

**Files:**
- Create: `content/facts/goodbot-badbot.md`
- Create: `content/facts/robots-txt-compliance.md`

**Interfaces:**
- Consumes: the frontmatter schema and `_fact_from_source` validation from Task 1 (requires `title` + `entity_type`).
- Produces: two loadable `Fact`s with slugs `goodbot-badbot` and `robots-txt-compliance`.

- [ ] **Step 1: Create `content/facts/goodbot-badbot.md`**

```markdown
---
title: goodbot-badbot
entity: goodbot-badbot
entity_type: Dataset
segment: AI crawler robots.txt compliance measurement
summary: A public experiment that measures whether AI crawlers respect a single robots.txt Disallow rule, publishing every violation live.
canonical: https://goodbot-badbot.com/facts/goodbot-badbot
date_modified: 2026-07-02
---

## goodbot-badbot is

goodbot-badbot is a public experiment, operated by dkd Internet Service GmbH,
that measures whether AI crawlers actually respect `robots.txt`. It runs at
<https://goodbot-badbot.com>. The site declares six honeypot paths as
`Disallow`; any request to one of them, by any user-agent, is logged as a
violation and shown on a public dashboard in real time.

## goodbot-badbot methodology

The entire site is open to all crawlers except six honeypot paths blocked by a
single global `User-agent: *` Disallow rule. A compliant crawler reads the
homepage and stops at that boundary; a non-compliant one continues into a
honeypot and is recorded. Because only one rule is under test, compliance can
be measured cleanly.

The honeypots come in two groups:

- **Linked** (`/do-not-crawl/`, `/training-data-forbidden/`, `/no-ai-allowed/`)
  are reachable via visible links on the homepage. A hit means the crawler
  followed a link and ignored the matching Disallow rule.
- **Unlinked** (`/private/`, `/honeypot/`, `/robots-test/`) are linked nowhere.
  The only way to find them is to read `/robots.txt` and use the Disallow list
  as a crawl seed (the "treasure map" anti-pattern) or to guess common paths.

## goodbot-badbot data and policy

Results are published as a live dashboard and a machine-readable JSON API. The
site's AI-usage policy is declared with Content Signals in `robots.txt`:
`search=yes, ai-input=yes, ai-train=no`.

- Live figures, updated continuously: <https://goodbot-badbot.com/api/stats>
- Dashboard: <https://goodbot-badbot.com/>
- Crawl rules: <https://goodbot-badbot.com/robots.txt>

Current violation counts are intentionally not restated on this page; read them
live from `/api/stats` rather than from a figure that would go stale here.

## goodbot-badbot operator

The experiment is operated by dkd Internet Service GmbH
(<https://www.dkd.de>). The source code is MIT-licensed and published at
<https://github.com/dkd-dobberkau/goodbot-badbot>.

## goodbot-badbot privacy

Client IP addresses are SHA-256 hashed and truncated to the first 16 hex
characters before storage. The raw IP is never written to disk.

## goodbot-badbot frequently asked

**Does goodbot-badbot block AI crawlers?** No. The site is deliberately open;
only six honeypot paths are disallowed, so that compliance with one rule can be
measured cleanly.

**Is reading robots.txt or llms.txt a violation?** No. Those reads are the
positive signal — an agent doing discovery. Only a request to a disallowed
honeypot path is a violation.

**Is goodbot-badbot itself an AI agent?** No. It is an observer of agents. It
exposes no callable agent, tool, or API endpoint to act on.
```

- [ ] **Step 2: Create `content/facts/robots-txt-compliance.md`**

```markdown
---
title: robots.txt compliance
entity: robots.txt compliance
entity_type: DefinedTerm
segment: web crawling standards and AI governance
summary: The degree to which an automated crawler obeys the Disallow rules a site publishes in its /robots.txt file.
canonical: https://goodbot-badbot.com/facts/robots-txt-compliance
date_modified: 2026-07-02
---

## robots.txt compliance is

robots.txt compliance is the degree to which an automated crawler obeys the
rules a website publishes in its `/robots.txt` file. The file format and
fetching behaviour are specified by RFC 9309, the Robots Exclusion Protocol.
`robots.txt` is advisory: it is enforced by convention and reputation, not by
access control, so compliance is a behavioural property of each crawler, not a
guarantee the server can impose.

## robots.txt compliance and Disallow

The core directive is `Disallow`, which names a path prefix a crawler should
not fetch, scoped to a `User-agent` group. A crawler is compliant with a given
rule when it refrains from requesting any path the rule disallows. A single
global `User-agent: *` rule applies to every crawler that does not match a more
specific group.

## robots.txt compliance measurement

Compliance can be measured by publishing paths as `Disallow` and observing
whether crawlers request them anyway. Two signal types are distinguishable:

- A hit on a **linked** disallowed path shows the crawler followed a link and
  ignored the Disallow rule.
- A hit on an **unlinked** disallowed path — discoverable only through
  `robots.txt` itself — shows the crawler used the Disallow list as a crawl
  seed, the "treasure map" anti-pattern, where the exclusion file is mined for
  URLs instead of being honoured.

## robots.txt compliance and AI crawlers

AI crawlers extend the same protocol with usage-specific tokens. Content
Signals such as `ai-train`, `ai-input`, and `search` let a site express not
just whether a path may be fetched but how the retrieved content may be used —
for model training, for answer grounding, or for search indexing. Compliance
then covers both the fetch boundary and the declared usage policy.

## robots.txt compliance — see also

This concept is measured live at
<https://goodbot-badbot.com/facts/goodbot-badbot>, which records real crawler
behaviour against a fixed set of Disallow rules.
```

- [ ] **Step 3: Verify both files load as valid Facts**

Run:
```bash
python -c "from app import facts; fs = facts.list_facts(); print([(f.slug, f.entity_type) for f in fs]); assert {f.slug for f in fs} == {'goodbot-badbot','robots-txt-compliance'}; import json; [json.loads(f.jsonld) for f in fs]; print('OK')"
```
Expected: prints the two `(slug, entity_type)` pairs and `OK` (JSON-LD parses for both).

- [ ] **Step 4: Commit**

```bash
git add content/facts/goodbot-badbot.md content/facts/robots-txt-compliance.md
git commit -m "content(facts): grounding pages for the experiment and robots.txt compliance"
```

---

### Task 4: Routes, discovery logging, and rate limit in `app/main.py`

**Files:**
- Modify: `app/main.py:29` (import), `:40-56` (rate-limit rule), and add route handlers after the blog routes (`:726`)

**Interfaces:**
- Consumes: `facts.render_index_html/markdown`, `facts.render_fact_html/markdown`, `facts.get_fact` from Tasks 1-2; existing `_should_log_meta_visit`, `log_visit`, `_wants_markdown`, `request.state.signature_status`.
- Produces: `GET /facts` and `GET /facts/{slug}` endpoints; every read logged with `is_honeypot=False` under the exact requested path.

- [ ] **Step 1: Extend the module import** (`app/main.py:29`)

Change:
```python
from app import blog
```
to:
```python
from app import blog, facts
```

- [ ] **Step 2: Add the rate-limit rule** (`app/main.py`, inside `RATE_LIMIT_RULES`, after the `("/blog", 60),` line)

```python
    ("/blog",                   60),
    ("/facts",                  60),
    ("/AGENTS.md",              60),
```

- [ ] **Step 3: Add the route handlers** (append after the `blog_post` handler, `app/main.py:726`)

```python
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
```

- [ ] **Step 4: Verify locally with the app running**

Run:
```bash
docker compose up -d --build
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/facts
curl -s http://localhost:8000/facts/goodbot-badbot | grep -c 'application/ld+json'
curl -s -H "Accept: text/markdown" http://localhost:8000/facts/goodbot-badbot | head -1
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/facts/does-not-exist
```
Expected: `200`; `1` (JSON-LD present in HTML); first markdown line `---`; `404` for the unknown slug.

- [ ] **Step 5: Confirm the read was logged as a non-violation discovery signal**

Run:
```bash
curl -s http://localhost:8000/api/stats | python -c "import sys,json; d=json.load(sys.stdin); print('total_discovery_reads', d['total_discovery_reads'])"
```
Expected: `total_discovery_reads` is a non-negative integer and no new row appears in `recent_violations` (the `/facts` read is not a honeypot hit). Note: the dashboard `facts` column arrives in Task 6; this step only confirms the read logged without erroring.

- [ ] **Step 6: Commit**

```bash
git add app/main.py
git commit -m "feat(facts): serve /facts + /facts/{slug} with content negotiation and read logging"
```

---

### Task 5: Wire grounding pages into sitemap, llms.txt, Link header, and dashboard footer

**Files:**
- Modify: `app/main.py:527-543` (`_build_sitemap`), `:590-631` (`LLMS_TXT`), `:890-894` (`HOMEPAGE_LINK_HEADER`)
- Modify: `templates/index.html:686` (footer link)

**Interfaces:**
- Consumes: `facts.list_facts()` from Task 1; each `Fact.slug` and `Fact.date_modified`.
- Produces: grounding pages present in `sitemap.xml`, `llms.txt`, the homepage `Link` header, and the dashboard footer.

- [ ] **Step 1: Add grounding pages to the sitemap** (`app/main.py`, inside `_build_sitemap`, after the blog-post loop, before `body = "\n".join(urls)`)

```python
    urls.append(
        f"  <url>\n    <loc>{SITE_BASE_URL}/facts</loc>\n    <lastmod>{SITEMAP_LASTMOD}</lastmod>\n  </url>"
    )
    for fact in facts.list_facts():
        lastmod = fact.date_modified or SITEMAP_LASTMOD
        urls.append(
            f"  <url>\n    <loc>{SITE_BASE_URL}/facts/{fact.slug}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>"
        )
    body = "\n".join(urls)
```

- [ ] **Step 2: Add a Grounding-pages section to `llms.txt`** (`app/main.py`, inside the `LLMS_TXT` string, insert after the `## Live data` block and before `## Honeypot paths`)

```
## Grounding pages

Factual, machine-readable entity definitions for AI systems to cite:

- [goodbot-badbot](https://goodbot-badbot.com/facts/goodbot-badbot): the experiment as a dataset
- [robots.txt compliance](https://goodbot-badbot.com/facts/robots-txt-compliance): the measured concept

```

- [ ] **Step 3: Add the grounding index to the homepage Link header** (`app/main.py:890-894`)

Replace `HOMEPAGE_LINK_HEADER` with:
```python
HOMEPAGE_LINK_HEADER = ", ".join((
    '</api/stats>; rel="service-desc"; type="application/json"',
    '</llms.txt>; rel="service-doc"; type="text/markdown"',
    '</facts>; rel="describedby"; type="text/html"',
    '</sitemap.xml>; rel="sitemap"',
))
```

- [ ] **Step 4: Add the footer link on the dashboard** (`templates/index.html:686`)

```html
  <span>goodbot-badbot.com — personal experiment by Olivier Dobberkau · <a href="/blog">blog</a> · <a href="/facts">facts</a> · <a href="https://github.com/dkd-dobberkau/goodbot-badbot" target="_blank" rel="noopener noreferrer">source on GitHub</a></span>
```

- [ ] **Step 5: Verify the wiring with the app running**

Run:
```bash
docker compose up -d --build
sleep 5
curl -s http://localhost:8000/sitemap.xml | grep -c '/facts'
curl -s http://localhost:8000/llms.txt | grep -c 'Grounding pages'
curl -s -D - -o /dev/null http://localhost:8000/ | grep -i '^link:' | grep -c '/facts'
```
Expected: `3` (`/facts` index + two pages in sitemap); `1` (llms.txt section present); `1` (Link header advertises `/facts`).

- [ ] **Step 6: Commit**

```bash
git add app/main.py templates/index.html
git commit -m "feat(facts): surface grounding pages in sitemap, llms.txt, Link header, footer"
```

---

### Task 6: Dashboard measurement — `facts_reads` column

**Files:**
- Modify: `app/main.py:800-822` (`_compute_stats` discovery query + total)
- Modify: `templates/index.html:657` (panel title), `:668-682` (table header), `:790-808` (row rendering)

**Interfaces:**
- Consumes: the `/facts` reads logged in Task 4; `DISCOVERY_PATHS`, `AGENTS_MD_PATHS` from `app/main.py`.
- Produces: `discovery_reads[].facts_reads` in `/api/stats`; a "grounding" column in the dashboard's Discovery Reads table.

- [ ] **Step 1: Add `facts_reads` to the discovery query** (`app/main.py`, replace the `cur.execute` for the discovery query, ~`:800-815`)

```python
            await cur.execute(
                f"""
                SELECT bot_name, operator,
                       CAST(SUM(path = '/llms.txt') AS UNSIGNED) AS llms_reads,
                       CAST(SUM(path IN ({agents_ph})) AS UNSIGNED) AS agents_reads,
                       CAST(SUM(path = '/facts' OR path LIKE '/facts/%%') AS UNSIGNED) AS facts_reads,
                       COUNT(*) AS total_reads,
                       MAX(ts) AS last_seen
                FROM visits
                WHERE (path IN ({discovery_ph}) OR path = '/facts' OR path LIKE '/facts/%%')
                  AND bot_name IS NOT NULL
                GROUP BY bot_name, operator
                ORDER BY total_reads DESC, last_seen DESC
                LIMIT 50
                """,
                (*AGENTS_MD_PATHS, *DISCOVERY_PATHS),
            )
            discovery = await cur.fetchall()
```

> **Why `%%`:** aiomysql/PyMySQL performs `query % args` because args are
> passed, so a literal `%` in `LIKE '/facts/%'` must be doubled to `%%` or the
> execute raises a formatting error.

- [ ] **Step 2: Include facts reads in the discovery total** (`app/main.py`, replace the `total_discovery` query ~`:818-822`)

```python
            await cur.execute(
                f"SELECT COUNT(*) AS c FROM visits "
                f"WHERE path IN ({discovery_ph}) OR path = '/facts' OR path LIKE '/facts/%%'",
                DISCOVERY_PATHS,
            )
            total_discovery = (await cur.fetchone())["c"]
```

- [ ] **Step 3: Update the panel title and table header** (`templates/index.html`)

Line 657 — panel title:
```html
  <div class="panel-title">Discovery Reads — who fetches llms.txt, agents.md &amp; grounding pages</div>
```

Lines 668-682 — table header (add a `grounding` column and bump the loading colspan to 7):
```html
  <table>
    <thead>
      <tr>
        <th>Bot</th>
        <th>Operator</th>
        <th style="text-align:right">llms.txt</th>
        <th style="text-align:right">agents.md</th>
        <th style="text-align:right">grounding</th>
        <th style="text-align:right">Total</th>
        <th style="text-align:right">Last read</th>
      </tr>
    </thead>
    <tbody id="discoveryTable">
      <tr><td colspan="7" class="empty-state">Loading…</td></tr>
    </tbody>
  </table>
```

- [ ] **Step 4: Render the `facts` cell** (`templates/index.html:790-808`)

Replace the discovery-table rendering block with:
```javascript
  if (discovery.length === 0) {
    discTable.innerHTML = `<tr><td colspan="7" class="empty-state">No discovery reads logged yet.</td></tr>`;
  } else {
    discTable.innerHTML = discovery.map(row => {
      const llms = Number(row.llms_reads) || 0;
      const agents = Number(row.agents_reads) || 0;
      const facts = Number(row.facts_reads) || 0;
      const total = Number(row.total_reads) || 0;
      const cell = (n) => `<td class="read-count ${n > 0 ? 'nonzero' : 'zero'}">${n > 0 ? n : '—'}</td>`;
      const lastRead = row.last_seen
        ? new Date(row.last_seen + 'Z').toLocaleString('en-GB')
        : '—';
      return `<tr>
        <td><span class="bot-name">${esc(row.bot_name)}</span></td>
        <td><span class="operator">${esc(row.operator)}</span></td>
        ${cell(llms)}
        ${cell(agents)}
        ${cell(facts)}
        <td class="read-count nonzero">${total}</td>
        <td class="last-seen">${esc(lastRead)}</td>
      </tr>`;
    }).join('');
  }
```

- [ ] **Step 5: Verify the column populates end-to-end**

Run:
```bash
docker compose up -d --build
sleep 5
curl -s -A "GPTBot" http://localhost:8000/facts/goodbot-badbot > /dev/null
curl -s http://localhost:8000/api/stats | python -c "import sys,json; d=json.load(sys.stdin); rows=d['discovery_reads']; print('has facts_reads key:', all('facts_reads' in r for r in rows) if rows else 'no rows yet'); print(rows)"
```
Expected: every discovery row carries a `facts_reads` key; the GPTBot row shows `facts_reads >= 1`. (The dedup TTL means a repeat read within 10 min is not double-counted — use a fresh path or wait if re-testing.)

- [ ] **Step 6: Open the dashboard and confirm the column renders**

Run: open <http://localhost:8000/> and check the "Discovery Reads" table shows a `grounding` column with the GPTBot count.
Expected: seven columns, `grounding` populated for the bot you curled as.

- [ ] **Step 7: Commit**

```bash
git add app/main.py templates/index.html
git commit -m "feat(facts): count grounding-page reads in the Discovery Reads dashboard"
```

---

### Task 7: Explanatory blog post

**Files:**
- Create: `content/blog/grounding-pages.md`

**Interfaces:**
- Consumes: the blog loader from `app/blog.py` (frontmatter needs `title`; `date`/`summary` optional but provided).
- Produces: a post at `/blog/grounding-pages`, listed on `/blog` and in the sitemap (via the existing blog wiring).

- [ ] **Step 1: Create `content/blog/grounding-pages.md`**

```markdown
---
title: Grounding pages — something true to cite
date: 2026-07-02
summary: We published two grounding pages — factual, machine-readable entity definitions — and made every read a measurement signal. Here is what they are, and why they are not compliance theatre.
---

# Grounding pages — something true to cite

This site already speaks several dialects of "please read me correctly" to AI
systems: a `robots.txt` with Content Signals, an `llms.txt` summary, an
`agents.md` probe surface, and Web Bot Auth keys. This week it learned one
more: **grounding pages**.

## What a grounding page actually is

It helps to separate three things that get blurred together:

- **llms.txt** decides *what* goes into an AI's retrieval pool. It is a
  declaration of which pages are worth reading — a table of contents for
  machines.
- **Grounding** is the runtime step where a model, answering a question, pulls
  documents from that pool and reasons over them instead of over its training
  memory. It is a live inference-time operation.
- **A grounding page** is a citable factual source *inside* that pool: a real
  HTML page, with its own URL, that defines one entity as plainly and
  verifiably as possible. It states facts and leaves the conclusion to the
  model — the opposite of an "instructions for AI" page that tries to script
  what the model should say.

The idea travels under the "Grounding Page Standard" banner. Worth being honest
about its status: that is a generative-engine-optimisation discipline, **not**
an IETF or W3C standard — the same footing as llms.txt. What is useful about it
is the editorial rule set: name the entity in your headings, keep the tone
factual rather than persuasive, and never hard-code a number that will rot —
link to the live source instead.

## Why this site has two

We published exactly two, because we have exactly two things worth grounding:

- [**goodbot-badbot**](/facts/goodbot-badbot) — the experiment itself,
  described as a `Dataset` whose distribution is the live `/api/stats` feed.
- [**robots.txt compliance**](/facts/robots-txt-compliance) — the concept we
  measure, described as a `DefinedTerm`.

Each page carries schema.org JSON-LD generated straight from its frontmatter,
so the words a human reads and the structured facts a machine extracts can
never drift apart.

## Not compliance theatre

Regular readers know this project's allergy to publishing signals it cannot
back up. We do not ship a DNS-AID record or an agent manifest, because the site
has no agent endpoint to advertise — doing so would be theatre.

Grounding pages pass that test for two reasons. First, they describe things
that genuinely exist: a running experiment and a real, measurable concept.
Second — and this is the part that fits the project — they are themselves a
**measurement surface**. Every read of a grounding page is logged exactly like
a read of `llms.txt` or `agents.md`: a positive discovery signal, the opposite
of a honeypot violation. You can watch which crawlers fetch them in the
[Discovery Reads](/) table on the dashboard.

So the site now offers agents something true to cite — and, true to form,
writes down who takes it up on the offer.
```

- [ ] **Step 2: Verify the post loads and is served**

Run:
```bash
docker compose up -d --build
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/blog/grounding-pages
curl -s http://localhost:8000/blog | grep -c 'grounding-pages'
```
Expected: `200`; `1` (post listed on the blog index).

- [ ] **Step 3: Commit**

```bash
git add content/blog/grounding-pages.md
git commit -m "content(blog): post explaining grounding pages"
```

---

## Final verification (after all tasks)

- [ ] **Run the unit tests**

```bash
python test_facts.py && python test_blog.py
```
Expected: both report `0 failures` / `8/8 checks passed`.

- [ ] **Full local smoke test**

```bash
docker compose up -d --build
sleep 5
for url in /facts /facts/goodbot-badbot /facts/robots-txt-compliance /blog/grounding-pages; do
  printf "%s -> " "$url"; curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000$url"
done
curl -s http://localhost:8000/facts/robots-txt-compliance | grep -c 'DefinedTerm'
curl -s http://localhost:8000/sitemap.xml | grep -c '/facts'
```
Expected: four `200`s; `1` (DefinedTerm JSON-LD present); `3` (sitemap entries).

- [ ] **Validate JSON-LD** (optional, if network available): paste
  `https://goodbot-badbot.com/facts/goodbot-badbot` into the
  [Schema Markup Validator](https://validator.schema.org/) after deploy and
  confirm the `Dataset` node parses with no errors.

## Deploy

Not part of this plan. When ready, follow the existing `./deploy.sh` workflow
(builds the immutable image — `content/`, `app/`, `templates/` are already
COPYd in the Dockerfile, so no Dockerfile change is needed).
