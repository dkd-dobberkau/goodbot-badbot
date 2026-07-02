---
title: robots.txt compliance
entity: robots.txt compliance
entity_type: DefinedTerm
segment: web crawling standards and AI governance
summary: The degree to which an automated crawler obeys the Disallow rules a site publishes in its /robots.txt file.
canonical: https://goodbot-badbot.com/facts/robots-txt-compliance
date_modified: 2026-07-02
---

## robots.txt compliance is

robots.txt compliance is the degree to which an automated crawler obeys the
rules a website publishes in its `/robots.txt` file. The file format and
fetching behaviour are specified by RFC 9309, the Robots Exclusion Protocol.
`robots.txt` is advisory: it is enforced by convention and reputation, not by
access control, so compliance is a behavioural property of each crawler, not a
guarantee the server can impose.

## robots.txt compliance and Disallow

The core directive is `Disallow`, which names a path prefix a crawler should
not fetch, scoped to a `User-agent` group. A crawler is compliant with a given
rule when it refrains from requesting any path the rule disallows. A single
global `User-agent: *` rule applies to every crawler that does not match a more
specific group.

## robots.txt compliance measurement

Compliance can be measured by publishing paths as `Disallow` and observing
whether crawlers request them anyway. Two signal types are distinguishable:

- A hit on a **linked** disallowed path shows the crawler followed a link and
  ignored the Disallow rule.
- A hit on an **unlinked** disallowed path — discoverable only through
  `robots.txt` itself — shows the crawler used the Disallow list as a crawl
  seed, the "treasure map" anti-pattern, where the exclusion file is mined for
  URLs instead of being honoured.

## robots.txt compliance and AI crawlers

AI crawlers extend the same protocol with usage-specific tokens. Content
Signals such as `ai-train`, `ai-input`, and `search` let a site express not
just whether a path may be fetched but how the retrieved content may be used —
for model training, for answer grounding, or for search indexing. Compliance
then covers both the fetch boundary and the declared usage policy.

## robots.txt compliance — see also

This concept is measured live at
<https://goodbot-badbot.com/facts/goodbot-badbot>, which records real crawler
behaviour against a fixed set of Disallow rules.
