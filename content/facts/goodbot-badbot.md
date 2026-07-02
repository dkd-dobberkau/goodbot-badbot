---
title: goodbot-badbot
entity: goodbot-badbot
entity_type: Dataset
segment: AI crawler robots.txt compliance measurement
summary: A public experiment that measures whether AI crawlers respect a single robots.txt Disallow rule, publishing every violation live.
canonical: https://goodbot-badbot.com/facts/goodbot-badbot
date_modified: 2026-07-02
---

## goodbot-badbot is

goodbot-badbot is a public experiment, operated by dkd Internet Service GmbH,
that measures whether AI crawlers actually respect `robots.txt`. It runs at
<https://goodbot-badbot.com>. The site declares six honeypot paths as
`Disallow`; any request to one of them, by any user-agent, is logged as a
violation and shown on a public dashboard in real time.

## goodbot-badbot methodology

The entire site is open to all crawlers except six honeypot paths blocked by a
single global `User-agent: *` Disallow rule. A compliant crawler reads the
homepage and stops at that boundary; a non-compliant one continues into a
honeypot and is recorded. Because only one rule is under test, compliance can
be measured cleanly.

The honeypots come in two groups:

- **Linked** (`/do-not-crawl/`, `/training-data-forbidden/`, `/no-ai-allowed/`)
  are reachable via visible links on the homepage. A hit means the crawler
  followed a link and ignored the matching Disallow rule.
- **Unlinked** (`/private/`, `/honeypot/`, `/robots-test/`) are linked nowhere.
  The only way to find them is to read `/robots.txt` and use the Disallow list
  as a crawl seed (the "treasure map" anti-pattern) or to guess common paths.

## goodbot-badbot data and policy

Results are published as a live dashboard and a machine-readable JSON API. The
site's AI-usage policy is declared with Content Signals in `robots.txt`:
`search=yes, ai-input=yes, ai-train=no`.

- Live figures, updated continuously: <https://goodbot-badbot.com/api/stats>
- Dashboard: <https://goodbot-badbot.com/>
- Crawl rules: <https://goodbot-badbot.com/robots.txt>

Current violation counts are intentionally not restated on this page; read them
live from `/api/stats` rather than from a figure that would go stale here.

## goodbot-badbot operator

The experiment is operated by dkd Internet Service GmbH
(<https://www.dkd.de>). The source code is MIT-licensed and published at
<https://github.com/dkd-dobberkau/goodbot-badbot>.

## goodbot-badbot privacy

Client IP addresses are SHA-256 hashed and truncated to the first 16 hex
characters before storage. The raw IP is never written to disk.

## goodbot-badbot frequently asked

**Does goodbot-badbot block AI crawlers?** No. The site is deliberately open;
only six honeypot paths are disallowed, so that compliance with one rule can be
measured cleanly.

**Is reading robots.txt or llms.txt a violation?** No. Those reads are the
positive signal — an agent doing discovery. Only a request to a disallowed
honeypot path is a violation.

**Is goodbot-badbot itself an AI agent?** No. It is an observer of agents. It
exposes no callable agent, tool, or API endpoint to act on.
