"""Bot catalog: what is claimed about each bot, by whom, and what it did here.

There is no standard for a bot to describe itself, so the claims come from
several places that do not agree. The catalog lists each claim with its
source, next to our own measurements. See
docs/superpowers/specs/2026-11-17-bot-catalog-design.md.

Stored claims (app/bot_claims.json) are hand-recorded from operator docs and
from Cloudflare Radar, each with a URL and a retrieval date. User-Agent and
the other Cloudflare fields are derived at render time so they cannot drift.
"""
import html
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from app import facts, spoofing
from app.bots import CLASS_AI, CLASS_CRAWLER, NON_AI_CRAWLERS, classify_ua

QUESTIONS = ("operator", "robots_txt", "recognition", "signing", "docs_opt_out")
SOURCES = ("user-agent", "cloudflare", "operator-docs", "signature-directory")
ROBOTS_VALUES = ("obeys", "does-not-obey", "no-statement")
# Only these may be stored; the other two sources are derived.
STORED_SOURCES = ("operator-docs", "cloudflare")

# Failed signatures before this moment failed because of our verifier, not the
# bot, so they are set aside. A verified signature is never our fault and
# counts whenever it happened (GeedoShopProductFinder, 2026-11-06).
# Every signature failed until 66e5b56, and bare-origin Signature-Agent values
# until f9873f9 (image pushed 2026-11-17 09:24:34 UTC). Naive UTC.
SIGNING_COUNT_SINCE = datetime(2026, 11, 17, 9, 30)
# Mirrors main.DISCOVERY_UA_GROUP_LIMIT: a UA-randomising crawler must not turn
# one catalog refresh into an unbounded result set.
CRAWLER_UA_GROUP_LIMIT = 500

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A UA's "+https://…" info URL. The UA is attacker-controlled, so the match
# stops at anything that could close a parenthesis, a tag or an attribute.
_UA_INFO_URL = re.compile(r"\+(https?://[^\s;)<>\"']+)")
# Only these URLs become links. cf_bots.json is a third-party copy and holds
# scheme-less values, leading spaces and could hold javascript: URLs.
_LINKABLE_URL = re.compile(r"^https?://[^\s<>\"']+$")


@dataclass(frozen=True)
class Claim:
    question: str
    value: str
    source: str
    url: str | None
    retrieved: str | None
    note: str = ""


@dataclass(frozen=True)
class BotClaims:
    slug: str
    name: str
    match: tuple[str, ...]
    cloudflare_slug: str | None
    docs_recorded: bool
    claims: tuple[Claim, ...]


def _claim_errors(where: str, question: str, claim: dict, today: date) -> list[str]:
    errors = []
    source = claim.get("source")
    if source not in STORED_SOURCES:
        errors.append(f"{where}: source {source!r} cannot be stored (use {STORED_SOURCES})")
    url = claim.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        errors.append(f"{where}: url must start with https://")
    retrieved = claim.get("retrieved")
    if not isinstance(retrieved, str) or not _ISO_DATE.match(retrieved):
        errors.append(f"{where}: retrieved must be YYYY-MM-DD")
    else:
        try:
            if date.fromisoformat(retrieved) > today:
                errors.append(f"{where}: retrieved {retrieved} is in the future")
        except ValueError:
            errors.append(f"{where}: retrieved {retrieved} is not a date")
    if question == "robots_txt" and claim.get("value") not in ROBOTS_VALUES:
        errors.append(f"{where}: robots_txt value must be one of {ROBOTS_VALUES}")
    if not isinstance(claim.get("value"), str) or not claim["value"]:
        errors.append(f"{where}: value is required")
    return errors


def validate_claims(raw: dict, cf_slugs: set[str], today: date) -> list[str]:
    """Readable errors for a parsed bot_claims.json; empty means valid."""
    errors = []
    seen_names: dict[str, str] = {}
    for slug, entry in raw.items():
        if not entry.get("name"):
            errors.append(f"{slug}: name is required")
        for name in entry.get("match") or []:
            if name in seen_names:
                errors.append(f"{slug}: match {name!r} already used by {seen_names[name]}")
            seen_names[name] = slug
        cf_slug = entry.get("cloudflare_slug")
        if cf_slug is not None and cf_slug not in cf_slugs:
            errors.append(f"{slug}: cloudflare_slug {cf_slug!r} is not in cf_bots.json")
        for question, claims in (entry.get("claims") or {}).items():
            if question not in QUESTIONS:
                errors.append(f"{slug}: unknown question {question!r}")
                continue
            for index, claim in enumerate(claims):
                errors += _claim_errors(f"{slug}.{question}[{index}]", question, claim, today)
    return errors


