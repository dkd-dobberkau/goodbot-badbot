"""Stdlib smoke test for the stateless MCP server (revision 2026-07-28).

Run with: python test_mcp.py
Exit 0 if all assertions pass, 1 otherwise.

Covers the three methods the spec requires a server to answer
(server/discover, tools/list, tools/call), the transport's header-validation
rules (-32020 HeaderMismatch, -32022 UnsupportedProtocolVersionError, 404 for
unknown methods), and the two tools' behaviour against a fake stats payload.
No DB and no HTTP client: app.mcp.handle_rpc is a pure function.
"""
import datetime
import json
import sys

from app.mcp import (
    HEADER_MISMATCH,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    TOOLS,
    UNSUPPORTED_PROTOCOL_VERSION,
    build_server_card,
    decode_header_value,
    handle_rpc,
)

# Mirrors the shape _compute_stats() returns, including a real datetime in
# last_seen — JSONResponse cannot serialise those, so the tools must stringify.
FAKE_STATS = {
    "summary": [
        {
            "bot_name": "GPTBot", "operator": "OpenAI", "total_visits": 40,
            "violations": 7, "verified_visits": 0, "failed_sigs": 0,
            "last_seen": datetime.datetime(2026, 8, 1, 12, 0, 0),
        },
        {
            "bot_name": "ClaudeBot", "operator": "Anthropic", "total_visits": 25,
            "violations": 0, "verified_visits": 5, "failed_sigs": 0,
            "last_seen": datetime.datetime(2026, 8, 2, 9, 30, 0),
        },
    ],
    "total_violations": 7,
    "total_bots_seen": 2,
    "total_verified": 5,
    "total_discovery_reads": 12,
}


def fake_identify_bot(user_agent: str):
    ua = (user_agent or "").lower()
    if "gptbot" in ua:
        return "gptbot", "GPTBot", "OpenAI"
    if "claudebot" in ua:
        return "claudebot", "ClaudeBot", "Anthropic"
    return None, None, None


