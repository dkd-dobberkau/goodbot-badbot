"""Test for Web Bot Auth incoming signature verification.

Exercises the covered-components check in _verify_request_signature: a
cryptographically valid signature is only accepted as 'verified' when it
covers BOTH @authority and signature-agent (Web Bot Auth draft §4).
A signature that omits either component must come back 'failed', even
though it verifies cryptographically.

Run with: python test_signature_verification.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import asyncio
import base64
import sys

import http_sfv
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from http_message_signatures import (
    HTTPMessageSigner,
    HTTPSignatureKeyResolver,
    algorithms,
)

import app.main as appmain

KID = "test-key-1"
AGENT_URL = "https://agent.example/jwks"
REQUEST_URL = "https://goodbot-badbot.com/robots.txt"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


class _SigningResolver(HTTPSignatureKeyResolver):
    """Hands the signer the private key for our single test kid."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._priv = private_key

    def resolve_private_key(self, key_id: str):
        return self._priv


class _FakeRequest:
    """Minimal stand-in for starlette.Request: only the attributes
    _verify_request_signature touches (headers, method, url)."""

    def __init__(self, method: str, url: str, headers: dict):
        self.method = method
        self.url = url
        self.headers = headers


def _signed_request(private_key: Ed25519PrivateKey, covered: tuple[str, ...]) -> _FakeRequest:
    """Build a request signed over `covered`, always carrying a valid
    Signature-Agent header so the JWKS-resolution path runs regardless of
    whether signature-agent is part of the covered set."""
    agent_header = str(http_sfv.Item(AGENT_URL))  # sf-string, e.g. "https://..."
    req = httpx.Request("GET", REQUEST_URL, headers={"signature-agent": agent_header})
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=_SigningResolver(private_key),
    )
    signer.sign(req, key_id=KID, covered_component_ids=covered)
    return _FakeRequest("GET", REQUEST_URL, dict(req.headers))


def main() -> int:
    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got == want
        print(("PASS " if ok else "FAIL ") + f"{label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    private_key = Ed25519PrivateKey.generate()
    raw_pub = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    jwks = {"keys": [{"kty": "OKP", "crv": "Ed25519", "kid": KID, "x": _b64url(raw_pub)}]}

    # Pin JWKS resolution so no network is touched; the public key always
    # matches the private key the signer used.
    original_get_jwks = appmain._get_jwks

    async def fake_get_jwks(url: str):
        return jwks

    appmain._get_jwks = fake_get_jwks
    try:
        # Both required components covered -> verified.
        req_a = _signed_request(private_key, ("@authority", "signature-agent"))
        check(
            "both @authority + signature-agent covered",
            asyncio.run(appmain._verify_request_signature(req_a)),
            "verified",
        )

        # @authority covered but signature-agent NOT -> failed.
        # (Pre-patch this verified cryptographically and was wrongly accepted.)
        req_b = _signed_request(private_key, ("@authority", "@method"))
        check(
            "signature-agent not covered",
            asyncio.run(appmain._verify_request_signature(req_b)),
            "failed",
        )

        # signature-agent covered but @authority NOT -> failed.
        req_c = _signed_request(private_key, ("@method", "signature-agent"))
        check(
            "@authority not covered",
            asyncio.run(appmain._verify_request_signature(req_c)),
            "failed",
        )
    finally:
        appmain._get_jwks = original_get_jwks

    total = 3
    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