def _utc_today() -> date:
    # The container runs in UTC; a date recorded in Germany just after
    # midnight must not count as "in the future" and stop the app starting.
    return datetime.now(timezone.utc).date()


def load_claims(path: Path, cf_slugs: set[str]) -> dict[str, BotClaims]:
    """Parse and validate the claims file, keyed by every name in `match`."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_claims(raw, cf_slugs, _utc_today())
    if errors:
        raise ValueError("invalid bot claims:\n" + "\n".join(errors))
    by_name = {}
    for slug, entry in raw.items():
        claims = tuple(
            Claim(question, c["value"], c["source"], c["url"], c["retrieved"], c.get("note", ""))
            for question, entries in (entry.get("claims") or {}).items()
            for c in entries
        )
        bot = BotClaims(slug, entry["name"], tuple(entry["match"]), entry.get("cloudflare_slug"),
                        bool(entry.get("docs_recorded")), claims)
        for name in bot.match:
            by_name[name] = bot
    return by_name


def ua_info_url(user_agent: str) -> str | None:
    match = _UA_INFO_URL.search(user_agent or "")
    return match.group(1) if match else None


def derived_claims(name: str, cf_entry: dict | None, top_user_agent: str | None) -> list[Claim]:
    """Claims taken from the UA string and from Cloudflare's directory.

    Cloudflare's followsRobotsTxt is deliberately ignored: in the vendored
    copy it is false for 560 of 607 bots, GoogleBot and AhrefsBot included,
    so false means "no value", not "does not obey". The robots.txt answer
    from Cloudflare is hand-checked on Radar and stored instead."""
    claims = []
    if cf_entry:
        if cf_entry.get("operator"):
            claims.append(Claim("operator", cf_entry["operator"], "cloudflare",
                                cf_entry.get("operatorUrl"), None))
        if cf_entry.get("signatureAgentUrl"):
            claims.append(Claim("signing", "publishes a key directory", "cloudflare",
                                cf_entry["signatureAgentUrl"], None))
    url = ua_info_url(top_user_agent or "")
    if url:
        claims.append(Claim("docs_opt_out", "info URL in the user agent", "user-agent", url, None))
    return claims


@dataclass
class Measurements:
    name: str
    bot_class: str
    operator: str
    visits: int = 0
    honeypot_hits: int = 0
    spoof_filtered: bool = False
    robots_read_before_first_hit: bool | None = None
    discovery_reads: int = 0
    signed_verified: int = 0
    signed_failed: int = 0
    signed_before_fix: int = 0
    spoofed_by_others: int = 0
    top_user_agent: str | None = None
    _ua_visits: Counter = field(default_factory=Counter, repr=False)
    _first_hit: datetime | None = field(default=None, repr=False)
    _first_robots: datetime | None = field(default=None, repr=False)


def _earliest(a: datetime | None, b: datetime | None) -> datetime | None:
    return min(x for x in (a, b) if x is not None) if (a or b) else None


def _add_row(entry: Measurements, row: dict) -> None:
    entry.visits += int(row["visits"] or 0)
    entry.honeypot_hits += int(row["honeypot"] or 0)
    entry.discovery_reads += int(row["discovery"] or 0)
    entry.signed_verified += int(row["verified_since"] or 0)
    entry.signed_failed += int(row["failed_since"] or 0)
    entry.signed_before_fix += int(row["signed_before"] or 0)
    entry._ua_visits[row["user_agent"]] += int(row["visits"] or 0)
    entry._first_hit = _earliest(entry._first_hit, row["first_honeypot_ts"])
    entry._first_robots = _earliest(entry._first_robots, row["first_robots_ts"])


def combine_measurements(named_rows: list[dict], named_visits: list[dict],
                         crawler_ua_rows: list[dict]) -> dict[str, Measurements]:
    """Per-name measurements from per-UA aggregates.

    AI bots are named at write time; named_rows must already exclude spoofed
    visits (fetch_measurements does that in SQL), and named_visits is only
    used to count how often each name was borrowed. Non-AI crawlers are named
    by classifying each distinct UA (not each row); their rows carry no
    bot_name, so they cannot be spoof-filtered."""
    measured: dict[str, Measurements] = {}
    for row in named_rows:
        name = row["bot_name"]
        entry = measured.setdefault(
            name, Measurements(name, CLASS_AI, row["operator"] or "—", spoof_filtered=True))
        _add_row(entry, row)

    spoofed_ids = spoofing.find_spoofed_visit_ids(named_visits)
    for visit in named_visits:
        entry = measured.get(visit["bot_name"])
        if entry is not None and visit["id"] in spoofed_ids:
            entry.spoofed_by_others += 1

    for row in crawler_ua_rows:
        bot_class, name, operator = classify_ua(row["user_agent"])
        if bot_class != CLASS_CRAWLER:
            continue
        entry = measured.setdefault(name, Measurements(name, CLASS_CRAWLER, operator))
        _add_row(entry, row)

    for entry in measured.values():
        entry.top_user_agent = entry._ua_visits.most_common(1)[0][0] if entry._ua_visits else None
        if entry.honeypot_hits > 0 and entry._first_hit is not None:
            entry.robots_read_before_first_hit = (
                entry._first_robots is not None and entry._first_robots < entry._first_hit)
    return measured


def _aggregate_columns(discovery_paths: tuple[str, ...], discovery_prefixes: tuple[str, ...]):
    """The per-UA aggregate SELECT list and its parameters."""
    path_ph = ",".join(["%s"] * len(discovery_paths)) or "NULL"
    # pymysql formats the whole statement, so a literal % must be doubled; the
    # prefixes are passed as parameters with the LIKE wildcard appended.
    prefix_sql = "".join(" OR path LIKE %s" for _ in discovery_prefixes)
    columns = f"""
        user_agent,
        COUNT(*) AS visits,
        CAST(SUM(is_honeypot) AS UNSIGNED) AS honeypot,
        CAST(SUM((path IN ({path_ph}){prefix_sql}) AND COALESCE(method, 'GET') <> 'HEAD')
             AS UNSIGNED) AS discovery,
        CAST(SUM(signature_status = 'verified') AS UNSIGNED) AS verified_since,
        CAST(SUM(signature_status = 'failed' AND ts >= %s) AS UNSIGNED) AS failed_since,
        CAST(SUM(signature_status = 'failed' AND ts < %s) AS UNSIGNED) AS signed_before,
        MIN(CASE WHEN is_honeypot = 1 THEN ts END) AS first_honeypot_ts,
        MIN(CASE WHEN path = '/robots.txt' THEN ts END) AS first_robots_ts
    """
    params = (*discovery_paths, *(p + "%" for p in discovery_prefixes),
              SIGNING_COUNT_SINCE, SIGNING_COUNT_SINCE)
    return columns, params


def _like_pattern(key: str) -> str:
    escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def fetch_measurements(cur, discovery_paths: tuple[str, ...],
                             discovery_prefixes: tuple[str, ...]) -> dict[str, Measurements]:
    columns, params = _aggregate_columns(discovery_paths, discovery_prefixes)
    # Spoofed visits first, so every AI measurement can exclude them: the
    # visit count, robots.txt timing and top UA, not only the honeypot hits.
    await cur.execute("""
        SELECT id, ts, ip_hash, bot_name, operator, path, is_honeypot
        FROM visits
        WHERE bot_name IS NOT NULL AND ip_hash IS NOT NULL
    """)
    named_visits = list(await cur.fetchall())
    spoofed_ids = sorted(spoofing.find_spoofed_visit_ids(named_visits))
    not_spoofed = f"AND id NOT IN ({','.join(['%s'] * len(spoofed_ids))})" if spoofed_ids else ""
    await cur.execute(
        f"SELECT bot_name, operator, {columns} FROM visits "
        f"WHERE bot_name IS NOT NULL {not_spoofed} GROUP BY bot_name, operator, user_agent",
        (*params, *spoofed_ids),
    )
    named_rows = await cur.fetchall()
    # Only UAs that can classify as a named crawler: browser UAs and scanners
    # rotating random strings must not use up the group limit and push a
    # one-visit crawler out of the catalog.
    patterns = tuple(_like_pattern(key) for key in NON_AI_CRAWLERS)
    matches = " OR ".join(["LOWER(user_agent) LIKE %s"] * len(patterns))
    await cur.execute(
        f"SELECT {columns} FROM visits WHERE bot_name IS NULL AND ({matches}) "
        f"GROUP BY user_agent ORDER BY visits DESC LIMIT {CRAWLER_UA_GROUP_LIMIT}",
        (*params, *patterns),
    )
    crawler_ua_rows = await cur.fetchall()
    return combine_measurements(list(named_rows), named_visits, list(crawler_ua_rows))


@dataclass(frozen=True)
class ShownClaim:
    claim: Claim
    is_link: bool
    contradicted: bool
    reason: str


@dataclass
class CatalogEntry:
    name: str
    operator: str
    bot_class: str
    docs_recorded: bool
    claims: list[ShownClaim]
    measurements: Measurements


@dataclass(frozen=True)
class CatalogSummary:
    bots: int
    docs_recorded: int
    with_contradiction: int


def _contradiction(claim: Claim, measured: Measurements) -> str:
    """The reason a claim is contradicted, or "" when it is not.

    Deliberately one rule. Only spoof-filtered (AI) bots qualify, and signing
    has no rule: anyone borrowing a name sends unsigned requests, and a failed
    signature may be our verifier's fault."""
    if (claim.question == "robots_txt" and claim.value == "obeys"
            and measured.bot_class == CLASS_AI and measured.honeypot_hits >= 1):
        hits = measured.honeypot_hits
        return f"{hits} honeypot hit{'s' if hits != 1 else ''}"
    return ""


