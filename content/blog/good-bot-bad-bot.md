---
title: Good bot, bad bot: measuring AI-crawler compliance in the open
date: 2026-06-29
summary: Why I built a site that publishes which crawlers respect robots.txt — and how the measurement actually works.
---

Every website has a `robots.txt`. It is a polite request: *please don't crawl
these paths.* For decades most search engines honoured it because it was in
their interest to. The arrival of AI crawlers — training data harvesters,
retrieval bots, and autonomous agents — has put that old handshake under real
strain. So I built a small site to answer one question with evidence instead
of opinion: **who actually respects your robots.txt?**

## Why I built this

I kept reading confident claims in both directions — "the AI companies ignore
robots.txt" and "of course we honour it" — with almost no public, reproducible
data behind either. That gap bothered me. A claim about crawler behaviour is
testable. You just need a site that invites everyone in, marks a few doors
clearly as off-limits, and writes down who walks through them anyway.

So that is what [goodbot-badbot.com](https://goodbot-badbot.com) is: a live,
open experiment. No tricks, no per-user-agent blocking, no cloaking. Just a
clean measurement, published in real time.

## How it works

The whole site is open to every crawler. The *only* thing `robots.txt`
disallows is a short list of honeypot paths:

```
User-agent: *
Disallow: /do-not-crawl/
Disallow: /private/
Disallow: /honeypot/
...
```

A compliant crawler reads those rules and stops at the boundary. A
non-compliant one keeps going and trips a honeypot — and every honeypot hit is
logged as a violation, regardless of which user-agent it claims to be. Because
the rest of the site is deliberately open, compliance is something we can
actually *measure*, not just assert.

There are two ways a bot can end up on a forbidden path, and they mean
different things, so the honeypots are split into two groups:

- **Linked traps** are reachable through a visible link on the homepage *and*
  disallowed in `robots.txt`. A hit here is unambiguous: the crawler followed
  a link and ignored the rule. Call it a *via-link* violation.
- **Unlinked traps** appear nowhere on the site. The only way to discover them
  is to read `robots.txt` and treat its `Disallow` list as a treasure map — or
  to guess. A hit here is a *via-guess* violation.

That distinction matters. Using the disallow list itself as a list of
interesting URLs to crawl is a particularly cheeky failure mode, and splitting
the honeypots lets us see it.

## Beyond the disallow list

Compliance is the headline, but two newer signals turned out to be just as
interesting.

**Web Bot Auth.** A handful of operators have started cryptographically
signing their requests (the IETF Web Bot Auth draft, built on HTTP Message
Signatures). The site verifies those signatures against the operator's
published keys, so a visit can be marked *verified*, *signature failed*, or
simply *unsigned*. It is an early look at which crawlers are willing to prove
who they are.

**Discovery reads.** Alongside `robots.txt`, the site serves the files agents
are starting to look for: `llms.txt` and `agents.md`. These are the opposite
of a honeypot — they are *invitations*, a machine-readable summary of the site
for a model that asks nicely. Reading them is not a violation; it is the
*good* signal, an agent doing discovery the way it is meant to. The dashboard
shows who fetches them, separately from who trips the traps.

## Privacy

Measuring behaviour does not require tracking people. Every logged IP address
is SHA-256 hashed and truncated to the first 16 hex characters before it is
stored. The raw IP never touches disk. What is published is aggregate: which
bot, which path, how often — not who.

## Watch it live

The scoreboard updates continuously at
[goodbot-badbot.com](https://goodbot-badbot.com), and the whole thing is open
source on [GitHub](https://github.com/dkd-dobberkau/goodbot-badbot) — FastAPI
and MySQL, nothing exotic. I will follow this post with a data one once there
is enough signal to say something honest about it. For now: the doors are
open, the off-limits ones are clearly marked, and the log is running.
