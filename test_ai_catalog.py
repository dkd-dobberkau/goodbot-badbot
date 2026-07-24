"""Stdlib smoke test for the Agentic Resource Discovery (ARD) manifest builder.

Run with: python test_ai_catalog.py
Exit 0 if all assertions pass, 1 otherwise.

The ARD manifest at /.well-known/ai-catalog.json lets agent-facing registries
index this site's one machine interface (the OpenAPI-described stats API) and
surface it to agents whose question matches a representativeQuery. Reads of the
manifest are logged as their own Discovery-Reads signal, never as a violation.
See dri.es "Agentic Resource Discovery".
"""
import json
import sys

from app.main import build_ai_catalog, ARD_CATALOG_PATHS


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures += 1

    base = "https://goodbot-badbot.com"
    cat = build_ai_catalog(base)

    # ARD 1.0: specVersion + host + entries[].
    check("specVersion is 1.0", cat.get("specVersion") == "1.0")
    check("host has a displayName", bool(cat.get("host", {}).get("displayName")))
    check("has entries array", isinstance(cat.get("entries"), list))
    check("exactly one entry", len(cat["entries"]) == 1)
    entry = cat["entries"][0]

    # Identifier is a URN scoped to the host so registries can dedupe.
    check("identifier is a host-scoped URN",
          entry["identifier"] == "urn:air:goodbot-badbot.com:stats")

    # The entry points at the same OpenAPI description the api-catalog reuses.
    check("entry -> openapi.json", entry["url"] == base + "/openapi.json")
    check("entry openapi type", entry["type"] == "application/openapi+json")
    check("entry has a displayName", bool(entry.get("displayName")))
    check("entry has a description", bool(entry.get("description")))

    # representativeQueries are the registry intent hooks — must be present and
    # topical (mention robots.txt, the site's actual subject).
    queries = entry.get("representativeQueries")
    check("has representativeQueries", isinstance(queries, list) and len(queries) >= 3)
    check("queries are on-topic (robots.txt)",
          any("robots.txt" in q.lower() for q in queries))

    # No honeypot path may ever leak into the manifest — it is an offer, not a
    # trap. Scan for the leading-slash path forms, not bare words: a
    # representativeQuery legitimately names the "honeypot" concept, but no
    # honeypot URL/path may appear.
    blob = json.dumps(cat)
    for trap in ("/do-not-crawl", "/honeypot", "/training-data-forbidden",
                 "/no-ai-allowed", "/robots-test"):
        check(f"manifest omits honeypot path '{trap}'", trap not in blob)

    check("manifest is JSON-serialisable",
          json.loads(blob)["entries"][0]["url"] == base + "/openapi.json")

    # The path whose reads count as the ARD Discovery signal.
    check("ARD_CATALOG_PATHS has the manifest path",
          "/.well-known/ai-catalog.json" in ARD_CATALOG_PATHS)

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
