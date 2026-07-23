---
title: The files agents actually read
date: 2026-07-24
summary: After 51 days of logging, the surprise is not who trips the honeypots — it is which "read me correctly" file agents actually fetch. Grounding pages get read; llms.txt and agents.md barely; the brand-new API catalog and Web Bot Auth sit at zero. A snapshot, with all the caveats a snapshot deserves.
---

This site now speaks half a dozen dialects of "please read me correctly":
`robots.txt` with Content Signals, `llms.txt`, an `agents.md` probe surface,
Web Bot Auth keys, [grounding pages](/facts), and — since last week — a
[`/.well-known/api-catalog`](/blog/api-catalog). After 51 days of logging, the
interesting question turned out not to be *who cheats*. It was *which of those
files an agent actually bothers to open*.

The numbers below are a snapshot as of 24 July 2026. They are small, and the
live version is always at [`/api/stats`](/api/stats) — read this as a first
reading of a thermometer, not a verdict.

## What gets read

Of 151 logged discovery reads — deliberate fetches of a "here is how to use
this site" file, the opposite of a honeypot hit — the split is lopsided:

- **Grounding pages** (`/facts`, the citable factual definitions) — **136 reads**.
- **`llms.txt`** (the LLM-oriented site summary) — **8 reads**.
- **`agents.md`** (the agent usage-instruction probe) — **5 reads**.
- **`/.well-known/api-catalog`** (the machine-readable API index) — **0 reads**.
  The two the dashboard shows are our own `curl` verifying the deploy; no real
  agent has fetched it yet.

The grounding pages are read seventeen times more often than `llms.txt` and
`agents.md` combined. Named crawlers are in there too — GPTBot, ClaudeBot and
Amazonbot each pulled the facts pages several times — not just anonymous
traffic.

## Why the facts win

It is worth being careful about *why*, because the obvious story is not quite
right. `llms.txt` and `agents.md` are **tables of contents**: they are useful
only to something that is *planning* — deciding what to crawl, how to call an
API, what the site is for. A **grounding page** is useful at a different
moment: when a model is answering a question *right now* and wants a citable,
unambiguous fact to stand on. There is simply a lot more inference happening in
the world than there is deliberate crawl-planning, so the surface that pays off
at inference time gets touched more often.

If that holds up — and 136 reads is a thermometer, not a proof — it is a
mildly heretical finding: the thing everyone is told to publish (`llms.txt`)
is read least, and the less-hyped grounding page is read most. We will keep
watching before we say it louder.

## Three offers, one taken

Line up the three things this site *offers* rather than *forbids*, and a
pattern falls out:

- **Grounding pages** — a real fact you can cite. **Consumed.**
- **API catalog** — a documented way to call the stats API. **Zero.**
- **Web Bot Auth** — a way to prove your identity when you crawl. **Zero
  verified requests in 51 days.**

The one that gets used is the one with immediate payoff. The two that sit at
zero are pure infrastructure: valuable *if* an ecosystem grows up around them,
worthless until it does. That is not a failure of the features — it is a
measurement of exactly how far ahead of the ecosystem they are. When the first
real API-catalog read lands, this post gets an update with a date and an
operator name.

## And the honeypots?

Briefly, because it is the least surprising part. 650 honeypot hits — but
**637 of them come from user-agents we cannot identify**. The headline number
is mostly anonymous scrapers, and says little about the big AI operators. The
identifiable signal is small and, for once, fairly clean: 13 violations across
six named operators, OpenAI's crawlers accounting for the most, and roughly
half the named bots (Apple, Amazon, Brave, Common Crawl, You.com) tripping
nothing at all. Thirteen data points is not a league table. It is a hint.

## The caveats, stated plainly

- **It is a snapshot.** 51 days, 1,258 requests. Trends need months.
- **Identification is by user-agent string**, which is trivially spoofed and
  absent on 98% of the violations. "Anonymous" is not a synonym for "AI
  crawler".
- **Reading a grounding page is a read, not comprehension.** We log the fetch;
  we cannot see whether the model used the fact or cited it correctly.
- **Correlation, not cause.** That facts outdraw `llms.txt` is consistent with
  the inference-versus-planning story — it does not prove it.

None of the zero columns are bugs, and that is the whole point of running the
experiment out loud: a quiet column is data. The site keeps offering agents
something true to use — and keeps writing down, honestly, who takes it up.