def build_catalog(claims: dict[str, BotClaims], cf_by_slug: dict[str, dict],
                  measurements: dict[str, Measurements]) -> tuple[list[CatalogEntry], CatalogSummary]:
    """One entry per measured bot, stored claims first, then derived ones."""
    entries = []
    for name, measured in measurements.items():
        if measured.visits < 1:
            continue
        stored = claims.get(name)
        cf_entry = cf_by_slug.get(stored.cloudflare_slug) if stored and stored.cloudflare_slug else None
        all_claims = [*(stored.claims if stored else ()),
                      *derived_claims(name, cf_entry, measured.top_user_agent)]
        shown = []
        for claim in all_claims:
            reason = _contradiction(claim, measured)
            linkable = bool(claim.url and _LINKABLE_URL.match(claim.url))
            shown.append(ShownClaim(claim, is_link=linkable and claim.source != "user-agent",
                                    contradicted=bool(reason), reason=reason))
        entries.append(CatalogEntry(name, measured.operator, measured.bot_class,
                                    bool(stored and stored.docs_recorded), shown, measured))
    entries.sort(key=lambda e: (-e.measurements.honeypot_hits, -e.measurements.visits))
    summary = CatalogSummary(
        bots=len(entries),
        docs_recorded=sum(e.docs_recorded for e in entries),
        with_contradiction=sum(any(c.contradicted for c in e.claims) for e in entries),
    )
    return entries, summary


