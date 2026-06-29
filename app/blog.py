"""Mini-blog: load Markdown posts from content/blog/ and render them.

Each post is content/blog/<slug>.md with an optional leading frontmatter
block delimited by '---' lines:

    ---
    title: Some title
    date: 2026-06-29
    summary: One-line description.
    ---
    # Body in Markdown

The filename stem is the slug. Posts are parsed once on first access (content
only changes when a new image ships) into an in-memory registry.

The markdown-it import and the registry load are deliberately lazy so this
module imports with stdlib only — parse_frontmatter stays unit-testable
without the dependency installed.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from pathlib import Path

_CONTENT_DIR = Path(__file__).parent.parent / "content" / "blog"
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


@dataclass(frozen=True)
class Post:
    slug: str
    title: str
    date: str
    summary: str
    html: str  # rendered body
    md: str    # raw source (full file, incl. frontmatter)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a post file into (frontmatter dict, body markdown).

    Frontmatter is an optional leading block delimited by lines that are
    exactly '---'. Keys are 'key: value'; the value keeps everything after the
    first colon. Without a leading fence the whole text is body, dict empty.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        key, sep, value = lines[i].partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    body = "\n".join(lines[body_start:]).lstrip("\n")
    return meta, body


_md = None


def _renderer():
    global _md
    if _md is None:
        from markdown_it import MarkdownIt
        # CommonMark preset leaves raw HTML in source escaped (safe default).
        _md = MarkdownIt("commonmark")
    return _md


def _load_post(path: Path) -> Post | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = parse_frontmatter(raw)
    title = meta.get("title")
    if not title:
        # Untitled post is malformed; skip it rather than crash the blog.
        return None
    return Post(
        slug=path.stem,
        title=title,
        date=meta.get("date", ""),
        summary=meta.get("summary", ""),
        html=_renderer().render(body),
        md=raw,
    )


def _load_all() -> dict[str, Post]:
    if not _CONTENT_DIR.is_dir():
        return {}
    posts: dict[str, Post] = {}
    for path in sorted(_CONTENT_DIR.glob("*.md")):
        post = _load_post(path)
        if post:
            posts[post.slug] = post
    return posts


_POSTS: dict[str, Post] | None = None


def _registry() -> dict[str, Post]:
    global _POSTS
    if _POSTS is None:
        _POSTS = _load_all()
    return _POSTS


def list_posts() -> list[Post]:
    """All posts, newest first (date is ISO YYYY-MM-DD, sorts lexically)."""
    return sorted(_registry().values(), key=lambda p: p.date, reverse=True)


def get_post(slug: str) -> Post | None:
    return _registry().get(slug)


def _base_template() -> str:
    return (_TEMPLATE_DIR / "blog_base.html").read_text(encoding="utf-8")


def _page(title: str, content_html: str) -> str:
    # Replace content first; titles/content never contain the literal tokens.
    return (
        _base_template()
        .replace("__CONTENT__", content_html)
        .replace("__TITLE__", _html.escape(title))
    )


def render_index_html() -> str:
    posts = list_posts()
    if not posts:
        items = '<p class="empty">No posts yet.</p>'
    else:
        rows = "".join(
            f'<li class="post-link">'
            f'<a href="/blog/{_html.escape(p.slug)}">'
            f'<span class="post-title">{_html.escape(p.title)}</span></a>'
            f'<div class="post-meta">{_html.escape(p.date)}</div>'
            f'<p class="post-summary">{_html.escape(p.summary)}</p>'
            f"</li>"
            for p in posts
        )
        items = f'<ul class="post-list">{rows}</ul>'
    content = f'<main class="article"><h1 class="article-title">Writing</h1>{items}</main>'
    return _page("Writing", content)


def render_post_html(post: Post) -> str:
    content = (
        '<main class="article">'
        '<a class="back-link" href="/blog">← all posts</a>'
        f'<h1 class="article-title">{_html.escape(post.title)}</h1>'
        f'<div class="article-date">{_html.escape(post.date)}</div>'
        f"{post.html}"
        "</main>"
    )
    return _page(post.title, content)


def render_index_markdown() -> str:
    posts = list_posts()
    lines = ["# Writing", ""]
    if not posts:
        lines.append("No posts yet.")
    for p in posts:
        lines.append(f"- [{p.title}](/blog/{p.slug}) — {p.summary} ({p.date})")
    return "\n".join(lines) + "\n"
