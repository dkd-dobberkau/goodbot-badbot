"""Stdlib-only test: the curl example we publish must actually work.

Run with: python test_documented_mcp_call.py
Exit 0 if all assertions pass, 1 otherwise.

llms.txt and agents.md both carry a worked `curl` call for the MCP endpoint.
Documented examples rot silently — a header renamed in the dispatcher leaves
the docs confidently wrong. So this test does not check that the example
*looks* right: it parses the published text, reconstructs the request from it,
and feeds that to the same handle_rpc() the live route calls.
"""
import json
import re
import shlex
import sys

from app.main import AGENTS_MD, LLMS_TXT
from app.mcp import PROTOCOL_VERSION, handle_rpc

# Minimal stats payload — this test is about the request, not the answer.
FAKE_STATS = {
    "summary": [], "total_violations": 0, "total_bots_seen": 0,
    "total_verified": 0, "total_discovery_reads": 0,
}


def fake_identify_bot(user_agent: str):
    return None, None, None


def parse_curl(text: str):
    """Pull the fenced curl example out of a document and destructure it."""
    match = re.search(r"```\n(curl .*?)\n```", text, re.S)
    if match is None:
        return None
    # Join shell line continuations, then split the way a shell would so
    # quoting bugs in the published snippet surface here.
    command = match.group(1).replace("\\\n", " ")
    argv = shlex.split(command)
    headers, body, method, url = {}, None, "GET", None
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "-H":
            name, _, value = argv[i + 1].partition(":")
            headers[name.strip().lower()] = value.strip()
            i += 2
        elif token == "-d":
            body = argv[i + 1]
            i += 2
        elif token == "-X":
            method = argv[i + 1]
            i += 2
        else:
            if token.startswith("http"):
                url = token
            i += 1
    return {"headers": headers, "body": body, "http_method": method, "url": url}


def main() -> int:
    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got == want
        print(f"{'PASS' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    for name, doc in (("llms.txt", LLMS_TXT), ("agents.md", AGENTS_MD)):
        parsed = parse_curl(doc)
        if parsed is None:
            print(f"FAIL {name}: no fenced curl example found")
            failures += 1
            continue

        check(f"{name}: posts", parsed["http_method"], "POST")
        check(f"{name}: targets the MCP endpoint", parsed["url"],
              "https://goodbot-badbot.com/mcp")
        # The spec requires the client to accept both content types.
        accept = parsed["headers"].get("accept", "")
        check(f"{name}: Accept lists both content types",
              ("application/json" in accept and "text/event-stream" in accept), True)
        # A stale version string in the docs is exactly the rot this catches.
        check(f"{name}: advertises the version the server speaks",
              parsed["headers"].get("mcp-protocol-version"), PROTOCOL_VERSION)

        body = json.loads(parsed["body"])
        check(f"{name}: Mcp-Method matches the body method",
              parsed["headers"].get("mcp-method"), body.get("method"))

        # The real assertion: run the documented request through the dispatcher.
        status, response = handle_rpc(
            body, parsed["headers"], stats=FAKE_STATS, identify_bot=fake_identify_bot
        )
        check(f"{name}: documented call is accepted", status, 200)
        check(f"{name}: response carries a result, not an error",
              "error" in (response or {}), False)
        tools = [t["name"] for t in (response or {}).get("result", {}).get("tools", [])]
        check(f"{name}: returns the advertised tools", sorted(tools),
              ["check_bot", "get_compliance_stats"])

    # Dropping any required header must fail loudly *and* usefully: the message
    # has to name the whole requirement, since a stateless protocol gives the
    # caller no handshake in which to discover it.
    parsed = parse_curl(LLMS_TXT)
    body = json.loads(parsed["body"])
    for dropped in ("mcp-protocol-version", "mcp-method"):
        headers = {k: v for k, v in parsed["headers"].items() if k != dropped}
        status, response = handle_rpc(
            body, headers, stats=FAKE_STATS, identify_bot=fake_identify_bot
        )
        check(f"missing {dropped}: rejected with 400", status, 400)
        message = response["error"]["message"]
        check(f"missing {dropped}: error names both required headers",
              ("MCP-Protocol-Version" in message and "Mcp-Method" in message), True)
        check(f"missing {dropped}: error points at the worked example",
              "llms.txt" in message, True)

    total = 2 * 8 + 2 * 3
    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
