---
title: An MCP endpoint nobody can find
date: 2026-08-05
summary: The site now answers POST /mcp — a stateless Model Context Protocol server exposing the compliance data as two callable tools. It is the fifth discovery signal and the first that is an interface rather than a document, and the only one with no discovery standard behind it: nothing in any spec tells an agent that /mcp exists. So we announced it in three places, deliberately left it out of a fourth, and can now tell the agents that guessed the path from the ones that followed a pointer. Building it also exposed that the site had been answering every HEAD request with 405 — meaning a crawler could have probed a honeypot unrecorded — so reads and probes are now counted separately.
---

For two months this site's `agents.md` said, in as many words:

> There is no MCP server, A2A endpoint, or JSON-RPC tool to discover here.

That sentence is now false, and deleting it deserves an explanation before
anything else.

## Why the stance changed

The rule here has never been "no endpoints". It was, and is, **don't publish an
offer you cannot honour**. We skipped [DNS-AID](/blog/ai-catalog) because a SVCB
record pointing at an HTML dashboard is a signpost to nothing. We would have
skipped an MCP server on the same grounds, right up until the moment we noticed
we had been sitting on a real one the whole time: `/api/stats` is a genuine
machine interface with a genuine consumer, already described by an
`/openapi.json` that two catalogs already point at. Wrapping it as tools is not
inventing a capability. It is admitting one we already had.