def call(method, params=None, *, headers=None, req_id=1, include_id=True):
    body = {"jsonrpc": "2.0", "method": method}
    if include_id:
        body["id"] = req_id
    if params is not None:
        body["params"] = params
    hdrs = {"mcp-protocol-version": PROTOCOL_VERSION, "mcp-method": method}
    if headers:
        hdrs.update(headers)
    return handle_rpc(body, hdrs, stats=FAKE_STATS, identify_bot=fake_identify_bot)


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures += 1

    # ── server/discover — the spec says servers MUST implement it ────────────
    status, res = call("server/discover")
    check("discover returns 200", status == 200)
    check("discover result is complete", res["result"]["resultType"] == "complete")
    check("discover lists the protocol version",
          PROTOCOL_VERSION in res["result"]["supportedVersions"])
    check("discover declares the tools capability",
          "tools" in res["result"]["capabilities"])
    check("discover carries serverInfo in _meta",
          bool(res["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"]))

    # ── tools/list ───────────────────────────────────────────────────────────
    status, res = call("tools/list")
    check("tools/list returns 200", status == 200)
    names = [t["name"] for t in res["result"]["tools"]]
    check("tools/list exposes both tools",
          names == ["get_compliance_stats", "check_bot"])
    check("every tool has an object inputSchema",
          all(t["inputSchema"]["type"] == "object" for t in res["result"]["tools"]))

    # ── tools/call: get_compliance_stats ─────────────────────────────────────
    status, res = call(
        "tools/call",
        {"name": "get_compliance_stats", "arguments": {}},
        headers={"mcp-name": "get_compliance_stats"},
    )
    check("get_compliance_stats returns 200", status == 200)
    payload = res["result"]["structuredContent"]
    check("not flagged as a tool error", res["result"]["isError"] is False)
    check("totals carry through", payload["totals"]["violations"] == 7)
    check("both bots returned", len(payload["bots"]) == 2)
    check("verdict: violations > 0 is bad_bot",
          payload["bots"][0]["bot_name"] == "GPTBot" and payload["bots"][0]["verdict"] == "bad_bot")
    check("verdict: zero violations is good_bot",
          payload["bots"][1]["verdict"] == "good_bot")
    check("datetimes are stringified",
          payload["bots"][0]["last_seen"] == "2026-08-01T12:00:00")
    check("whole result is JSON-serialisable", bool(json.dumps(res)))
    check("content mirrors structuredContent",
          json.loads(res["result"]["content"][0]["text"]) == payload)

    # limit is clamped, never trusted.
    _, res = call(
        "tools/call",
        {"name": "get_compliance_stats", "arguments": {"limit": 1}},
        headers={"mcp-name": "get_compliance_stats"},
    )
    check("limit is honoured", len(res["result"]["structuredContent"]["bots"]) == 1)
    _, res = call(
        "tools/call",
        {"name": "get_compliance_stats", "arguments": {"limit": 9999}},
        headers={"mcp-name": "get_compliance_stats"},
    )
    check("oversized limit is clamped, not rejected",
          len(res["result"]["structuredContent"]["bots"]) == 2)
    _, res = call(
        "tools/call",
        {"name": "get_compliance_stats", "arguments": {"limit": "many"}},
        headers={"mcp-name": "get_compliance_stats"},
    )
    check("bad limit type is a tool error, not a protocol error",
          res["result"]["isError"] is True)

    # ── tools/call: check_bot ────────────────────────────────────────────────
    _, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {"bot": "GPTBot"}},
        headers={"mcp-name": "check_bot"},
    )
    payload = res["result"]["structuredContent"]
    check("check_bot resolves a display name",
          payload["recognised"] and payload["observed"] and payload["verdict"] == "bad_bot")

    _, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {"bot": "Mozilla/5.0 (compatible; ClaudeBot/1.0)"}},
        headers={"mcp-name": "check_bot"},
    )
    payload = res["result"]["structuredContent"]
    check("check_bot resolves a full user-agent string",
          payload["bot_name"] == "ClaudeBot" and payload["verdict"] == "good_bot")

    _, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {"bot": "SomeRandomCrawler/2.0"}},
        headers={"mcp-name": "check_bot"},
    )
    payload = res["result"]["structuredContent"]
    check("unknown bot is reported, not errored",
          payload["recognised"] is False and payload["observed"] is False)

    _, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {}},
        headers={"mcp-name": "check_bot"},
    )
    check("missing required argument is a tool error", res["result"]["isError"] is True)

    status, res = call(
        "tools/call",
        {"name": "no_such_tool", "arguments": {}},
        headers={"mcp-name": "no_such_tool"},
    )
    check("unknown tool is a protocol error (-32602)",
          status == 200 and res["error"]["code"] == INVALID_PARAMS)

    # ── Transport: header validation ─────────────────────────────────────────
    status, res = handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"mcp-method": "tools/list"},
        stats=FAKE_STATS, identify_bot=fake_identify_bot,
    )
    check("missing MCP-Protocol-Version is 400 + HeaderMismatch",
          status == 400 and res["error"]["code"] == HEADER_MISMATCH)

    status, res = handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"mcp-protocol-version": PROTOCOL_VERSION},
        stats=FAKE_STATS, identify_bot=fake_identify_bot,
    )
    check("missing Mcp-Method is 400 + HeaderMismatch",
          status == 400 and res["error"]["code"] == HEADER_MISMATCH)

    status, res = handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"mcp-protocol-version": PROTOCOL_VERSION, "mcp-method": "tools/call"},
        stats=FAKE_STATS, identify_bot=fake_identify_bot,
    )
    check("Mcp-Method disagreeing with the body is 400 + HeaderMismatch",
          status == 400 and res["error"]["code"] == HEADER_MISMATCH)

    status, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {"bot": "GPTBot"}},
        headers={"mcp-name": "get_compliance_stats"},
    )
    check("Mcp-Name disagreeing with params.name is 400 + HeaderMismatch",
          status == 400 and res["error"]["code"] == HEADER_MISMATCH)

    # No Mcp-Name header at all — call() only sets the two mandatory ones.
    status, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {"bot": "GPTBot"}},
    )
    check("tools/call without Mcp-Name is 400 + HeaderMismatch",
          status == 400 and res["error"]["code"] == HEADER_MISMATCH)

    status, res = handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"mcp-protocol-version": "1900-01-01", "mcp-method": "tools/list"},
        stats=FAKE_STATS, identify_bot=fake_identify_bot,
    )
    check("unsupported version is 400 + -32022 listing supported versions",
          status == 400
          and res["error"]["code"] == UNSUPPORTED_PROTOCOL_VERSION
          and PROTOCOL_VERSION in res["error"]["data"]["supported"])

    # The body is the source of truth; a contradicting _meta must be rejected,
    # but an absent one is not a mismatch.
    status, res = call("tools/list", {"_meta": {
        "io.modelcontextprotocol/protocolVersion": "2025-11-25"}})
    check("_meta version contradicting the header is rejected",
          status == 400 and res["error"]["code"] == HEADER_MISMATCH)
    status, _ = call("tools/list", {"_meta": {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION}})
    check("_meta version matching the header is accepted", status == 200)
    status, _ = call("tools/list", {})
    check("absent _meta is accepted (lenient by design)", status == 200)

    status, res = call("resources/list")
    check("unknown method is 404 + -32601",
          status == 404 and res["error"]["code"] == METHOD_NOT_FOUND)

    status, res = call("tools/list", include_id=False)
    check("a notification gets 202 with no body", status == 202 and res is None)

    status, res = handle_rpc(
        ["not", "an", "object"], {}, stats=FAKE_STATS, identify_bot=fake_identify_bot,
    )
    check("non-object body is rejected", status == 400)

    status, res = handle_rpc(
        {"jsonrpc": "1.0", "id": 1, "method": "tools/list"}, {},
        stats=FAKE_STATS, identify_bot=fake_identify_bot,
    )
    check("wrong jsonrpc version is rejected", status == 400)

    # ── Base64 header sentinel ───────────────────────────────────────────────
    check("plain header values pass through",
          decode_header_value("check_bot") == "check_bot")
    check("base64 sentinel is decoded",
          decode_header_value("=?base64?Y2hlY2tfYm90?=") == "check_bot")
    check("undecodable sentinel falls through unchanged",
          decode_header_value("=?base64?!!!?=") == "=?base64?!!!?=")
    status, res = call(
        "tools/call",
        {"name": "check_bot", "arguments": {"bot": "GPTBot"}},
        headers={"mcp-name": "=?base64?Y2hlY2tfYm90?="},
    )
    check("base64-encoded Mcp-Name matches the body", status == 200)

    # ── ARD server card ──────────────────────────────────────────────────────
    card = build_server_card("https://goodbot-badbot.com/mcp")
    check("server card points at the endpoint",
          card["url"] == "https://goodbot-badbot.com/mcp")
    check("server card tool list matches the served tools",
          [t["name"] for t in card["tools"]] == [t["name"] for t in TOOLS])
    blob = json.dumps(card)
    for trap in ("/do-not-crawl", "/honeypot", "/training-data-forbidden",
                 "/no-ai-allowed", "/robots-test"):
        check(f"server card omits honeypot path '{trap}'", trap not in blob)

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
