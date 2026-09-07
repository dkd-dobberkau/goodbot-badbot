"""Legal pages: Impressum (§ 5 DDG) and Datenschutzerklärung (Art. 13 GDPR).

Each page is content/legal/<slug>.md with frontmatter carrying the title. The
Markdown body is the legal text itself, so the wording can be reviewed and
amended as prose without touching Python.

Mirrors app/facts.py, minus the machine-readable layer: these pages carry no
JSON-LD and are deliberately not logged as visits. They are read by people
looking for a postal address, not by agents being measured.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from pathlib import Path

from app.blog import parse_frontmatter

_CONTENT_DIR = Path(__file__).parent.parent / "content" / "legal"
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


@dataclass(frozen=True)
class LegalPage:
    slug: str
    title: str
    html: str  # rendered body
    md: str    # raw source (full file, incl. frontmatter)


_registry_cache: dict[str, LegalPage] | None = None


def _load_page(path: Path) -> LegalPage | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = parse_frontmatter(raw)
    title = meta.get("title")
    if not title:
        # Untitled page is malformed; skip it rather than crash the site.
        return None
    from app.blog import _renderer

    return LegalPage(slug=path.stem, title=title, html=_renderer().render(body), md=raw)


def _registry() -> dict[str, LegalPage]:
    global _registry_cache
    if _registry_cache is None:
        pages = {}
        if _CONTENT_DIR.is_dir():
            for path in sorted(_CONTENT_DIR.glob("*.md")):
                page = _load_page(path)
                if page is not None:
                    pages[page.slug] = page
        _registry_cache = pages
    return _registry_cache


def get_page(slug: str) -> LegalPage | None:
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


def render_page_html(page: LegalPage) -> str:
    content = (
        '<main class="article" id="main">'
        '<a class="back-link" href="/">← dashboard</a>'
        f'<h1 class="article-title">{_html.escape(page.title)}</h1>'
        f"{page.html}"
        "</main>"
    )
    # noindex: these pages must be reachable, but they are not what the site
    # is about and should not compete with it in search results.
    return _page(page.title, content, head_extra='<meta name="robots" content="noindex, follow">')
