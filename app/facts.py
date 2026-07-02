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
