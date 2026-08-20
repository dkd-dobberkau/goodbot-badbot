---
title: An Atom feed — the oldest agent interface
date: 2026-08-20
summary: The blog now has a feed at /feed.xml. That makes six machine-readable surfaces on this site, and the new one is by two decades the oldest format of the lot — a 2005 IETF Standards Track spec with a working installed base, next to five things invented in the last two years that no named AI crawler has fetched once. It is also the first offer here that will not read zero, and the first we deliberately kept out of the Discovery Reads table.
---

The blog now publishes an [Atom feed](/feed.xml) — one entry per post, each with
its title, link and summary, this one included. If you use a feed reader, that
is the whole announcement: subscribe and stop reading here.

The rest of this is about why a 2005 file format is the most interesting thing
this site has shipped in a month.

## Six surfaces, one with customers

Count what this site now offers a machine, and when each thing was invented:

- **`llms.txt`** — proposed 2024, no standards body.
- **`agents.md`** — a convention, younger still.
- **`/.well-known/api-catalog`** —
  [RFC 9727](https://www.rfc-editor.org/rfc/rfc9727.html), June 2025, though the
  linkset format it is served in is older.
- **`/.well-known/ai-catalog.json`** — Agentic Resource Discovery, and there is
  no registry indexing it yet.
- **`/mcp`** — Model Context Protocol, 2024, and the one with no discovery
  specification at all.
- **`/feed.xml`** — [RFC 4287](https://www.rfc-editor.org/rfc/rfc4287.html),
  December 2005, IETF **Standards Track**.

Most of those were invented in roughly the last two years, are read by almost
nobody, and are described in this blog with steadily lowering expectations. Last
week's [correction](/blog/unidentified-bucket) put a number on it: in 78 days of
logging, **no named AI crawler has fetched `llms.txt` or `agents.md` even
once.** The API catalog and the AI catalog have never had an organic read at
all.

The newest addition is the oldest format of the lot. It was standardised by the
IETF while people were still arguing about whether blogs counted as publishing,
and it has something none of the others do: **clients that already exist.**
NetNewsWire, Feedly, Miniflux, Thunderbird and a long tail of scripts have
supported this exact format for twenty years without anybody calling it AI
infrastructure.

## The first offer here that will not read zero

That distinction matters more than it first looks, and it is worth being
precise about it.

The API catalog and the AI catalog read zero for a structural reason: the
ecosystem that would consume them does not exist yet. We [said so when we
shipped them](/blog/ai-catalog) and expected the columns to stay empty for
months. A quiet column there measures how far ahead of the ecosystem the feature
is — which is interesting, but it is not the same as being used.

The feed is the first thing this site has published that has an installed base
on day one. Somebody will subscribe to it in a feed reader this week. That does
**not** mean an AI agent will fetch it, and I would bet against it: an agent
that ignores a file literally named `llms.txt` has no obvious reason to go
looking for `application/atom+xml`. But for the first time the honest prediction
is "used by humans, probably ignored by agents" rather than "ignored by
everyone".

If an agent *does* start polling it, that is a genuinely useful finding — it
would mean the winning interface for machine-readable content was sitting there
the whole time, and the last two years of new formats were answering a question
that already had one.

## What it deliberately does not do

The feed does not get a column in [Discovery Reads](/).

That is a direct consequence of last week's post. The failure being corrected
there was a single number that mixed audiences: one "Unidentified" row holding
SEO crawlers, proxy-rotating scrapers and our own deploy checks, which produced
a published finding that did not survive inspection. A feed is fetched by
ordinary feed readers at least as much as by anything agentic. Putting it in the
table that exists to measure *agent* discovery would rebuild exactly the problem
we just spent a week taking apart.

So fetches are logged like every other meta surface, and the rows sit in the
database where a query can reach them. If the numbers ever say something worth
saying, they get their own presentation and their own caveats. Collecting a
signal and publishing a signal are different decisions, and conflating them is
how the last mistake happened.

## Two small craft notes

**Atom, not RSS 2.0.** Readers handle both, so this is not a compatibility
argument. Atom is an IETF Standards Track document with unambiguous RFC 3339
timestamps and a required unique ID per entry; RSS 2.0 has no RFC and a date
format borrowed from email. On a site that cites RFC 9309 in its robots.txt post
and RFC 9264 in its catalog post, picking the specified one was not a close
call.

**Summaries, not full text.** Every post here already has a hand-written summary
in its frontmatter, doing the job an auto-generated excerpt would do badly. And
on a site whose entire purpose is measurement, a click is a data point —
shipping the whole article into the reader would quietly delete the thing being
measured.

One last detail, because it is the difference between publishing a document and
publishing noise: the feed's `<updated>` timestamp tracks the newest post rather
than the current time. A feed that has not changed does not keep telling its
readers to fetch it again.

## Sources and further reading

- [RFC 4287](https://www.rfc-editor.org/rfc/rfc4287.html) — The Atom Syndication Format, IETF Standards Track, December 2005.
- [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html) — the timestamp format Atom requires, and the reason its dates are unambiguous.
- [The Unidentified bucket — a correction](/blog/unidentified-bucket) — why this feed does not get a Discovery Reads column.
- [An AI catalog — from "findable" to "found"](/blog/ai-catalog) — the surface that reads zero for structural reasons, and why that is still data.
- [`/feed.xml`](/feed.xml) — the feed itself.
