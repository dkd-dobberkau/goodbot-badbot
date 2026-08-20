"""Stdlib-only test for the /.well-known/mcp-server discovery manifest.

Run with: python test_mcp_manifest.py
Exit 0 if all assertions pass, 1 otherwise.

Conformance target is draft-serra-mcp-discovery-uri-04, section 6. That draft is
an individual Internet-Draft with no formal IETF standing and it expires in
September 2026 — which is exactly why these assertions are pinned here rather
than trusted to memory. If the draft dies or changes, this test is the thing
that says so.
"""
import sys

from app.mcp import PROTOCOL_VERSION, build_mcp_manifest

# Section 6.2 — MUST be present for the manifest to be valid at all.
REQUIRED_FIELDS = ("mcp_version", "name", "endpoint", "transport")
# Section 6.3 — SHOULD be present. We claim all four, so all four are asserted.
RECOMMENDED_FIELDS = ("description", "auth", "capabilities", "trust_class")

VALID_TRANSPORTS = {"http", "sse", "stdio"}
VALID_CAPABILITIES = {"tools", "resources", "prompts"}
VALID_TRUST_CLASSES = {"public", "sandbox", "enterprise", "regulated"}


def main() -> int:
    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got == want
        print(f"{'PASS' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    def check_true(label, cond):
        nonlocal failures
        print(f"{'PASS' if cond else 'FAIL'} {label}")
        if not cond:
            failures += 1

    m = build_mcp_manifest()

    for field in REQUIRED_FIELDS:
        check_true(f"required field present: {field}", bool(m.get(field)))
    for field in RECOMMENDED_FIELDS:
        check_true(f"recommended field present: {field}", field in m)

    check_true("transport is a valid enum value", m["transport"] in VALID_TRANSPORTS)
    check_true("trust_class is a valid enum value", m["trust_class"] in VALID_TRUST_CLASSES)
    check_true("capabilities are valid enum values",
               set(m["capabilities"]) <= VALID_CAPABILITIES)

    # The manifest must describe *this* server, not a plausible one. Every claim
    # below is checked against what the MCP implementation actually does.
    check("mcp_version matches what the server speaks", m["mcp_version"], PROTOCOL_VERSION)
    check("endpoint is the real MCP route", m["endpoint"], "https://goodbot-badbot.com/mcp")
    # The server advertises {"tools": {}} and nothing else; claiming resources or
    # prompts here would be advertising an interface that does not exist.
    check("capabilities claim tools only", m["capabilities"], ["tools"])

    # Section 6.3 auth: an open server declares required=false, methods=["none"].
    check("auth declares no authentication", m["auth"], {"required": False, "methods": ["none"]})

    check_true("endpoint and docs are absolute https URLs",
               m["endpoint"].startswith("https://") and m["docs"].startswith("https://"))

    # A manifest that cannot be serialised is not a manifest.
    import json
    try:
        json.dumps(m)
        check_true("manifest is JSON-serialisable", True)
    except (TypeError, ValueError) as exc:
        print(f"FAIL manifest is JSON-serialisable: {exc}")
        failures += 1

    total = len(REQUIRED_FIELDS) + len(RECOMMENDED_FIELDS) + 9
    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
