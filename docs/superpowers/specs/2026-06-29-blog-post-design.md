# Design: Mini-blog for goodbot-badbot

**Date:** 2026-06-29
**Status:** Approved (design); spec under review

## Goal

Add a small, extensible blog to goodbot-badbot.com and publish a first
English post that explains the experiment's methodology and why it was built.
Later "findings / data" posts are an explicit future use of the same blog —
the design must make adding a post a one-file change.

## Scope

In scope:

- A blog index at `/blog` and per-post pages at `/blog/{slug}`.
- Content negotiation (`Accept: text/markdown`) on both, matching the site's
  existing behaviour on `/`.
- One first post: methodology explainer + "why I built this" narrative.
- Minimal discoverability wiring (sitemap, llms.txt, homepage footer link).

Out of scope (deferred):

- Findings/data posts (a later post, same machinery).
- Logging blog reads as visits (editorial content is not a measurement
  surface; revisit only if there's a concrete reason).
- Tags, pagination, RSS, comments, drafts.

## Architecture

A new isolated module rather than growing `app/main.py` (already ~800 lines).

### Files

- `content/blog/<slug>.md` — one Markdown file per post. Frontmatter block
  delimited by `---` lines with `title`, `date` (YYYY-MM-DD), `summary`.
  Body is CommonMark Markdown. The filename stem is the slug.
- `app/blog.py` — the blog subsystem:
  - Loads and parses every `content/blog/*.md` **once at import / startup**
    (content only changes when a new image ships — same semantic as
    `SITEMAP_LASTMOD`). No per-request file I/O.
  - A minimal frontmatter parser (split on the leading `---` fence, parse
    `key: value` lines). Avoids a YAML dependency for three trivial fields.
  - Renders the Markdown body to HTML with `markdown-it-py` (CommonMark,
    pure Python, HTML-in-source escaping left at the safe default).
  - Holds a registry `slug -> Post`, where `Post` carries `slug, title,
    date, summary, html (rendered body), md (raw source)`.
  - Exposes: `list_posts()` (sorted newest-first), `get_post(slug)`,
    and page-shell render helpers for index + single post that produce a
    full HTML document in the dashboard's visual style.
- `vendor/css/blog.css` — shared theme variables (light/dark), header/footer
  chrome, and article typography. Served through the existing `/vendor`
  StaticFiles mount. `templates/index.html` is **not** refactored to use it
  (kept untouched to minimise risk); minor variable duplication is accepted.
- `requirements.txt` — add `markdown-it-py`.

### Routes (in `app/main.py`, delegating to `app/blog.py`)

- `GET /blog`
  - Default: HTML index listing posts (title, date, summary, link), in the
    dashboard look, with the shared header/footer and theme toggle.
  - `Accept: text/markdown`: a Markdown list of posts (title + summary +
    relative link), `media_type=text/markdown; charset=utf-8`.
- `GET /blog/{slug}`
  - Default: rendered HTML article page (header/footer/theme toggle, article
    typography from `blog.css`).
  - `Accept: text/markdown`: the raw Markdown source of the post.
  - Unknown slug: `404` (plain text), not a server error.
- Rate limiting: add `/blog` (prefix) at 60/min to `RATE_LIMIT_RULES`,
  consistent with the other content/meta routes. The prefix rule covers
  `/blog` and `/blog/<slug>`.
- No `log_visit` call on blog routes (see Out of scope).

### Discoverability

- `sitemap.xml`: include `/blog` and every post URL (built from the registry),
  each with the post's `date` as `lastmod` where applicable.
- `llms.txt`: add a `## Writing` section linking to `/blog`.
- `templates/index.html`: add a single "blog" link in the footer (the only
  edit to that file).

## Data flow

1. At startup, `app/blog.py` reads `content/blog/*.md`, parses frontmatter,
   renders bodies, and builds the in-memory registry.
2. A request to `/blog` or `/blog/{slug}` hits a `main.py` route, which
   inspects `Accept` (reusing the existing `_wants_markdown` helper) and asks
   `app/blog.py` for either the HTML page or the Markdown payload.
3. `sitemap.xml` and `llms.txt` read the registry at request time (cheap; the
   registry is already in memory) to list posts.

## First post

- Slug: `good-bot-bad-bot`
- Date: `2026-06-29`
- Title (working): "Good bot, bad bot: measuring AI-crawler compliance in
  the open"
- Angle: methodology explainer + "why I built this" (no data/findings yet).
- Section outline:
  1. Hook — "Who respects your robots.txt?" and why it matters now (AI
     crawlers).
  2. Why I built this — short, personal.
  3. How it works — open site + honeypots; linked vs unlinked axes
     (via-link / via-guess).
  4. Beyond the disallow list — Web Bot Auth signature verification;
     Discovery Reads (llms.txt / agents.md as invitations, not traps).
  5. Privacy (truncated IP hashing) + invitation to watch live + GitHub link.

## Error handling

- Unknown slug → 404 plain text.
- Malformed/missing frontmatter on a post file → that file is skipped at load
  with the failure isolated to that post (the rest of the blog still loads);
  a well-formed post set is the deploy-time contract.
- Empty blog (no files) → `/blog` renders an empty-state message; `/blog/x`
  → 404.

## Testing

- Local run against Docker (`docker compose up -d --build`):
  - `GET /blog` → 200, `text/html`.
  - `GET /blog/good-bot-bad-bot` → 200, `text/html`.
  - `GET /blog/good-bot-bad-bot` with `Accept: text/markdown` → 200,
    `text/markdown; charset=utf-8`, body is the raw source.
  - `GET /blog/does-not-exist` → 404.
  - `GET /sitemap.xml` contains the post URL; `GET /llms.txt` contains the
    `/blog` link.
- Visual: screenshot the index and the post in both themes (as done for the
  Discovery Reads view).

## Risks / trade-offs

- **New dependency** (`markdown-it-py`): justified — a prose blog genuinely
  needs Markdown rendering, the lib is pure-Python with no native build, and
  it keeps content out of code. Accepted by the user.
- **CSS duplication** between `index.html` and `blog.css`: accepted to avoid a
  risky refactor of the working dashboard. If a third surface needs the chrome
  later, extract a shared stylesheet then.
