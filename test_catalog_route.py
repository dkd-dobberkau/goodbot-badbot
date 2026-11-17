"""Route-level test for /bots and /api/bots, through the real ASGI stack.

Run with: python test_catalog_route.py
Exit 0 if all assertions pass, 1 otherwise.

test_catalog.py covers the catalog logic as pure functions. This file covers
what only the routes can do: content negotiation, visit logging, and the
links that announce the catalog (sitemap, llms.txt). Only the DB-backed
calls are stubbed.
"""
import sys

from fastapi.testclient import TestClient

from app import catalog, main

logged: list[str] = []


async def fake_log_visit(pool, path, ua, ip, *, is_honeypot=False, signature_status=None,
                         method=None):
    logged.append(path)


async def fake_catalog():
    measured = catalog.Measurements("GPTBot", "ai", "OpenAI", visits=3, honeypot_hits=1,
                                    spoof_filtered=True)
    return catalog.build_catalog({}, {}, {"GPTBot": measured})


main.log_visit = fake_log_visit
main._get_catalog_cached = fake_catalog

UA = {"User-Agent": "Mozilla/5.0 (compatible; GPTBot/1.2)"}


def main_() -> int:
    failures = 0
    total = 0

    def check(label, got, want):
        nonlocal failures, total
        total += 1
        ok = got == want
        print(("PASS " if ok else "FAIL ") + f"{label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    main.app.state.db_pool = None
    client = TestClient(main.app)

    html_resp = client.get("/bots", headers=UA)
    check("/bots status", html_resp.status_code, 200)
    check("/bots is HTML", html_resp.headers["content-type"].startswith("text/html"), True)
    check("/bots lists the bot", "GPTBot" in html_resp.text, True)

    md_resp = client.get("/bots", headers={**UA, "Accept": "text/markdown"})
    check("/bots as Markdown", md_resp.headers["content-type"].startswith("text/markdown"), True)
    check("Markdown starts with the title", md_resp.text.startswith("# Bot catalog"), True)

    api_resp = client.get("/api/bots", headers=UA)
    check("/api/bots status", api_resp.status_code, 200)
    check("/api/bots keys", sorted(api_resp.json()), ["bots", "summary"])

    check("/bots read is logged", "/bots" in logged, True)
    check("/api/bots read is logged", "/api/bots" in logged, True)

    check("sitemap lists /bots", "https://goodbot-badbot.com/bots<" in client.get("/sitemap.xml").text, True)
    check("llms.txt links /bots", "https://goodbot-badbot.com/bots" in client.get("/llms.txt").text, True)

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main_())