QUESTION_LABELS = {
    "operator": "Who runs it",
    "robots_txt": "Obeys robots.txt?",
    "recognition": "How to recognise it",
    "signing": "Signs its requests?",
    "docs_opt_out": "Docs and opt-out",
}
SOURCE_LABELS = {
    "user-agent": "stated in its user agent",
    "cloudflare": "Cloudflare",
    "operator-docs": "operator docs",
    "signature-directory": "signature directory",
}
_SINCE_LABEL = SIGNING_COUNT_SINCE.date().isoformat()

TITLE = "Bot catalog"
INTRO = (
    "There is no standard for a bot to describe itself. robots.txt holds the "
    "site's rules, not the bot's. The info URL in a user agent is a convention "
    "anyone can forge. Web Bot Auth proves who signed a request, not what the "
    "bot promises. So what a bot is said to do comes from several places that "
    "do not agree. This page lists every claim about each bot we have seen, "
    "where it comes from, and what the bot actually did here. An empty row is "
    "a finding, not a gap in the page."
)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _summary_line(summary: CatalogSummary) -> str:
    return (f"{_plural(summary.bots, 'bot')} · {summary.docs_recorded} with operator docs "
            f"recorded · {summary.with_contradiction} with at least one contradicted claim")


def _hits_text(m: Measurements) -> str:
    return str(m.honeypot_hits) + ("" if m.spoof_filtered else " (not checked for spoofing)")


