"""Bot catalog: what is claimed about each bot, by whom, and what it did here.

There is no standard for a bot to describe itself, so the claims come from
several places that do not agree. The catalog lists each claim with its
source, next to our own measurements. See
docs/superpowers/specs/2026-11-17-bot-catalog-design.md.

Stored claims (app/bot_claims.json) are hand-recorded from operator docs and
from Cloudflare Radar, each with a URL and a retrieval date. User-Agent and
the other Cloudflare fields are derived at render time so they cannot drift.
"""
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from app import spoofing
from app.bots import CLASS_AI, CLASS_CRAWLER, classify_ua

QUESTIONS = ("operator", "robots_txt", "recognition", "signing", "docs_opt_out")
SOURCES = ("user-agent", "cloudflare", "operator-docs", "signature-directory")
ROBOTS_VALUES = ("obeys", "does-not-obey", "no-statement")
# Only these may be stored; the other two sources are derived.
STORED_SOURCES = ("operator-docs", "cloudflare")

# Signed rows before this moment failed because of our verifier, not the bot:
# every signature failed until 66e5b56, and bare-origin Signature-Agent values
# until f9873f9 (image pushed 2026-11-17 09:24:34 UTC). Naive UTC.
SIGNING_COUNT_SINCE = datetime(2026, 11, 17, 9, 30)
# Mirrors main.DISCOVERY_UA_GROUP_LIMIT: a UA-randomising crawler must not turn
# one catalog refresh into an unbounded result set.
CRAWLER_UA_GROUP_LIMIT = 500

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A UA's "+https://…" info URL. The UA is attacker-controlled, so the match
# stops at anything that could close a parenthesis, a tag or an attribute.
_UA_INFO_URL = re.compile(r"\+(https?://[^\s;)<>\"']+)")


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


def load_claims(path: Path, cf_slugs: set[str]) -> dict[str, BotClaims]:
    """Parse and validate the claims file, keyed by every name in `match`."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_claims(raw, cf_slugs, date.today())
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

    AI bots are named at write time and spoof-filtered like the scoreboard.
    Non-AI crawlers are named by classifying each distinct UA (not each row);
    their rows carry no bot_name, so they cannot be spoof-filtered."""
    measured: dict[str, Measurements] = {}
    for row in named_rows:
        name = row["bot_name"]
        entry = measured.setdefault(
            name, Measurements(name, CLASS_AI, row["operator"] or "—", spoof_filtered=True))
        _add_row(entry, row)

    spoofed_ids = spoofing.find_spoofed_visit_ids(named_visits)
    for visit in named_visits:
        entry = measured.get(visit["bot_name"])
        if entry is None or visit["id"] not in spoofed_ids:
            continue
        entry.spoofed_by_others += 1
        if visit["is_honeypot"]:
            entry.honeypot_hits -= 1

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
        CAST(SUM(signature_status = 'verified' AND ts >= %s) AS UNSIGNED) AS verified_since,
        CAST(SUM(signature_status = 'failed' AND ts >= %s) AS UNSIGNED) AS failed_since,
        CAST(SUM(signature_status IS NOT NULL AND ts < %s) AS UNSIGNED) AS signed_before,
        MIN(CASE WHEN is_honeypot = 1 THEN ts END) AS first_honeypot_ts,
        MIN(CASE WHEN path = '/robots.txt' THEN ts END) AS first_robots_ts
    """
    params = (*discovery_paths, *(p + "%" for p in discovery_prefixes),
              SIGNING_COUNT_SINCE, SIGNING_COUNT_SINCE, SIGNING_COUNT_SINCE)
    return columns, params


async def fetch_measurements(cur, discovery_paths: tuple[str, ...],
                             discovery_prefixes: tuple[str, ...]) -> dict[str, Measurements]:
    columns, params = _aggregate_columns(discovery_paths, discovery_prefixes)
    await cur.execute(
        f"SELECT bot_name, operator, {columns} FROM visits "
        "WHERE bot_name IS NOT NULL GROUP BY bot_name, operator, user_agent",
        params,
    )
    named_rows = await cur.fetchall()
    await cur.execute("""
        SELECT id, ts, ip_hash, bot_name, operator, path, is_honeypot
        FROM visits
        WHERE bot_name IS NOT NULL AND ip_hash IS NOT NULL
    """)
    named_visits = await cur.fetchall()
    await cur.execute(
        f"SELECT {columns} FROM visits WHERE bot_name IS NULL "
        f"GROUP BY user_agent ORDER BY visits DESC LIMIT {CRAWLER_UA_GROUP_LIMIT}",
        params,
    )
    crawler_ua_rows = await cur.fetchall()
    return combine_measurements(list(named_rows), list(named_visits), list(crawler_ua_rows))
