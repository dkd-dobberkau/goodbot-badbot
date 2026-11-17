"""The client IP must come from Mittwald's proxy, not from the client.

uvicorn runs with --proxy-headers. With --forwarded-allow-ips "*" it takes the
*first* X-Forwarded-For entry, which the client sets itself, so anyone could
pick their own IP: ip_hash, rate limits and spoof detection all trusted it.
These tests run uvicorn's real middleware with the value from the Dockerfile.

Run with: python test_proxy_headers.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

PROXY = "100.125.119.41"  # a peer seen on :8000 in production, 2026-11-17


def dockerfile_allow_ips() -> str:
    cmd = re.search(r"^CMD (\[.*?\])", Path("Dockerfile").read_text(), re.S | re.M).group(1)
    args = json.loads(cmd.replace("\\\n", ""))
    return args[args.index("--forwarded-allow-ips") + 1]


def client_seen(peer: str, forwarded_for: str | None) -> str:
    seen = {}

    async def app(scope, receive, send):
        seen["client"] = scope["client"][0]

    headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    scope = {"type": "http", "client": (peer, 40000), "headers": headers, "scheme": "http"}
    middleware = ProxyHeadersMiddleware(app, trusted_hosts=dockerfile_allow_ips())
    asyncio.run(middleware(scope, None, None))
    return seen["client"]


def main() -> int:
    failures = 0
    total = 0

    def check(label, got, want):
        nonlocal failures, total
        total += 1
        ok = got == want
        print(("PASS " if ok else "FAIL ") + f"{label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    check("Dockerfile does not trust every peer", dockerfile_allow_ips() != "*", True)
    check("normal visitor behind the proxy",
          client_seen(PROXY, "198.51.100.9"), "198.51.100.9")
    check("a client-supplied entry is ignored; the proxy's appended one wins",
          client_seen(PROXY, "203.0.113.77, 198.51.100.9"), "198.51.100.9")
    check("a peer outside the proxy network cannot set its IP",
          client_seen("198.51.100.20", "203.0.113.77"), "198.51.100.20")

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
