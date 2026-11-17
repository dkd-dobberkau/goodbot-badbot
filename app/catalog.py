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
from dataclasses import dataclass
from datetime import date
from pathlib import Path

QUESTIONS = ("operator", "robots_txt", "recognition", "signing", "docs_opt_out")
SOURCES = ("user-agent", "cloudflare", "operator-docs", "signature-directory")
ROBOTS_VALUES = ("obeys", "does-not-obey", "no-statement")
# Only these may be stored; the other two sources are derived.
STORED_SOURCES = ("operator-docs", "cloudflare")

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
