"""Detect User-Agent rotation: one client claiming several operators' bots.

A User-Agent is a string the client picks. The honeypot log shows scanners
that cycle through names from one address within seconds — ClaudeBot,
ChatGPT-User, GPTBot and PerplexityBot inside four seconds — so their hits
would otherwise be charged to every bot they impersonate.

Rule: a named visit is spoofed when the same ip_hash produced a named visit
attributed to a *different operator* within SPOOF_WINDOW_S seconds. Operator,
not bot name, because one operator may legitimately run several crawlers
from shared infrastructure (GPTBot and OAI-SearchBot are both OpenAI).

The rule only catches rotation. A client that sticks to a single borrowed
name is indistinguishable from the real bot here; only Web Bot Auth can
tell those apart.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any, Iterable

SPOOF_WINDOW_S = 60
MAX_SPOOF_BURSTS = 20


def _operator_of(visit: dict[str, Any]) -> str:
    return visit.get("operator") or visit.get("bot_name") or ""


def _by_ip_hash(visits: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for visit in visits:
        if visit.get("ip_hash") and visit.get("bot_name"):
            grouped[visit["ip_hash"]].append(visit)
    for group in grouped.values():
        group.sort(key=lambda visit: visit["ts"])
    return grouped


def find_spoofed_visit_ids(
    visits: Iterable[dict[str, Any]], window_s: int = SPOOF_WINDOW_S
) -> set[int]:
    """Ids of named visits that share an ip_hash, within window_s, with a
    named visit of another operator. Visits need id, ts, ip_hash, bot_name
    and operator."""
    window = timedelta(seconds=window_s)
    spoofed: set[int] = set()
    for group in _by_ip_hash(visits).values():
        start = 0
        for end, visit in enumerate(group):
            while visit["ts"] - group[start]["ts"] > window:
                start += 1
            # Every visit in group[start:end] is within the window of this one;
            # mark both sides of any operator mismatch.
            for earlier in group[start:end]:
                if _operator_of(earlier) != _operator_of(visit):
                    spoofed.add(earlier["id"])
                    spoofed.add(visit["id"])
    return spoofed


def group_spoof_bursts(
    visits: Iterable[dict[str, Any]],
    spoofed_ids: set[int],
    window_s: int = SPOOF_WINDOW_S,
    limit: int = MAX_SPOOF_BURSTS,
) -> list[dict[str, Any]]:
    """Fold spoofed visits into bursts (same ip_hash, gaps of at most
    window_s), newest first. The ip_hash itself is deliberately not part of
    the output: the dashboard never publishes it."""
    window = timedelta(seconds=window_s)
    spoofed = [visit for visit in visits if visit.get("id") in spoofed_ids]
    bursts: list[list[dict[str, Any]]] = []
    for group in _by_ip_hash(spoofed).values():
        current = [group[0]]
        for visit in group[1:]:
            if visit["ts"] - current[-1]["ts"] > window:
                bursts.append(current)
                current = []
            current.append(visit)
        bursts.append(current)
    bursts.sort(key=lambda burst: burst[0]["ts"], reverse=True)
    return [_burst_summary(burst) for burst in bursts[:limit]]


def _burst_summary(burst: list[dict[str, Any]]) -> dict[str, Any]:
    claimed = list(dict.fromkeys(visit["bot_name"] for visit in burst))
    return {
        "started": burst[0]["ts"],
        "claimed_bots": claimed,
        "honeypot_hits": sum(1 for visit in burst if visit.get("is_honeypot")),
        "visits": [
            {
                "ts": visit["ts"],
                "bot_name": visit["bot_name"],
                "path": visit["path"],
                "is_honeypot": bool(visit.get("is_honeypot")),
            }
            for visit in burst
        ],
    }


def attributed_summary(
    summary: list[dict[str, Any]], visits: Iterable[dict[str, Any]], spoofed_ids: set[int]
) -> list[dict[str, Any]]:
    """Per-bot rows with violations reduced to hits the bot can be charged
    with, spoofed_hits holding the rest, re-sorted the way the raw query
    sorted (violations, then visits)."""
    spoofed_hits: dict[tuple[Any, Any], int] = defaultdict(int)
    for visit in visits:
        if visit.get("id") in spoofed_ids and visit.get("is_honeypot"):
            spoofed_hits[(visit["bot_name"], visit.get("operator"))] += 1
    rows = []
    for row in summary:
        spoofed = spoofed_hits.get((row["bot_name"], row.get("operator")), 0)
        rows.append({
            **row,
            "violations": int(row.get("violations") or 0) - spoofed,
            "spoofed_hits": spoofed,
        })
    rows.sort(key=lambda row: (row["violations"], int(row.get("total_visits") or 0)), reverse=True)
    return rows

