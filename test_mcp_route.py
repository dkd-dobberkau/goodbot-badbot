"""Route-level test for /mcp, through the real ASGI stack.

Run with: python test_mcp_route.py
Exit 0 if all assertions pass, 1 otherwise.

test_mcp.py covers the protocol logic as a pure function. This file covers
what only the route can do: Origin rejection, the body cap, the 405 for
GET/DELETE, visit logging, and the fact that the endpoint is announced in the
ARD manifest / llms.txt / agents.md but deliberately *not* in the homepage
Link header. Only the two DB-backed calls are stubbed, so middleware, routing
and JSON serialisation are exercised for real.
"""
import sys

from fastapi.testclient import TestClient

from app import main
from app.mcp import PROTOCOL_VERSION

logged: list[str] = []


async def fake_log_visit(pool, path, ua, ip, *, is_honeypot=False, signature_status=None):
    logged.append(path)


async def fake_stats():
    return {
        "summary": [{"bot_name": "GPTBot", "operator": "OpenAI", "total_visits": 3,
                     "violations": 2, "verified_visits": 0, "last_seen": None}],
        "total_violations": 2, "total_bots_seen": 1, "total_verified": 0,
        "total_discovery_reads": 4,
    }


main.log_visit = fake_log_visit
main._get_stats_cached = fake_stats

BASE_HEADERS = {
    "MCP-Protocol-Version": PROTOCOL_VERSION,
    "Mcp-Method": "tools/list",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; GPTBot/1.2)",
}
TOOLS_LIST_BODY = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def main_() -> int:
    failures = 0

    def check(label, cond, detail=""):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if not cond else ""))
        if not cond:
            failures += 1

    # TestClient without entering lifespan: nothing on these paths touches the
    # DB pool once log_visit and _get_stats_cached are stubbed.
    client = TestClient(main.app)
    main.app.state.db_pool = None

    r = client.post("/mcp", headers=BASE_HEADERS, json=TOOLS_LIST_BODY)
    check("tools/list over HTTP -> 200", r.status_code == 200, r.text[:120])
    check("content-type is application/json",
          r.headers["content-type"].startswith("application/json"))
    check("responses are not cached", r.headers.get("cache-control") == "no-store")
    check("security headers still applied", "content-security-policy" in r.headers)
    check("tools are returned",
          [t["name"] for t in r.json()["result"]["tools"]]
          == ["get_compliance_stats", "check_bot"])
    check("the call is logged under /mcp", logged == ["/mcp"], str(logged))

    r = client.post("/mcp", headers={**BASE_HEADERS, "Mcp-Method": "tools/call",
                                     "Mcp-Name": "check_bot"},
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": "check_bot",
                                     "arguments": {"bot": "GPTBot"},
                                     "_meta": {"io.modelcontextprotocol/protocolVersion":
                                               PROTOCOL_VERSION}}})
    check("tools/call over HTTP -> 200", r.status_code == 200, r.text[:120])
    check("check_bot verdict survives serialisation",
          r.json()["result"]["structuredContent"]["verdict"] == "bad_bot")

    # Revision 2026-07-28 has no GET stream and no session teardown, but a GET
    # probe is still the clearest evidence an agent guessed the path exists.
    r = client.get("/mcp", headers={"User-Agent": "curl/8"})
    check("GET /mcp -> 405", r.status_code == 405, str(r.status_code))
    check("GET /mcp sets Allow: POST", r.headers.get("allow") == "POST")
    check("GET /mcp is logged too", logged.count("/mcp") == 2, str(logged))
    r = client.request("DELETE", "/mcp", headers={"User-Agent": "curl/9"})
    check("DELETE /mcp -> 405", r.status_code == 405)

    # DNS-rebinding guard: absent Origin is fine (non-browser clients send
    # none), a foreign one is not.
    r = client.post("/mcp", headers={**BASE_HEADERS, "Origin": "https://evil.example"},
                    json=TOOLS_LIST_BODY)
    check("foreign Origin -> 403", r.status_code == 403, str(r.status_code))
    r = client.post("/mcp", headers={**BASE_HEADERS, "Origin": main.SITE_BASE_URL},
                    json=TOOLS_LIST_BODY)
    check("own Origin allowed", r.status_code == 200)

    r = client.post("/mcp", headers=BASE_HEADERS, content=b"{not json")
    check("malformed JSON -> 400 parse error",
          r.status_code == 400 and r.json()["error"]["code"] == -32700, r.text[:120])
    r = client.post("/mcp", headers=BASE_HEADERS,
                    content=b"x" * (main.MAX_MCP_BODY_BYTES + 10))
    check("oversized body -> 413", r.status_code == 413, str(r.status_code))

    r = client.post("/mcp", headers={**BASE_HEADERS, "Mcp-Method": "resources/read"},
                    json={"jsonrpc": "2.0", "id": 9, "method": "resources/read"})
    check("unknown method -> 404 + -32601",
          r.status_code == 404 and r.json()["error"]["code"] == -32601, r.text[:120])
    r = client.post("/mcp", headers=BASE_HEADERS,
                    json={"jsonrpc": "2.0", "method": "tools/list"})
    check("notification -> 202 with no body",
          r.status_code == 202 and not r.content, str(r.status_code))

    # Announced where it should be...
    r = client.get("/.well-known/ai-catalog.json", headers={"User-Agent": "probe/1"})
    check("ARD manifest carries the MCP entry",
          r.status_code == 200
          and len(r.json()["entries"]) == 2
          and r.json()["entries"][1]["data"]["url"].endswith("/mcp"))
    r = client.get("/llms.txt", headers={"User-Agent": "probe/2"})
    check("llms.txt names /mcp", "/mcp" in r.text)
    r = client.get("/.well-known/agents.md", headers={"User-Agent": "probe/3"})
    check("agents.md names /mcp", "/mcp" in r.text)
    check("agents.md no longer denies having an MCP server",
          "There is no MCP server" not in r.text)

    # ...and deliberately absent where it should not be, so "guessed the path"
    # stays a distinguishable case in the data.
    r = client.get("/", headers={"User-Agent": "probe/4"})
    check("homepage Link header omits /mcp",
          "/mcp" not in r.headers.get("link", ""), r.headers.get("link", ""))

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main_())
