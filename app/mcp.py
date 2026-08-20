"""Stateless MCP server (protocol revision 2026-07-28) for goodbot-badbot.

Why this exists
---------------
Revision 2026-07-28 removed the `initialize` handshake and protocol-level
sessions from Streamable HTTP: every POST is self-contained, carrying its
protocol version and client identity in `_meta` (mirrored into headers). That
makes an MCP server for a read-only stats API small enough to be a pure
function of the already-cached `/api/stats` payload — no session store, no
background stream, no new DB queries.

Two things are being measured by hosting it. First, whether agents *invoke*
the offered machine interface at all once it is described as tools rather than
as an OpenAPI document. Second — and this is the part nobody has data on —
whether agents *guess* `/mcp` unprompted. There is no discovery specification
for MCP endpoints, so the endpoint is announced only in the ARD manifest,
llms.txt and agents.md; it is deliberately kept out of the homepage `Link`
header. Reads of `/mcp` by a bot that never touched a discovery file are
therefore guesses, and reads that follow an `ai-catalog.json` read are not.

This module is pure: it takes a decoded body, the request headers and an
already-computed stats dict, and returns `(http_status, json_body)`. All I/O
(logging, stats fetching, Origin checks) stays in the route in `app.main`.

Spec references (2026-07-28):
  - basic/transports/streamable-http  — POST-only, header mirroring, -32020
  - basic/versioning                  — -32022 UnsupportedProtocolVersionError
  - server/discover                   — MUST be implemented
  - server/tools                      — tools/list, tools/call, resultType
"""

import base64
import json
from typing import Any, Callable

PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION,)

SERVER_INFO = {"name": "goodbot-badbot", "version": "1.0.0"}

SERVER_INSTRUCTIONS = (
    "goodbot-badbot.com measures whether AI crawlers obey robots.txt. Six "
    "honeypot paths are listed as Disallow; any request to one is logged as a "
    "violation. Use get_compliance_stats for the scoreboard and check_bot to "
    "look up a single crawler by name or user-agent string. All data is "
    "observational and public; there is nothing to write here."
)

SITE_BASE_URL = "https://goodbot-badbot.com"


def _missing_header_message(header: str) -> str:
    """Explain a missing required header instead of only naming it.

    Revision 2026-07-28 has no handshake, so a caller never learns the rules
    from an initialize round-trip — the first request either carries every
    header or fails. A bare "Mcp-Method header is required" is technically a
    complete answer and practically a riddle, so the error states the whole
    requirement at the moment it bites. (Written after walking into it while
    verifying a deploy of this very endpoint.)
    """
    return (
        f"Header mismatch: {header} header is required. Protocol revision "
        f"{PROTOCOL_VERSION} is stateless — there is no initialize handshake, so "
        "every POST must carry MCP-Protocol-Version and Mcp-Method, plus Mcp-Name "
        f"for tools/call. Worked example: {SITE_BASE_URL}/llms.txt"
    )

# Discovery manifest for /.well-known/mcp-server, per
# draft-serra-mcp-discovery-uri-04 §6.
#
# Status matters here and is the reason this exists at all: that draft is an
# *individual* Internet-Draft. The IETF states plainly that it "is not endorsed
# by the IETF and has no formal standing in the IETF standards process", it has
# not been adopted by any working group, and revision 04 expires in September
# 2026. So this is not compliance with a standard — it is this site doing what
# it did with the API catalog and the ARD manifest: publishing an offer far
# ahead of any ecosystem that would consume it, and then measuring the silence.
#
# Until now MCP was the one interface here that nothing advertised by path;
# /mcp was announced only in llms.txt, agents.md and the ARD manifest. This
# adds a fourth announcement channel, and it is the first one specified by
# anybody outside this project.


def build_mcp_manifest() -> dict:
    """Return the /.well-known/mcp-server manifest.

    Every field is checked against what the server actually does rather than
    what would look impressive: capabilities claims `tools` alone because
    initialize advertises `{"tools": {}}` and nothing else, and auth declares
    itself open because it is. Advertising a resources or prompts interface
    that does not exist would be the machine-readable version of lying.
    """
    return {
        # §6.2 — required.
        "mcp_version": PROTOCOL_VERSION,
        "name": SERVER_INFO["name"],
        "endpoint": f"{SITE_BASE_URL}/mcp",
        "transport": "http",
        # §6.3 — recommended. All four are answerable honestly, so all four
        # are here; a SHOULD is only worth skipping when the truthful answer
        # is unknown.
        "description": (
            "Compliance data for AI crawlers: which ones fetch robots.txt-forbidden "
            "honeypot paths, and which discovery surfaces they read. Read-only."
        ),
        "auth": {"required": False, "methods": ["none"]},
        "capabilities": ["tools"],
        "trust_class": "public",
        # §6.4 — optional.
        "docs": f"{SITE_BASE_URL}/blog/mcp-endpoint",
    }


