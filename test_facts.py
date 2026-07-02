"""Stdlib smoke test for app.facts.build_jsonld and _fact_from_source.

Run with: python test_facts.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import json
import sys

from app.facts import build_jsonld, _fact_from_source

DATASET_META = {
    "title": "goodbot-badbot",
    "entity": "goodbot-badbot",
    "entity_type": "Dataset",
    "segment": "AI crawler robots.txt compliance measurement",
    "summary": "A public experiment measuring robots.txt compliance.",
    "canonical": "https://goodbot-badbot.com/facts/goodbot-badbot",
    "date_modified": "2026-07-02",
}
TERM_META = {
    "title": "robots.txt compliance",
    "entity": "robots.txt compliance",
    "entity_type": "DefinedTerm",
    "summary": "How far a crawler obeys robots.txt Disallow rules.",
    "canonical": "https://goodbot-badbot.com/facts/robots-txt-compliance",
    "date_modified": "2026-07-02",
}


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            failures += 1

    ds = build_jsonld(DATASET_META)
    check("dataset @type", ds["@type"] == "Dataset")
    check("dataset @context", ds["@context"] == "https://schema.org")
    check("dataset name", ds["name"] == "goodbot-badbot")
    check("dataset description = summary", ds["description"] == DATASET_META["summary"])
    check("dataset url = canonical", ds["url"] == DATASET_META["canonical"])
    check("dataset dateModified", ds["dateModified"] == "2026-07-02")
    check("dataset creator name", ds["creator"]["name"] == "dkd Internet Service GmbH")
    check("dataset creator url", ds["creator"]["url"] == "https://www.dkd.de")
    check("dataset free", ds["isAccessibleForFree"] is True)
    check("dataset license MIT", "MIT" in ds["license"])
    check("dataset distribution url",
          ds["distribution"]["contentUrl"] == "https://goodbot-badbot.com/api/stats")
    check("dataset distribution format",
          ds["distribution"]["encodingFormat"] == "application/json")

    dt = build_jsonld(TERM_META)
    check("term @type", dt["@type"] == "DefinedTerm")
    check("term inDefinedTermSet",
          dt["inDefinedTermSet"] == "https://goodbot-badbot.com/facts")
    check("term has no distribution", "distribution" not in dt)

    fallback = build_jsonld({"title": "x", "entity_type": "Nonsense"})
    check("unknown type falls back to Thing", fallback["@type"] == "Thing")

    # JSON-LD must serialise to valid JSON.
    check("dataset json valid", json.loads(json.dumps(ds))["@type"] == "Dataset")

    # _fact_from_source needs markdown-it-py; skip gracefully if absent.
    try:
        import markdown_it  # noqa: F401
        raw = (
            "---\ntitle: goodbot-badbot\nentity: goodbot-badbot\n"
            "entity_type: Dataset\nsegment: seg\nsummary: A summary.\n"
            "canonical: https://goodbot-badbot.com/facts/goodbot-badbot\n"
            "date_modified: 2026-07-02\n---\n"
            "## goodbot-badbot is\n\ngoodbot-badbot is a test.\n"
        )
        fact = _fact_from_source(raw, "goodbot-badbot")
        check("fact slug", fact.slug == "goodbot-badbot")
        check("fact entity_type", fact.entity_type == "Dataset")
        check("fact html rendered", "<h2>" in fact.html)
        check("fact md is raw source", fact.md == raw)
        check("fact jsonld is a string", isinstance(fact.jsonld, str))
        check("fact jsonld parses", json.loads(fact.jsonld)["@type"] == "Dataset")

        missing_type = _fact_from_source("---\ntitle: x\n---\nbody", "x")
        check("missing entity_type -> None", missing_type is None)
    except ImportError:
        print("SKIP _fact_from_source tests (markdown-it-py not installed)")

    try:
        import markdown_it  # noqa: F401
        from app.facts import (
            render_index_html, render_index_markdown,
            render_fact_html, render_fact_markdown,
        )
        raw = (
            "---\ntitle: goodbot-badbot\nentity: goodbot-badbot\n"
            "entity_type: Dataset\nsegment: seg\nsummary: A summary.\n"
            "canonical: https://goodbot-badbot.com/facts/goodbot-badbot\n"
            "date_modified: 2026-07-02\n---\n## goodbot-badbot is\n\nBody.\n"
        )
        fact = _fact_from_source(raw, "goodbot-badbot")

        fh = render_fact_html(fact)
        check("fact html has jsonld script", 'application/ld+json' in fh)
        check("fact html has back link", 'href="/facts"' in fh)
        check("fact html has title", "goodbot-badbot" in fh)
        check("fact html injected via head token", "__HEAD_EXTRA__" not in fh)

        fm = render_fact_markdown(fact)
        check("fact markdown is raw source", fm == raw)

        im = render_index_markdown()
        check("index markdown heading", im.startswith("# Grounding pages"))

        ih = render_index_html()
        check("index html no leftover token", "__CONTENT__" not in ih)
    except ImportError:
        print("SKIP renderer tests (markdown-it-py not installed)")

    print(f"\n{failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