def _hits_html(m: Measurements) -> str:
    if m.spoof_filtered:
        return str(m.honeypot_hits)
    return f'{m.honeypot_hits}<br><span class="source">not checked for spoofing</span>'


def _robots_first_text(m: Measurements) -> str:
    if m.robots_read_before_first_hit is None:
        return "—"
    return "yes" if m.robots_read_before_first_hit else "no"


def _signing_text(m: Measurements) -> str:
    parts = []
    if m.signed_verified:
        parts.append(f"{m.signed_verified} verified")
    if m.signed_failed:
        parts.append(f"{m.signed_failed} failed since {_SINCE_LABEL}")
    if m.signed_before_fix:
        parts.append(f"{m.signed_before_fix} failed before our verifier fix")
    return "; ".join(parts) or "none"


def _bot_notes(entry: CatalogEntry) -> list[str]:
    notes = []
    if not entry.docs_recorded:
        notes.append("operator docs not yet recorded")
    if entry.measurements.spoofed_by_others:
        notes.append(f"name borrowed in {_plural(entry.measurements.spoofed_by_others, 'spoofed visit')}")
    return notes


# Table columns: the two questions the measurements can speak to get their
# own column; the rest share one so the table stays readable.
_OTHER_QUESTIONS = ("operator", "recognition", "docs_opt_out")
_HEADERS = ("Bot", "Visits", "Honeypot hits", "Read robots.txt first?", "Signed requests",
            "Obeys robots.txt?", "Signs its requests?", "Other claims")


def _claim_columns(entry: CatalogEntry) -> tuple[list[ShownClaim], list[ShownClaim], list[ShownClaim]]:
    grouped = _claims_by_question(entry)
    others = [c for q in _OTHER_QUESTIONS for c in grouped[q]]
    return grouped["robots_txt"], grouped["signing"], others


def _claims_by_question(entry: CatalogEntry) -> dict[str, list[ShownClaim]]:
    grouped = {question: [] for question in QUESTIONS}
    for shown in entry.claims:
        grouped[shown.claim.question].append(shown)
    return grouped


def _claim_html(shown: ShownClaim, with_question: bool = False) -> str:
    claim = shown.claim
    source = html.escape(SOURCE_LABELS[claim.source])
    if claim.retrieved:
        source += f", {html.escape(claim.retrieved)}"
    if shown.is_link:
        url = html.escape(claim.url, quote=True)
        source = f'<a href="{url}" rel="nofollow noopener">{source}</a>'
    elif claim.url:
        source += f": <code>{html.escape(claim.url)}</code>"
    label = f"{html.escape(QUESTION_LABELS[claim.question])}: " if with_question else ""
    text = f"{label}{html.escape(claim.value)} <span class=\"source\">({source})</span>"
    if claim.note:
        text += f" — {html.escape(claim.note)}"
    if shown.contradicted:
        text += f' <strong class="contradicted">contradicted: {html.escape(shown.reason)}</strong>'
    return f"<li>{text}</li>"


def _claims_cell_html(claims: list[ShownClaim], with_question: bool = False) -> str:
    if not claims:
        return '<span class="source">no source</span>'
    return '<ul class="claims">' + "".join(_claim_html(c, with_question) for c in claims) + "</ul>"


