"""Test for Web Bot Auth incoming signature verification.

Exercises _verify_request_signature against draft-ietf-webbotauth-httpsig-protocol-01:
a cryptographically valid signature is only 'verified' when it covers
@authority or @target-uri (§5.2) plus the Signature-Agent member keyed to
its own label (§5.2.1), and when the key comes from the directory that
member names (§5.2.2). Keys are matched by kid or, failing that, by their
RFC 7638 thumbprint (§5.5).

Run with: python test_signature_verification.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import asyncio
import base64
import datetime
import sys
import time

import http_sfv
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from http_message_signatures import (
    HTTPMessageSigner,
    HTTPMessageVerifier,
    HTTPSignatureKeyResolver,
    algorithms,
)

import app.main as appmain

KID = "test-key-1"
AGENT_URL = "https://agent.example/jwks"
OTHER_AGENT_URL = "https://other.example/jwks"
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
    """Legacy form: Signature-Agent as a bare sf-string, signed via the
    library. Always carries the header so the JWKS path runs regardless of
    whether signature-agent is part of the covered set."""
    agent_header = str(http_sfv.Item(AGENT_URL))  # sf-string, e.g. "https://..."
    req = httpx.Request("GET", REQUEST_URL, headers={"signature-agent": agent_header})
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=_SigningResolver(private_key),
    )
    signer.sign(req, key_id=KID, covered_component_ids=covered)
    return _FakeRequest("GET", REQUEST_URL, dict(req.headers))


def _signed_request_dictionary_form(
    private_key: Ed25519PrivateKey,
    *,
    target_component: str = "@authority",
    sign_agent_member: bool = True,
    agent_header: str = f'sig1="{AGENT_URL}"',
    agent_header_after_signing: str | None = None,
    keyid: str = KID,
) -> _FakeRequest:
    """Current form: Signature-Agent as an sf-dictionary whose member is
    keyed to the signature label (sig1) and covered as
    "signature-agent";key="sig1".

    The signature base is assembled by hand per RFC 9421 §2.5 rather than via
    HTTPMessageSigner, so the test does not share the library's view of
    `;key=` resolution (2.x signed the whole field value)."""
    member_value = http_sfv.Dictionary()
    member_value.parse(agent_header.encode())
    target_values = {
        "@authority": "goodbot-badbot.com",
        "@target-uri": REQUEST_URL,
        "@method": "GET",
    }
    components = [f'"{target_component}"']
    base_lines = [f'"{target_component}": {target_values[target_component]}']
    if sign_agent_member:
        components.append('"signature-agent";key="sig1"')
        base_lines.append(f'"signature-agent";key="sig1": {member_value["sig1"]}')
    created = int(time.time())
    params = (
        f'({" ".join(components)});created={created};keyid="{keyid}"'
        f';alg="ed25519";expires={created + 300};tag="web-bot-auth"'
    )
    base_lines.append(f'"@signature-params": {params}')
    signature = private_key.sign("\n".join(base_lines).encode())
    return _FakeRequest("GET", REQUEST_URL, {
        "signature-agent": agent_header_after_signing or agent_header,
        "signature-input": f"sig1={params}",
        "signature": f"sig1=:{base64.b64encode(signature).decode()}:",
    })


def _official_vector_verifies() -> bool:
    """draft-ietf-webbotauth-httpsig-protocol-01 Appendix E.2.1, verified by
    the library directly. Guards the pinned http-message-signatures major
    against regressing on ;key= member resolution. Goes around
    _verify_request_signature because the vector's `created` is in 2025 and
    the production age limit would reject it."""
    public_key = Ed25519PublicKey.from_public_bytes(
        base64.urlsafe_b64decode("JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs=")
    )

    class _VectorResolver(HTTPSignatureKeyResolver):
        def resolve_public_key(self, key_id: str):
            return public_key

    headers = {
        "signature-agent": 'sig2="https://signature-agent.test"',
        "signature-input": (
            'sig2=("@authority" "signature-agent";key="sig2");created=1735689600'
            ';keyid="poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U";alg="ed25519"'
            ';expires=4889289600'
            ';nonce="n9p433xm+NJ3ph3upfBIGmsuwHw387YV7Q/F+6BSpGCVjYCqQw6rznNA8PVVLySrAWsv0hQtFioQb6E1YsauiA=="'
            ';tag="web-bot-auth"'
        ),
        "signature": (
            "sig2=:CGokAoY/FrPpyuzTe1Fb2kLTAH9Idw6qSFd1+D77r1firsMRCxeuLu5e6O+ek3zQgDMAzjiXtLVfqE00xnABCQ==:"
        ),
    }
    verifier = HTTPMessageVerifier(
        signature_algorithm=algorithms.ED25519, key_resolver=_VectorResolver()
    )
    try:
        verifier.verify(
            httpx.Request("GET", "https://example.com/", headers=headers),
            max_age=datetime.timedelta(days=365 * 100),
        )
        return True
    except Exception:
        return False


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

    def verify(request):
        return asyncio.run(appmain._verify_request_signature(request))

    private_key = Ed25519PrivateKey.generate()
    raw_pub = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    signing_jwk = {"kty": "OKP", "crv": "Ed25519", "x": _b64url(raw_pub)}
    unrelated_jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": KID,
        "x": _b64url(
            Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ),
    }
    # Pin JWKS resolution per URL so no network is touched. AGENT_URL holds
    # the signing key; OTHER_AGENT_URL holds an unrelated key under the same kid.
    directories = {
        AGENT_URL: {"keys": [{**signing_jwk, "kid": KID}]},
        OTHER_AGENT_URL: {"keys": [unrelated_jwk]},
    }
    original_get_jwks = appmain._get_jwks

    async def fake_get_jwks(url: str):
        return directories.get(url)

    appmain._get_jwks = fake_get_jwks
    try:
        # Legacy sf-string Signature-Agent, signed via the library.
        check("legacy: @authority + signature-agent covered",
              verify(_signed_request(private_key, ("@authority", "signature-agent"))),
              "verified")
        check("legacy: signature-agent not covered",
              verify(_signed_request(private_key, ("@authority", "@method"))),
              "failed")
        check("legacy: neither @authority nor @target-uri covered",
              verify(_signed_request(private_key, ("@method", "signature-agent"))),
              "failed")

        # Dictionary form (pre-patch every one of these came back 'failed',
        # which is how all of AhrefsBot's signed traffic was logged).
        check("dictionary: member covered",
              verify(_signed_request_dictionary_form(private_key)),
              "verified")
        check("dictionary: member not covered",
              verify(_signed_request_dictionary_form(private_key, sign_agent_member=False)),
              "failed")
        check("dictionary: member swapped after signing",
              verify(_signed_request_dictionary_form(
                  private_key, agent_header_after_signing='sig1="https://attacker.example/jwks"')),
              "failed")

        # §5.2: @target-uri satisfies the binding as well as @authority does.
        check("dictionary: @target-uri instead of @authority",
              verify(_signed_request_dictionary_form(private_key, target_component="@target-uri")),
              "verified")

        # §5.2.2: the key must come from the member the signature covers,
        # not from any directory listed in the header.
        check("dictionary: key only in a member the signature does not cover",
              verify(_signed_request_dictionary_form(
                  private_key,
                  agent_header=f'sig1="{OTHER_AGENT_URL}", other="{AGENT_URL}"')),
              "failed")

        # §5.2.1: a member that carries parameters MUST be ignored.
        check("dictionary: covered member carries parameters",
              verify(_signed_request_dictionary_form(
                  private_key, agent_header=f'sig1="{AGENT_URL}";x=1')),
              "failed")

        # §5.5: a directory key without kid is selected by its thumbprint.
        directories[AGENT_URL] = {"keys": [signing_jwk]}
        thumbprint = appmain._jwk_thumbprint(signing_jwk)
        check("dictionary: key without kid, keyid is its thumbprint",
              verify(_signed_request_dictionary_form(private_key, keyid=thumbprint)),
              "verified")
        check("thumbprint of the RFC 9421 B.1.4 test key matches the draft's keyid",
              appmain._jwk_thumbprint(
                  {"kty": "OKP", "crv": "Ed25519", "x": "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"}),
              "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U")
    finally:
        appmain._get_jwks = original_get_jwks

    check("official vector E.2.1 verifies with the pinned library",
          _official_vector_verifies(), True)

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
