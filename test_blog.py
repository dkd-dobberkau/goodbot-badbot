"""Stdlib-only smoke test for app.blog.parse_frontmatter.

Run with: python test_blog.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import sys

from app.blog import parse_frontmatter

TOTAL = 8


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures += 1

    meta, body = parse_frontmatter(
        "---\ntitle: Hello\ndate: 2026-06-29\nsummary: Hi there\n---\n# Body\n\ntext"
    )
    check("title parsed", meta.get("title") == "Hello")
    check("date parsed", meta.get("date") == "2026-06-29")
    check("summary parsed", meta.get("summary") == "Hi there")
    check("body starts at heading", body.startswith("# Body"))
    check("frontmatter stripped from body", "title:" not in body)

    meta2, _ = parse_frontmatter("---\ntitle: A: B\n---\nx")
    check("value with colon kept whole", meta2.get("title") == "A: B")

    meta3, body3 = parse_frontmatter("# Just body\n\nno fm")
    check("no frontmatter -> empty meta", meta3 == {})
    check("no frontmatter -> body intact", body3.startswith("# Just body"))

    print(f"\n{TOTAL - failures}/{TOTAL} checks passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