def _row_html(entry: CatalogEntry) -> str:
    m = entry.measurements
    robots, signing, others = _claim_columns(entry)
    bot = (f'<span class="bot-name">{html.escape(entry.name)}</span>'
           f'<br><span class="source">{html.escape(entry.operator)}</span>')
    if m.top_user_agent:
        bot += f"<br><code>{html.escape(m.top_user_agent)}</code>"
    for note in _bot_notes(entry):
        bot += f'<br><em class="source">{html.escape(note)}</em>'
    cells = (
        bot, str(m.visits), _hits_html(m), _robots_first_text(m),
        html.escape(_signing_text(m)), _claims_cell_html(robots), _claims_cell_html(signing),
        _claims_cell_html(others, with_question=True),
    )
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def render_html(entries: list[CatalogEntry], summary: CatalogSummary) -> str:
    if entries:
        head = "".join(f'<th scope="col">{html.escape(h)}</th>' for h in _HEADERS)
        rows = "".join(_row_html(entry) for entry in entries)
        body = (f'<div class="table-scroll" tabindex="0" role="region" aria-label="{TITLE}">'
                f'<table class="catalog"><thead><tr>{head}</tr></thead>'
                f"<tbody>{rows}</tbody></table></div>")
    else:
        body = '<p class="empty">No bots observed yet.</p>'
    content = (
        f'<main class="article catalog-page" id="main"><h1 class="article-title">{TITLE}</h1>'
        f"<p>{html.escape(INTRO)}</p>"
        f'<p class="article-date">{html.escape(_summary_line(summary))}</p>'
        f"{body}</main>"
    )
    return facts._page(TITLE, content)


def _md_cell(text: str) -> str:
    """Text inside a Markdown table cell: a pipe would start a new column."""
    return text.replace("|", "\\|").replace("\n", " ")


def _md_code(text: str) -> str:
    """Untrusted text as an inert Markdown code span."""
    return "`" + text.replace("`", "").replace("\n", " ") + "`"


def _claim_markdown(shown: ShownClaim, with_question: bool = False) -> str:
    claim = shown.claim
    source = SOURCE_LABELS[claim.source] + (f", {claim.retrieved}" if claim.retrieved else "")
    if shown.is_link:
        source = f"[{source}](<{claim.url}>)"
    elif claim.url:
        source += f": {_md_code(claim.url)}"
    text = (f"{QUESTION_LABELS[claim.question]}: " if with_question else "") + f"{claim.value} ({source})"
    if claim.note:
        text += f" — {claim.note}"
    if shown.contradicted:
        text += f" **contradicted: {shown.reason}**"
    return text


def _claims_cell_markdown(claims: list[ShownClaim], with_question: bool = False) -> str:
    return "<br>".join(_claim_markdown(c, with_question) for c in claims) or "no source"


def render_markdown(entries: list[CatalogEntry], summary: CatalogSummary) -> str:
    lines = [f"# {TITLE}", "", INTRO, "", _summary_line(summary), ""]
    if not entries:
        lines.append("No bots observed yet.")
    else:
        lines.append("| " + " | ".join(_HEADERS) + " |")
        lines.append("|" + "---|" * len(_HEADERS))
    for entry in entries:
        m = entry.measurements
        robots, signing, others = _claim_columns(entry)
        bot = f"**{entry.name}**<br>{entry.operator}"
        if m.top_user_agent:
            bot += f"<br>{_md_code(m.top_user_agent)}"
        bot += "".join(f"<br>_{note}_" for note in _bot_notes(entry))
        cells = (bot, str(m.visits), _hits_text(m), _robots_first_text(m), _signing_text(m),
                 _claims_cell_markdown(robots), _claims_cell_markdown(signing),
                 _claims_cell_markdown(others, with_question=True))
        lines.append("| " + " | ".join(_md_cell(cell) for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def _public_measurements(m: Measurements) -> dict:
    return {k: v for k, v in asdict(m).items() if not k.startswith("_")}


def to_json(entries: list[CatalogEntry], summary: CatalogSummary) -> dict:
    return {
        "summary": asdict(summary),
        "bots": [
            {
                "name": e.name,
                "operator": e.operator,
                "class": e.bot_class,
                "docs_recorded": e.docs_recorded,
                "measurements": _public_measurements(e.measurements),
                "claims": [
                    {**asdict(s.claim), "is_link": s.is_link,
                     "contradicted": s.contradicted, "reason": s.reason}
                    for s in e.claims
                ],
            }
            for e in entries
        ],
    }
