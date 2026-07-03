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
            "creator": dict(ORG),
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
        # CommonMark preset, but with raw HTML pass-through disabled so any
        # stray HTML in a body is escaped rather than rendered (bodies are prose).
        _md = MarkdownIt("commonmark", {"html": False})
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
    # CSP allows inline ld+json. The payload is our own serialised dict, but
    # json.dumps does not escape "</", so defuse a "</script>" breakout should
    # a frontmatter field ever contain one ("\/" is a valid JSON escape for "/").
    safe = fact.jsonld.replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{safe}\n</script>'


def render_fact_html(fact: Fact) -> str:
    content = (
        '<main class="article" id="main">'
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
        f'<main class="article" id="main"><h1 class="article-title">Grounding pages</h1>'
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
