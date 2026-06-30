"""Test for the per-URL JWKS fetch lock in app.main._get_jwks.

Proves two properties of _get_jwks:
  1. Per-URL isolation: a slow fetch for one URL must NOT block the
     fetch/cache path for a different URL. (A single global lock would
     serialise them; per-URL locks do not.)
  2. Same-URL dedup: concurrent callers for the same URL still trigger
     exactly one network fetch; later callers read the cache.

The httpx.AsyncClient is replaced with a fake whose .get() blocks on a
per-URL asyncio.Event, so we control fetch ordering deterministically.

Run with: python test_jwks_cache.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import asyncio
import sys

import app.main as appmain

URL_A = "https://a.example/jwks"
URL_B = "https://b.example/jwks"


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def _install_fake_client(gates: dict, fetches: list):
    """Patch appmain.httpx.AsyncClient with a fake whose get() awaits the
    per-URL gate before returning. Returns the original class."""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            await gates[url].wait()
            fetches.append(url)
            return _FakeResp({"keys": [], "_url": url})

    original = appmain.httpx.AsyncClient
    appmain.httpx.AsyncClient = _FakeClient
    return original


def _reset_state():
    appmain._jwks_cache.clear()
    appmain._jwks_locks.clear()


async def _test_per_url_isolation():
    """B must complete while A's fetch is still blocked."""
    _reset_state()
    gates = {URL_A: asyncio.Event(), URL_B: asyncio.Event()}
    fetches: list = []
    original = _install_fake_client(gates, fetches)
    try:
        gates[URL_B].set()  # B can fetch immediately; A stays blocked
        task_a = asyncio.create_task(appmain._get_jwks(URL_A))
        task_b = asyncio.create_task(appmain._get_jwks(URL_B))

        # B must resolve even though A is blocked. With a single global
        # lock this would hang and time out.
        result_b = await asyncio.wait_for(task_b, timeout=1.0)
        assert result_b == {"keys": [], "_url": URL_B}, result_b
        assert task_a.cancel() is not None  # A still pending -> cancellable
        await asyncio.gather(task_a, return_exceptions=True)
        return True
    except (AssertionError, asyncio.TimeoutError) as e:
        print(f"  isolation failure: {e!r}")
        return False
    finally:
        appmain.httpx.AsyncClient = original


async def _test_same_url_dedup():
    """Two concurrent callers for the same URL -> exactly one fetch."""
    _reset_state()
    gates = {URL_A: asyncio.Event()}
    fetches: list = []
    original = _install_fake_client(gates, fetches)
    try:
        task1 = asyncio.create_task(appmain._get_jwks(URL_A))
        task2 = asyncio.create_task(appmain._get_jwks(URL_A))
        await asyncio.sleep(0)  # let both reach the lock
        gates[URL_A].set()
        r1, r2 = await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)
        assert r1 == r2 == {"keys": [], "_url": URL_A}, (r1, r2)
        assert fetches.count(URL_A) == 1, f"expected 1 fetch, got {fetches.count(URL_A)}"
        return True
    except (AssertionError, asyncio.TimeoutError) as e:
        print(f"  dedup failure: {e!r}")
        return False
    finally:
        appmain.httpx.AsyncClient = original


def main() -> int:
    failures = 0

    def check(label, ok):
        nonlocal failures
        print(("PASS " if ok else "FAIL ") + label)
        if not ok:
            failures += 1

    check("per-URL isolation: slow A does not block B", asyncio.run(_test_per_url_isolation()))
    check("same-URL dedup: concurrent callers -> one fetch", asyncio.run(_test_same_url_dedup()))

    total = 2
    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
