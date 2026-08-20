"""Stdlib-only test for the Atom feed.

Run with: python test_feed.py
Exit 0 if all assertions pass, 1 otherwise.

The feed is built from post titles and summaries, which is exactly the content
class the sitemap builder never has to handle: real prose containing '&',
quotes and em-dashes. Parsing the output back with ElementTree is the point —
it fails loudly on anything that is not well-formed XML.
"""
import sys
import xml.etree.ElementTree as ET

from app.blog import Post, render_atom_feed

ATOM = "{http://www.w3.org/2005/Atom}"

# A title and summary carrying every character that breaks naive XML building.
NASTY_TITLE = 'Tools & "traps" — a <fair> comparison'
NASTY_SUMMARY = "Cost < 5 % & rising; see \"the table\" for O'Brien's numbers."

POSTS = [
    Post(slug="newer", title=NASTY_TITLE, date="2026-08-20",
         summary=NASTY_SUMMARY, html="<p>body</p>", md="raw"),
    Post(slug="older", title="An earlier post", date="2026-06-29",
         summary="Something older.", html="<p>body</p>", md="raw"),
]


def main() -> int:
    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got == want
        print(f"{'PASS' if ok else 'FAIL'} {label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    xml = render_atom_feed(POSTS)

    # Well-formedness is the headline assertion: ET.fromstring raises on any
    # unescaped '&' or stray '<' that manual string building would let through.
    try:
        root = ET.fromstring(xml)
        parsed = True
    except ET.ParseError as exc:
        print(f"FAIL feed parses as XML: {exc}")
        parsed = False
        failures += 1

    if not parsed:
        print(f"\n{0}/13 passed")
        return 1

    check("root element is an Atom feed", root.tag, f"{ATOM}feed")
    check("declares the site title", root.findtext(f"{ATOM}title"), "goodbot-badbot.com")
    check("feed id is the site URL", root.findtext(f"{ATOM}id"),
          "https://goodbot-badbot.com/")
    # Feed-level <updated> must track the newest post, not the oldest or "now",
    # so readers can skip refetching when nothing has been published.
    check("feed updated tracks newest post", root.findtext(f"{ATOM}updated"),
          "2026-08-20T00:00:00Z")

    links = {link.get("rel"): link.get("href") for link in root.findall(f"{ATOM}link")}
    check("self link", links.get("self"), "https://goodbot-badbot.com/feed.xml")
    check("alternate link", links.get("alternate"), "https://goodbot-badbot.com/blog")

    entries = root.findall(f"{ATOM}entry")
    check("one entry per post", len(entries), 2)
    check("newest entry first", entries[0].findtext(f"{ATOM}id"),
          "https://goodbot-badbot.com/blog/newer")

    first = entries[0]
    # The real assertion: the round-trip returns the original characters, not
    # doubly-escaped '&amp;amp;' and not a truncated string.
    check("title survives the round trip", first.findtext(f"{ATOM}title"), NASTY_TITLE)
    check("summary survives the round trip", first.findtext(f"{ATOM}summary"), NASTY_SUMMARY)
    check("entry link", first.find(f"{ATOM}link").get("href"),
          "https://goodbot-badbot.com/blog/newer")
    check("entry updated is RFC 3339", first.findtext(f"{ATOM}updated"),
          "2026-08-20T00:00:00Z")

    # An empty blog must still produce a valid document rather than blow up.
    try:
        empty = ET.fromstring(render_atom_feed([]))
        check("empty feed has no entries", len(empty.findall(f"{ATOM}entry")), 0)
    except ET.ParseError as exc:
        print(f"FAIL empty feed parses: {exc}")
        failures += 1

    print(f"\n{13 - failures}/13 passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
