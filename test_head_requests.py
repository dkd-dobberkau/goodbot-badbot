"""Regression test: HEAD must work on every GET route.

Run with: python test_head_requests.py
Exit 0 if all assertions pass, 1 otherwise.

Starlette 1.x stopped adding HEAD implicitly to GET routes, which silently
turned the whole site into a 405 for HEAD — including /robots.txt and the
honeypots, so a crawler could probe a Disallow'd path with HEAD and never be
recorded. _allow_head_on_get_routes() puts HEAD back centrally; this test
pins that behaviour so a Starlette upgrade or a new route cannot regress it.
"""
import sys

from fastapi.testclient import TestClient

from app import main

logged: list[tuple[str, bool, str | None]] = []


async def fake_log_visit(pool, path, ua, ip, *, is_honeypot=False, signature_status=None,
                         method=None):
    logged.append((path, is_honeypot, method))


async def fake_stats():
    return {"summary": [], "recent_violations": [], "total_violations": 0,
            "total_bots_seen": 0, "total_verified": 0, "discovery_reads": [],
            "total_discovery_reads": 0}


main.log_visit = fake_log_visit
main._get_stats_cached = fake_stats

# One representative path per category the site serves.
GET_PATHS = [
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/AGENTS.md",
    "/agents.md",
    "/.well-known/agents.md",
    "/.well-known/api-catalog",
    "/.well-known/ai-catalog.json",
    "/.well-known/http-message-signatures-directory",
    "/openapi.json",
    "/api/stats",
    "/api/version",
    "/favicon.ico",
    "/blog",
    "/facts",
]

HONEYPOT_PATH = "/honeypot/probe"


def main_() -> int:
    failures = 0

    def check(label, cond, detail=""):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if not cond else ""))
        if not cond:
            failures += 1

    client = TestClient(main.app)
    main.app.state.db_pool = None

    check("some routes were patched", len(main.HEAD_ENABLED_PATHS) > 10,
          str(len(main.HEAD_ENABLED_PATHS)))

    for path in GET_PATHS:
        r = client.head(path, headers={"User-Agent": f"head-probe{path}"})
        check(f"HEAD {path} -> 200", r.status_code == 200, str(r.status_code))
        # HTTP requires HEAD to carry no body but the headers GET would send.
        check(f"HEAD {path} has no body", not r.content, f"{len(r.content)} bytes")

    # GET must be unaffected.
    for path in ("/", "/robots.txt", "/api/stats"):
        r = client.get(path, headers={"User-Agent": "get-probe"})
        check(f"GET {path} still 200 with a body",
              r.status_code == 200 and bool(r.content), str(r.status_code))

    # The point of the fix: a HEAD to a Disallow'd path is still a violation,
    # and the method is recorded so the feed can label it.
    logged.clear()
    r = client.head(HONEYPOT_PATH, headers={"User-Agent": "sneaky-head-bot/1.0"})
    check("HEAD on a honeypot -> 200 (not 405)", r.status_code == 200, str(r.status_code))
    check("HEAD on a honeypot is logged as a violation with method",
          logged == [(HONEYPOT_PATH, True, "HEAD")], str(logged))

    # Every logged visit carries the method that produced it.
    logged.clear()
    client.get("/llms.txt", headers={"User-Agent": "method-bot/1.0"})
    check("GET records method=GET", logged == [("/llms.txt", False, "GET")], str(logged))

    # Dedup is keyed on method: a bot that HEAD-probes a file and then GETs it
    # within the TTL must produce BOTH rows, or the probe would silently
    # swallow the read (and the whole read/probe split would be a lie).
    logged.clear()
    main._visit_dedup.clear()
    ua = {"User-Agent": "probe-then-read-bot/1.0"}
    client.head("/llms.txt", headers=ua)
    client.get("/llms.txt", headers=ua)
    check("HEAD then GET on the same path logs both",
          logged == [("/llms.txt", False, "HEAD"), ("/llms.txt", False, "GET")], str(logged))

    # ...but a repeat of the same method within the TTL is still deduped.
    logged.clear()
    client.get("/llms.txt", headers=ua)
    check("repeat GET within the TTL is still deduped", logged == [], str(logged))

    # POST-only routes must NOT have gained HEAD.
    r = client.head("/mcp", headers={"User-Agent": "head-probe-mcp"})
    check("HEAD /mcp -> 405 (POST-only endpoint)", r.status_code == 405, str(r.status_code))

    # Methods the site never serves stay rejected.
    r = client.request("PUT", "/robots.txt", headers={"User-Agent": "put-probe"})
    check("PUT /robots.txt still 405", r.status_code == 405, str(r.status_code))

    # Adding HEAD to a route makes FastAPI emit two operations sharing one
    # operationId, which is invalid OpenAPI — and this site advertises
    # /openapi.json as its machine interface from two catalogs. The served
    # document must document GET only and keep every id unique.
    spec = main.app.openapi()
    operations = [op.get("operationId")
                  for item in spec["paths"].values() for op in item.values()]
    check("openapi operationIds are unique",
          len(operations) == len(set(operations)),
          f"{len(operations)} ops / {len(set(operations))} ids")
    documented = sorted({m for item in spec["paths"].values() for m in item})
    check("openapi documents GET only (HEAD is implied)",
          documented == ["get"], str(documented))
    r = client.get("/openapi.json", headers={"User-Agent": "schema-probe"})
    check("served /openapi.json matches", r.status_code == 200
          and sorted({m for i in r.json()["paths"].values() for m in i}) == ["get"])

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main_())