# `_meta` key carrying the protocol version in the request body. The
# MCP-Protocol-Version header mirrors it and the two MUST agree.
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# JSON-RPC codes plus the two MCP-defined ones we can return.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022

# Guard rails on caller-supplied values before they reach any lookup.
MAX_BOT_QUERY_LEN = 512
MAX_STATS_LIMIT = 50
DEFAULT_STATS_LIMIT = 20


# ── Tool definitions ─────────────────────────────────────────────────────────

# Deliberately two read-only tools over data the dashboard already publishes.
# Nothing here can mutate state, so there is no destructive operation for a
# client to gate behind human confirmation.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_compliance_stats",
        "title": "robots.txt compliance scoreboard",
        "description": (
            "Return the live robots.txt-compliance scoreboard: every AI crawler "
            "observed on goodbot-badbot.com, how many times it was seen, how "
            "many honeypot violations it committed, and the resulting verdict "
            "(good_bot = zero violations, bad_bot = one or more). Sorted by "
            "violations descending."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_STATS_LIMIT,
                    "description": (
                        f"How many bots to return (default {DEFAULT_STATS_LIMIT}, "
                        f"max {MAX_STATS_LIMIT})."
                    ),
                }
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "totals": {
                    "type": "object",
                    "properties": {
                        "violations": {"type": "integer"},
                        "bots_seen": {"type": "integer"},
                        "verified_signatures": {"type": "integer"},
                        "discovery_reads": {"type": "integer"},
                    },
                    "required": ["violations", "bots_seen"],
                },
                "bots": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "bot_name": {"type": "string"},
                            "operator": {"type": "string"},
                            "verdict": {"type": "string", "enum": ["good_bot", "bad_bot"]},
                            "total_visits": {"type": "integer"},
                            "violations": {"type": "integer"},
                            "verified_visits": {"type": "integer"},
                            "last_seen": {"type": ["string", "null"]},
                        },
                        "required": ["bot_name", "verdict", "violations"],
                    },
                },
            },
            "required": ["totals", "bots"],
        },
    },
    {
        "name": "check_bot",
        "title": "Look up one crawler",
        "description": (
            "Look up a single crawler by display name (e.g. 'GPTBot') or by raw "
            "User-Agent string. Reports whether it is a recognised AI crawler, "
            "and — if it has been observed here — its visit count, honeypot "
            "violations and verdict."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bot": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_BOT_QUERY_LEN,
                    "description": "Bot display name or full User-Agent string.",
                }
            },
            "required": ["bot"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "recognised": {
                    "type": "boolean",
                    "description": "True if the string matches a known AI crawler.",
                },
                "observed": {
                    "type": "boolean",
                    "description": "True if this crawler has been seen on this site.",
                },
                "bot_name": {"type": ["string", "null"]},
                "operator": {"type": ["string", "null"]},
                "verdict": {"type": ["string", "null"], "enum": ["good_bot", "bad_bot", None]},
                "total_visits": {"type": "integer"},
                "violations": {"type": "integer"},
                "last_seen": {"type": ["string", "null"]},
            },
            "required": ["query", "recognised", "observed"],
        },
    },
]

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def build_server_card(endpoint_url: str) -> dict[str, Any]:
    """MCP server card for embedding in the ARD manifest.

    ARD entries carry either a `url` pointing at an artifact document or an
    inline `data` object. `/mcp` is POST-only and serves no document, so the
    card is inlined — the same shape the ARD spec's own MCP example uses,
    plus the endpoint URL so a registry can pass it through to an agent.
    Built from TOOLS so the advertised tool list cannot drift from the served
    one.
    """
    return {
        "name": SERVER_INFO["name"],
        "description": SERVER_INSTRUCTIONS,
        "url": endpoint_url,
        "protocolVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
            }
            for tool in TOOLS
        ],
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

_B64_PREFIX = "=?base64?"
_B64_SUFFIX = "?="


