"""Stdlib smoke test for the RFC 9264 API-catalog linkset builder.

Run with: python test_api_catalog.py
Exit 0 if all assertions pass, 1 otherwise.

The catalog advertises the site's one genuinely useful machine endpoint
(/api/stats) plus its OpenAPI description, so an agent can discover the
public data API without scraping HTML. Reads of the catalog are logged as
a Discovery-Reads signal (an offer taken up), never as a violation.
"""
import json
import sys

from app.main import build_api_catalog, API_CATALOG_PATHS


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures += 1

    base = "https://goodbot-badbot.com"
    cat = build_api_catalog(base)

    # RFC 9264: a "linkset" member holding an array of context objects.
    check("has linkset array", isinstance(cat.get("linkset"), list))
    check("exactly one context object", len(cat["linkset"]) == 1)
    ctx = cat["linkset"][0]

    check("anchor is the site root", ctx["anchor"] == base + "/")

    # service-desc (RFC 8631) points at the OpenAPI description.
    desc = ctx["service-desc"][0]
    check("service-desc -> openapi.json", desc["href"] == base + "/openapi.json")
    check("service-desc openapi media type",
          desc["type"] == "application/vnd.oai.openapi+json")

    # service-doc points at the human/LLM-oriented prose.
    doc = ctx["service-doc"][0]
    check("service-doc -> llms.txt", doc["href"] == base + "/llms.txt")
    check("service-doc markdown type", doc["type"] == "text/markdown")

    # item is the actual data endpoint being catalogued.
    item = ctx["item"][0]
    check("item -> /api/stats", item["href"] == base + "/api/stats")
    check("item json type", item["type"] == "application/json")
    check("item has a title", bool(item.get("title")))

    # No honeypot path may ever leak into the catalog — the catalog is an
    # offer, not a trap. Serialise and scan the whole payload.
    blob = json.dumps(cat)
    for trap in ("do-not-crawl", "honeypot", "training-data-forbidden",
                 "no-ai-allowed", "robots-test"):
        check(f"catalog omits honeypot '{trap}'", trap not in blob)

    check("catalog is JSON-serialisable", json.loads(blob)["linkset"][0]["anchor"] == base + "/")

    # The paths whose reads count as catalog Discovery signal.
    check("API_CATALOG_PATHS has the catalog path",
          "/.well-known/api-catalog" in API_CATALOG_PATHS)
    check("API_CATALOG_PATHS has the openapi path",
          "/openapi.json" in API_CATALOG_PATHS)

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
