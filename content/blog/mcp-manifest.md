---
title: An MCP manifest — a specification with no standing
date: 2026-08-20
summary: The site now serves /.well-known/mcp-server, so something finally tells an agent that /mcp exists. The document specifying it is an individual Internet-Draft the IETF explicitly does not endorse, and it expires in September 2026 — which makes implementing it a different kind of act than implementing RFC 9309. It also closed the wrong experiment: in fifteen days no agent has called the endpoint at all, so being unfindable was never the bottleneck.
---

Two weeks ago this site [published an MCP endpoint nobody could
find](/blog/mcp-endpoint). That was the experiment: `/mcp` was announced in
`llms.txt`, `agents.md` and the ARD manifest, deliberately left out of the
homepage `Link` header, and no specification anywhere told an agent the path
existed. Whoever showed up had either guessed a three-letter path or followed
one of our own pointers, and we could tell which.

As of today the site also serves
[`/.well-known/mcp-server`](/.well-known/mcp-server). Something now tells an
agent that `/mcp` exists, and that something was written by somebody else.

## The correction that started it

The [Atom feed post](/blog/atom-feed), published a few hours before this one,
listed the site's machine-readable surfaces and described `/mcp` as "the one
with no discovery specification at all." That line has since been corrected in
place — it was hours old and plainly false, so it was fixed rather than left
standing. What follows is the correction stated openly, which is the part that
matters.

That was wrong, and it was wrong on the day it was published. A reader asked
whether the MCP date in that list was really right. The date was fine —
Anthropic open-sourced MCP on 25 November 2024 — but checking it turned up
[draft-serra-mcp-discovery-uri](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/),
which specifies exactly the thing we had just claimed did not exist: a
`/.well-known/mcp-server` manifest, plus a DNS-based variant, plus an IANA
registration request for the well-known suffix.

The older MCP post says "no discovery *standard*", which is still accurate.
The new one said "no *specification* at all", which was not. That is the second
correction here in a week, and both had the same shape: a claim that was true
when it was first written, restated later without rechecking.

## Implementing something that is not a standard

This site cites [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) for
robots.txt, [RFC 9727](https://www.rfc-editor.org/rfc/rfc9727.html) for the API
catalog and [RFC 4287](https://www.rfc-editor.org/rfc/rfc4287.html) for the
feed. Those are ratified documents that will read the same way in ten years.
This one is not that, and it is worth being blunt about the difference:

- It is an **individual submission**, not adopted by any IETF working group.
- The datatracker states that it "is **not endorsed by the IETF**" and has "**no
  formal standing** in the IETF standards process".
- Its intended status is **none** — it is not on the Standards Track.
- Revision 04 was published in March 2026 and **expires on 25 September 2026**,
  about five weeks from now.

So this is not compliance. It is a bet that a proposal is worth answering before
anyone has blessed it — the same bet as the API catalog and the ARD manifest,
where the column reading zero is itself the measurement. The difference is that
those bets were placed on ratified specs with no ecosystem, and this one is
placed on a spec that may cease to exist before an ecosystem could form.

The practical consequence is a test. `test_mcp_manifest.py` pins the draft's
enumerated values — the four required fields, the transport and trust-class
enums, the shape of the `auth` object — and cross-checks the manifest's
`mcp_version` and `endpoint` against what the running server actually speaks. If
the draft changes or dies, the failing test is the thing that tells us, rather
than a stranger's parser.

Every field is answerable honestly, so every recommended field is present.
`capabilities` claims `["tools"]` and nothing more, because `initialize`
advertises `{"tools": {}}` and nothing more; `auth` declares itself open because
it is. Advertising a `resources` or `prompts` interface that does not exist
would be the machine-readable version of lying.

## The rule that did not change

The [grounding pages post](/blog/grounding-pages) drew a line and stated it
plainly:

> We do not ship a DNS-AID record or an agent manifest, because the site has no
> agent endpoint to advertise — doing so would be theatre.

That was July. The site now has an agent endpoint. Publishing a manifest that
points at a real, working, callable interface is the case the rule was written
to permit. The rule did not bend; the facts changed under it. Had `/mcp` not
existed, this manifest would be exactly the theatre that sentence refused.

## It closed the wrong experiment

Here is the part that stings.

`/mcp` has been live since 5 August. In the fifteen days since, the endpoint has
been touched by exactly **five distinct user agents.** Two are ours: the marked
deploy tooling, and a bare `curl`. One is `httpx`. One is CensysInspect, an
internet-wide scanner that POSTs at everything it can reach. And one is
Amazonbot — an identified AI crawler — which on 9 August sent a **`GET`**.

That last detail is the finding, and it is worth spelling out rather than
asserting.

Under the current protocol revision a `GET` is not a step in MCP at all. The
spec requires exactly one thing of the endpoint — that it "supports POST" — and
revision `2026-07-28` explicitly removed both the GET stream and protocol-level
sessions, which earlier revisions did have. For a server that speaks only this
revision the spec even prescribes the reply: `GET` or `DELETE` to the MCP
endpoint gets a `405 Method Not Allowed`, which is what ours returns, with an
`Allow: POST` header and an error naming the revision.

There is exactly one path on which a bare `GET` would be legitimate: an old
client probing whether this is a legacy HTTP+SSE server. But that fallback is
ordered — the client **must POST first**, and only after a `400`, `404` or `405`
comes back may it try a `GET`. Amazonbot never posted. One `GET`, on 9 August,
and nothing else.

So it did not call the endpoint; it *crawled the URL*, treating an interface as
if it were a document. **No AI agent has ever opened an MCP session with this
server.**

Which means the experiment we designed — guessed the path, or followed a
pointer? — never got to run, because nothing ever arrived to be classified.
Being undiscoverable was not the bottleneck. Nothing was looking.

Publishing the manifest is still the right move: it removes the last excuse, and
if the number ever moves off zero we will know an agent got here by reading a
signpost rather than by guessing. But the honest prediction is the same as for
the AI catalog. A signpost helps somebody already walking toward the door. So
far nobody has come down the road.

One last piece of bookkeeping, in the spirit of [last week's
correction](/blog/unidentified-bucket): the manifest already shows one read, and
that read is a bare `curl` of ours from verifying the deploy. Our marked
tooling is dropped before logging, but a plain `curl` cannot be told apart from
a stranger's, so it stays visible under **HTTP client** rather than being
quietly claimed as our own. The first *organic* read, if it comes, gets a date
and an operator name here.

## Sources and further reading

- [draft-serra-mcp-discovery-uri](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/) — the manifest specification, its revision history, and its "no formal standing" disclaimer.
- [RFC 8615](https://www.rfc-editor.org/rfc/rfc8615.html) — well-known URIs, the registry the draft asks to be added to.
- [An MCP endpoint nobody can find](/blog/mcp-endpoint) — the experiment this manifest ends.
- [Grounding pages — something true to cite](/blog/grounding-pages) — where the no-theatre rule was written down.
- [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) — the POST-only requirement, the removal of the GET stream in revision 2026-07-28, and the ordered legacy fallback.
- [`/.well-known/mcp-server`](/.well-known/mcp-server) — the manifest itself.