def decode_header_value(raw: str) -> str:
    """Decode the `=?base64?...?=` sentinel clients use for non-ASCII headers.

    Markers are case-sensitive and lowercase per the transport spec. A value
    that only looks like the sentinel but does not decode is returned as-is —
    it will then simply fail the header/body comparison, which is the right
    outcome rather than a 500.
    """
    if not (raw.startswith(_B64_PREFIX) and raw.endswith(_B64_SUFFIX)):
        return raw
    payload = raw[len(_B64_PREFIX):-len(_B64_SUFFIX)]
    try:
        return base64.b64decode(payload, validate=True).decode("utf-8")
    except Exception:
        return raw


def _iso(value: Any) -> str | None:
    # MySQL DATETIME comes back as a datetime; JSONResponse cannot serialise it.
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def _verdict(violations: int) -> str:
    # Same rule the dashboard renders: one violation is enough.
    return "bad_bot" if violations > 0 else "good_bot"


def _error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _result(req_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": {"resultType": "complete", **payload}}


def _tool_result(req_id: Any, structured: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    # A tool returning structuredContent SHOULD also mirror it into a text
    # block for clients that only read `content`.
    return _result(req_id, {
        "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
        "structuredContent": structured,
        "isError": is_error,
    })


# ── Tool implementations ─────────────────────────────────────────────────────

def _row_to_bot(row: dict[str, Any]) -> dict[str, Any]:
    violations = int(row.get("violations") or 0)
    return {
        "bot_name": row.get("bot_name") or "Unknown",
        "operator": row.get("operator") or "Unknown",
        "verdict": _verdict(violations),
        "total_visits": int(row.get("total_visits") or 0),
        "violations": violations,
        "verified_visits": int(row.get("verified_visits") or 0),
        "last_seen": _iso(row.get("last_seen")),
    }


def _tool_get_compliance_stats(arguments: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    raw_limit = arguments.get("limit", DEFAULT_STATS_LIMIT)
    if not isinstance(raw_limit, int) or isinstance(raw_limit, bool):
        raise ValueError("limit must be an integer")
    limit = max(1, min(MAX_STATS_LIMIT, raw_limit))
    summary = stats.get("summary") or []
    return {
        "source": "https://goodbot-badbot.com/api/stats",
        "totals": {
            "violations": int(stats.get("total_violations") or 0),
            "bots_seen": int(stats.get("total_bots_seen") or 0),
            "verified_signatures": int(stats.get("total_verified") or 0),
            "discovery_reads": int(stats.get("total_discovery_reads") or 0),
        },
        "bots": [_row_to_bot(row) for row in summary[:limit]],
    }


def _tool_check_bot(
    arguments: dict[str, Any],
    stats: dict[str, Any],
    identify_bot: Callable[[str], tuple[Any, Any, Any]],
) -> dict[str, Any]:
    raw = arguments.get("bot")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("bot must be a non-empty string")
    query = raw.strip()[:MAX_BOT_QUERY_LEN]

    # identify_bot does substring matching over KNOWN_BOTS, so it handles both
    # a bare display name and a full User-Agent header.
    _, bot_name, operator = identify_bot(query)
    recognised = bot_name is not None

    # Fall back to matching the query against names actually observed, so a bot
    # seen here but absent from KNOWN_BOTS still resolves.
    summary = stats.get("summary") or []
    row = None
    if recognised:
        row = next((r for r in summary if r.get("bot_name") == bot_name), None)
    else:
        needle = query.casefold()
        row = next((r for r in summary if (r.get("bot_name") or "").casefold() == needle), None)
        if row is not None:
            bot_name = row.get("bot_name")
            operator = row.get("operator")

    if row is None:
        return {
            "query": query,
            "recognised": recognised,
            "observed": False,
            "bot_name": bot_name,
            "operator": operator,
            "verdict": None,
            "total_visits": 0,
            "violations": 0,
            "last_seen": None,
            "note": (
                "Recognised AI crawler, but it has not visited this site yet."
                if recognised
                else "Not a recognised AI crawler and not observed on this site."
            ),
        }

    bot = _row_to_bot(row)
    return {"query": query, "recognised": recognised, "observed": True, **bot}


# ── JSON-RPC dispatch ────────────────────────────────────────────────────────

def _method_result(
    method: str,
    req_id: Any,
    params: dict[str, Any],
    headers: dict[str, str],
    stats: dict[str, Any],
    identify_bot: Callable[[str], tuple[Any, Any, Any]],
) -> tuple[int, dict[str, Any]]:
    if method == "server/discover":
        return 200, _result(req_id, {
            "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "capabilities": {"tools": {}},
            "instructions": SERVER_INSTRUCTIONS,
            "_meta": {META_SERVER_INFO: SERVER_INFO},
            # Tools change only on deploy; a public hour-long cache is safe and
            # keeps repeat probes off the DB entirely.
            "ttlMs": 3600000,
            "cacheScope": "public",
        })

    if method == "tools/list":
        # No pagination: two tools fit in one page, so nextCursor is omitted.
        return 200, _result(req_id, {
            "tools": TOOLS,
            "ttlMs": 3600000,
            "cacheScope": "public",
        })

    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str):
            return 200, _error(req_id, INVALID_PARAMS, "params.name is required")

        # Mcp-Name mirrors params.name and MUST match it.
        header_name = headers.get("mcp-name")
        if header_name is None:
            return 400, _error(
                req_id, HEADER_MISMATCH, "Header mismatch: Mcp-Name header is required for tools/call"
            )
        if decode_header_value(header_name) != name:
            return 400, _error(
                req_id, HEADER_MISMATCH,
                f"Header mismatch: Mcp-Name header value does not match body value '{name}'",
            )

        if name not in TOOLS_BY_NAME:
            return 200, _error(req_id, INVALID_PARAMS, f"Unknown tool: {name}")

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return 200, _error(req_id, INVALID_PARAMS, "params.arguments must be an object")

        # Argument-validation failures are tool execution errors, not protocol
        # errors: the model can read the message and retry with fixed input.
        try:
            if name == "get_compliance_stats":
                payload = _tool_get_compliance_stats(arguments, stats)
            else:
                payload = _tool_check_bot(arguments, stats, identify_bot)
        except ValueError as exc:
            return 200, _tool_result(req_id, {"error": str(exc)}, is_error=True)

        return 200, _tool_result(req_id, payload)

    # Unknown method: 404 with a JSON-RPC body, which is what distinguishes a
    # modern server from a legacy one that simply does not host this path.
    return 404, _error(req_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def handle_rpc(
    body: Any,
    headers: dict[str, str],
    *,
    stats: dict[str, Any],
    identify_bot: Callable[[str], tuple[Any, Any, Any]],
) -> tuple[int, dict[str, Any] | None]:
    """Handle one JSON-RPC message. Returns (http_status, json_body_or_None).

    `headers` must be lower-cased keys. A None body means "no response body",
    which is the 202 case for notifications.
    """
    if not isinstance(body, dict):
        return 400, _error(None, INVALID_REQUEST, "Request body must be a JSON-RPC object")
    if body.get("jsonrpc") != "2.0":
        return 400, _error(body.get("id"), INVALID_REQUEST, "jsonrpc must be '2.0'")

    method = body.get("method")
    if not isinstance(method, str) or not method:
        return 400, _error(body.get("id"), INVALID_REQUEST, "method is required")

    # No `id` means notification. This revision defines no client-to-server
    # notifications, but the transport still says: accept it, 202, no body.
    if "id" not in body:
        return 202, None
    req_id = body.get("id")

    # ── Header validation (transport spec, Server Validation) ────────────────
    header_version = headers.get("mcp-protocol-version")
    if not header_version:
        return 400, _error(
            req_id, HEADER_MISMATCH,
            _missing_header_message("MCP-Protocol-Version"),
        )

    header_method = headers.get("mcp-method")
    if header_method is None:
        return 400, _error(
            req_id, HEADER_MISMATCH,
            _missing_header_message("Mcp-Method"),
        )
    if header_method != method:
        return 400, _error(
            req_id, HEADER_MISMATCH,
            f"Header mismatch: Mcp-Method header value '{header_method}' does not match "
            f"body value '{method}'",
        )

    if header_version not in SUPPORTED_PROTOCOL_VERSIONS:
        return 400, _error(
            req_id, UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
            {"supported": list(SUPPORTED_PROTOCOL_VERSIONS), "requested": header_version},
        )

    params = body.get("params") or {}
    if not isinstance(params, dict):
        return 400, _error(req_id, INVALID_REQUEST, "params must be an object")

    # The body is the source of truth, but a client that omits _meta entirely
    # is not *mismatching* anything — reject only a version that contradicts
    # the header. Being lenient here keeps sloppy real-world agents in the
    # dataset, which is the whole point of hosting this.
    meta = params.get("_meta") or {}
    if isinstance(meta, dict):
        body_version = meta.get(META_PROTOCOL_VERSION)
        if body_version is not None and body_version != header_version:
            return 400, _error(
                req_id, HEADER_MISMATCH,
                f"Header mismatch: MCP-Protocol-Version header '{header_version}' does not "
                f"match body _meta value '{body_version}'",
            )

    return _method_result(method, req_id, params, headers, stats, identify_bot)