What changed on the other side is that the cost collapsed. Protocol revision
`2026-07-28` removed the `initialize` handshake and protocol-level sessions from
Streamable HTTP. Every request is now self-contained — it carries its own
protocol version and client identity — so a read-only server is a pure function
over data you already have. No session store, no background stream, no state
machine. [Dries Buytaert](https://dri.es/), whose lead this site has now
followed four times, shipped his site-search server in under 150 lines and said
the revision was what made it feasible. Ours is about the same size, and it
issues **zero new database queries**: both tools read the same five-second stats
cache the dashboard already polls.

## What it does

`POST /mcp`, three methods, two tools. The three methods are the ones the
revision requires: `server/discover` (mandatory — it is how a client learns your
supported versions without a handshake), `tools/list`, and `tools/call`. The
tools are:

- **`get_compliance_stats`** — the full scoreboard: every crawler observed, its
  visit count, its honeypot violations, and the resulting verdict.
- **`check_bot`** — one crawler, looked up by display name (`GPTBot`) or by raw
  User-Agent string.

```bash
curl -sX POST https://goodbot-badbot.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/list' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

There are no write operations, and there will not be. `GET` and `DELETE` return
`405` — this revision has no GET stream and no session teardown to tear down.

## The fifth signal, and the first that isn't a document

The [Discovery Reads](/) table now has a sixth column. Read in order, the
signals it tracks are a ladder:

- **`llms.txt` / `agents.md`** — an agent that found us, reading a hint.
- **grounding pages** — an agent looking for a citable fact.
- **api catalog** — an agent taking up a documented offer instead of scraping.
- **ai catalog** — the registries that would help an agent find us at all.
- **mcp calls** — an agent *calling* rather than reading.

That last step is a category change, not another rung. Everything above it is a
document an agent fetches and interprets. `/mcp` is an interface an agent
invokes, with typed arguments and a schema-checked result. It is the difference
between publishing a manual and answering the phone.

## The experiment: guessed, or followed?

Here is the part that makes this worth building on a measurement site rather
than just useful.

**MCP has no discovery specification.** There is no `.well-known` path for it,
no `Link` relation, nothing in any published standard that tells an agent that
`/mcp` exists. Dries hit exactly this wall: he built the server, then found the
three candidate discovery routes were an IETF standard nobody reads, a draft
nobody has implemented, and — for the endpoint itself — nothing at all. His
fallback was a hand-written Agent Skill pointing at his API catalog.

So `/mcp` is announced in exactly three places — the ARD manifest, `llms.txt`,
and `agents.md` — and **deliberately kept out of the homepage `Link` header**,
where every other machine surface on this site is advertised. That asymmetry is
the experiment. A bot that calls `/mcp` having never read a discovery file
**guessed the path**. A bot that reads `ai-catalog.json` and then calls `/mcp`
**followed a pointer**. Both land in the same log under the same path, so the
two cases separate by query rather than by schema — no new column required, and
the question stays answerable later even if we think of a better way to ask it.

Nobody has published numbers on this, because until the handshake came out of
the protocol almost nobody had a public MCP endpoint sitting on a domain with
honest request logs. We do now.

## Reads and probes are not the same thing

Shipping the endpoint turned up something embarrassing about the rest of the
site. While checking that `GET /mcp` returned a clean `405`, a `HEAD` against
the homepage came back `405` too. So did `HEAD /robots.txt`. So did every
route on the site.

The cause was mundane: Starlette 1.x stopped adding `HEAD` implicitly to
routes that declare `GET`, which older versions did automatically. Every
handler here inherited the old assumption and nobody noticed, because browsers
and `curl` default to `GET` and the dashboard looked fine.

The consequence was not mundane. Crawlers routinely send `HEAD` before
fetching — to check freshness, size, or whether a URL exists at all. This site
was answering all of them with "method not allowed", which means **a crawler
could have `HEAD`-probed a `Disallow`'d honeypot and never been recorded as a
violation**. A site whose entire purpose is measuring whether crawlers respect
`robots.txt` was refusing a standard HTTP method and quietly dropping the
evidence. `robots.txt` rules are method-independent; our enforcement was not.

That is fixed, and it forced a distinction worth making explicit. A `HEAD`
request asks whether something exists without taking the bytes. That is a
*probe*, not a *read*, and folding the two together would have inflated every
"discovery read" number on the dashboard with crawlers that never actually
consumed anything. So the `visits` table now records the HTTP method, every
per-surface column counts non-`HEAD` only, and probes get their own **head
probes** column beside them.

Two footnotes on the data, both in the spirit of saying what the numbers
actually mean:

- Every read logged **before** August 2026 is a `GET` by construction, not by
  assumption. `HEAD` returned `405` site-wide until the fix, so no historical
  row could have been a probe. The back-catalogue is clean.
- The probe column therefore necessarily starts at zero. A quiet column here
  means something different from a quiet `ai catalog` column: not "nobody is
  looking", but "we have only just started listening".

There is a general lesson in this that applies well beyond one site. An
instrument that silently rejects a class of input does not report a smaller
number — it reports a *wrong* number, confidently, with no indication anything
is missing. We were publishing compliance statistics with a hole in the
collection layer and no way to see it from the output. The only reason it
surfaced is that building something unrelated made us look at raw status codes
again.

## The honest part

The `ai catalog` post predicted its column would read zero for months. This one
will probably read zero for longer, and the reasons are worth separating,
because they are not the same reason.

The AI catalog is quiet because **its readers may not exist yet** — ARD
registries have to be built and crawling before a manifest matters. The MCP
column will be quiet because **there is no way to find it**. Those are different
failures. The first is an ecosystem that hasn't arrived; the second is a
specification-shaped hole. An agent that desperately wanted to call this server
and had every incentive to could still only reach it by guessing a three-letter
path or by reading a file that mentions it in passing.

That gap is the actual finding, and it is available today without waiting for a
single request to arrive. The industry has a mature story for *invoking* agent
tools and no story at all for *finding* them. `robots.txt` solved discovery for
crawlers in 1994 with a fixed path. Thirty-two years later, the protocol
everyone is building agents on top of has no equivalent — and the working groups
are busy with header-mirroring rules and error codes.

If the column ever turns non-zero, we will know which agent got there first,
whether it guessed or followed, and on what date. All three are more interesting
than the number itself.

## A note on WebMCP

Worth heading off the obvious question: this is **not**
[WebMCP](https://patrickbrosset.com/articles/2026-02-23-webmcp-updates-clarifications-and-next-steps/),
the `navigator.modelContext` browser API from Google and Microsoft currently in
origin trial. Same protocol name, disjoint audiences. WebMCP lets a *rendered
page* hand its tools to a browser-driving agent, replacing
screenshot-and-guess-where-to-click. Ours is a server endpoint any client can
POST to headlessly.

We are not implementing WebMCP, and the reason is the same discipline as
everything else here: it leaves no trace in a server log. A measurement site can
only publish what it can honestly observe, and browser-side tool invocation is
invisible from where we are standing. That is not a criticism of WebMCP — it is
an admission about the limits of this instrument.

## Sources and further reading

- [Dries Buytaert — Helping agents discover my site search with MCP](https://dri.es/helping-agents-discover-my-site-search-with-mcp) — the post this one follows, and the source of the "discovery and invocation are separate layers" framing.
- [MCP specification, revision 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) — the Streamable HTTP binding, including the header-mirroring rules and why `GET` is now a `405`.
- [MCP versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning) — how a handshake-free protocol negotiates versions, and why `server/discover` is mandatory.
- [Agentic Resource Discovery](https://agenticresourcediscovery.org/spec/) — where the MCP server card is advertised, from our [previous post](/blog/ai-catalog).
- [WebMCP updates and next steps](https://patrickbrosset.com/articles/2026-02-23-webmcp-updates-clarifications-and-next-steps/) — the browser-side API this is not.
