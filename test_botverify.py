"""Test for app/botverify.py, the client of verify.goodbot-badbot.com.

The HTTP client is a fake that answers from a table, so the tests check what
is asked, what is cached and how failures end up, without the network.

Run with: python test_botverify.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import asyncio
import sys

from app import botverify

# The shape of GET /v1/bots: a list of bot objects.
BOTS = [{"id": "gptbot"}, {"id": "claudebot"}, {"id": "google-cloudvertexbot"}]


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


class _FakeClient:
    """Answers GETs from `routes` (path -> (status, json) or an exception)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, url, params=None):
        path = url.split("verify.example", 1)[1]
        self.calls.append((path, dict(params or {})))
        answer = self.routes[path]
        if isinstance(answer, Exception):
            raise answer
        return _Resp(*answer)


def fresh(routes):
    client = _FakeClient(routes)
    return botverify.Verifier("https://verify.example", client=client), client


def verify_route(result):
    return (200, {"result": result})


async def main() -> int:
    failures = 0
    total = 0

    def check(label, got, want):
        nonlocal failures, total
        total += 1
        ok = got == want
        print(("PASS " if ok else "FAIL ") + f"{label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    v, client = fresh({"/v1/bots": (200, BOTS), "/v1/verify": verify_route("confirmed")})
    check("a known bot is asked about", await v.verdict("66.249.66.1", "gptbot"), "confirmed")
    check("the query names ip and bot", client.calls[-1], ("/v1/verify", {"ip": "66.249.66.1", "bot": "gptbot"}))
    calls = len(client.calls)
    await v.verdict("66.249.66.1", "gptbot")
    check("the same ip and bot are answered from the cache", len(client.calls), calls)

    check("a key bot-verify does not know is not asked", await v.verdict("1.2.3.4", "devin"), None)
    check("no verify call for an unknown key", [c for c in client.calls if c[1].get("bot") == "devin"], [])
    check("no bot key, no question", await v.verdict("1.2.3.4", None), None)

    v, client = fresh({"/v1/bots": (200, BOTS), "/v1/verify": verify_route("refuted")})
    check("goodbot's cloudvertexbot is bot-verify's google-cloudvertexbot",
          await v.verdict("1.2.3.4", "cloudvertexbot"), "refuted")
    check("the alias is sent", client.calls[-1][1]["bot"], "google-cloudvertexbot")

    for label, answer in [
        ("rate limited", (429, {"error": {"code": "rate_limited"}})),
        ("server error", (500, {})),
        ("an unexpected result", verify_route("maybe")),
        ("a network error", OSError("down")),
    ]:
        v, client = fresh({"/v1/bots": (200, BOTS), "/v1/verify": answer})
        check(f"{label} gives no verdict", await v.verdict("1.2.3.4", "gptbot"), None)
        client.routes["/v1/verify"] = verify_route("confirmed")
        check(f"{label} is not cached", await v.verdict("1.2.3.4", "gptbot"), "confirmed")

    v, client = fresh({"/v1/bots": OSError("down"), "/v1/verify": verify_route("confirmed")})
    check("without the bot list nothing is asked", await v.verdict("1.2.3.4", "gptbot"), None)
    client.routes["/v1/bots"] = (200, BOTS)
    v._bots_retry_at = 0
    check("the bot list is fetched again later", await v.verdict("1.2.3.4", "gptbot"), "confirmed")

    check("an empty base URL turns the client off",
          await botverify.Verifier("", client=_FakeClient({})).verdict("1.2.3.4", "gptbot"), None)

    v, _ = fresh({"/v1/bots": (200, BOTS), "/v1/verify": verify_route("not_checkable")})
    v.max_cache_entries = 2
    for i in range(5):
        await v.verdict(f"10.0.0.{i}", "gptbot")
    check("the cache stays bounded", len(v._cache) <= 2, True)

    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
