---
title: Level 4 of 5, and the red mark is correct
date: 2026-11-20
summary: We ran this site through isitagentready.com, Cloudflare's agent-readiness scanner, and scored level 4 of 5. Its advice for the next level was to publish an MCP Server Card at a .well-known path — the one location the final Server Card specification considered and rejected. We followed the spec instead, so that check stays red on purpose. The scanner also caught a real mistake of ours, and its own visits in our log make it one of the better-behaved bots this site has seen.
---

[isitagentready.com](https://isitagentready.com) is a scanner run by
Cloudflare. You give it a URL, and it checks around twenty emerging
agent-facing conventions — `robots.txt`, Markdown negotiation, Content
Signals, Web Bot Auth, API catalogs, MCP, A2A, OAuth discovery, a few
commerce protocols — and turns the result into a level from 0 to 5.

This site scored **level 4, "Agent-Integrated"**. That is not surprising: most
of what it checks, we had already built in order to [measure who reads
it](/blog/files-agents-actually-read). What is more interesting is the one
check we deliberately left failing, the one we fixed because the scanner was
right, and what the scanner looks like from the other side of the log.

## What it gets right

Credit first, because it is earned. Every check comes back with its
**evidence**: the exact request the scanner sent, the response it got, and a
machine-readable reason code. A "fail" is never a verdict you have to take on
trust; you can replay it with `curl`. The scan is available as a public JSON
API, every failing check links to a short fix-it spec, and the commerce checks
mark themselves as not applicable on a site that sells nothing instead of
dragging the score down. Most "AI SEO" graders give you a number. This one
shows its work.

## The red mark

To reach level 5, the scanner asked for four things. Three of them — an
`auth.md` for agent registration, an A2A Agent Card, an Agent Skills index —
describe things this site does not have: there is no login and no agent here.
Publishing them would mean advertising interfaces that do not exist, which is
the one thing [this site does not do](/blog/mcp-endpoint).

The fourth looked like an easy win. We do run an MCP server, and the scanner
asked for its **Server Card** at `/.well-known/mcp/server-card.json`, listing
the server's capabilities. The card already existed, inlined in our [AI
catalog](/blog/ai-catalog). Serving it at one more path would have taken a few
lines, and that was the first plan.

Then we read the specification the scanner itself links to.
[SEP-2127, "MCP Server Cards"](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2127)
was merged as **Final** on 6 October 2026. It says three things that matter
here:

- A card may live at any URL. The location it **reserves** is
  `<streamable-http-url>/server-card` — for a server at `/mcp`, that is
  `/mcp/server-card`. Clients are meant to find cards through an AI catalog,
  not by guessing.
- The extension's [discovery document](https://github.com/modelcontextprotocol/experimental-ext-server-card/blob/main/docs/discovery.md)
  lists a `.well-known` location under **"Alternatives considered"** and
  recommends against it: `.well-known` is for site-wide metadata, and a single
  server's card is not site-wide.
- Cards deliberately contain **no tools, resources, prompts or capabilities**.
  Those depend on who is asking and are learned at runtime, so a static list
  would invite clients to trust something that may be wrong.

So the scanner's advice asks for the rejected location and for content the
spec excludes. Its evidence shows exactly what it probes:
`/.well-known/mcp/server-card.json`, `/.well-known/mcp/server-cards.json` and
`/.well-known/mcp.json`. It never tries `/mcp/server-card`. And although its
own catalog check reads our AI catalog — and finds the MCP entry in it — the
MCP check does not follow that entry. The two checks do not talk to each
other.

We implemented the spec. The card is now served at
[`/mcp/server-card`](/mcp/server-card) with the media type, CORS and caching
headers the discovery document asks for, and the same card stays inlined in
the catalog. The scanner still reports **"MCP Server Card not found"**, and
that is the correct outcome of a check written before the spec settled. A score
is only as current as its checklist.

Reads of the new path are logged next to the [MCP
manifest](/blog/mcp-manifest) we published in August. That post noted that
nothing in any specification told an agent where `/mcp` was. Something does
now — the AI catalog, pointing at a Server Card — and we will see whether
anything follows it.

## Where we were wrong

Reading SEP-2127 closely was not comfortable. The card we had been inlining
since August was **not a valid card**: no `$schema`, no `version`, a name that
was not in the required reverse-DNS form, a description over the 100-character
limit, and a full tool list the spec explicitly keeps out. It was the shape an
earlier example suggested, and nothing had ever checked it. It now validates
against the extension's published JSON Schema, and the server's own
`server/discover` reports the same name, as the spec asks.

The scanner also found a mistake on its own. Its catalog check reported
`correctMediaType: false`: we served `/.well-known/ai-catalog.json` as plain
`application/json`. The [AI Catalog
specification](https://github.com/Agent-Card/ai-catalog) defines
`application/ai-catalog+json`, and its serving guide asks for exactly that as
the `Content-Type`. The scanner was right, so we fixed it, and the next scan
showed `correctMediaType: true`.

Worth noting, though: the check said **"pass"** both before and after. The
score could not see the mistake it had detected. That is the pattern in
miniature.

## Presence is not function

Most checks ask whether a file exists and parses, not whether it is useful.
Markdown negotiation passes if the response says `text/markdown`; whether the
body contains anything is not examined. The AI-bot rule check passes a
`robots.txt` that only has wildcard rules, which suits this site — the
experiment depends on treating every bot alike — but means the check rarely
says anything. One point is lost to DNS-AID, a draft that needs SVCB records;
we skipped it on purpose ([reasons here](/blog/ai-catalog)), and our DNS
provider could not publish them anyway. That point measures a hosting choice,
not a site.

What no check asks is whether an agent can actually *do* something here:
whether the API behind the `Link` header returns usable data, whether the MCP
server answers, whether a firewall turns away the very agents the metadata
invites. "Agent-ready", in this scanner, means having adopted a particular set
of drafts — several of them Cloudflare's own, such as Content Signals and
Markdown for Agents. That is a reasonable checklist. It is not a measurement
of readiness, and the scanner's own red mark on this site shows the gap.

## The scanner as a visitor

This site exists to watch bots, so here is how this one behaves. Since
3 June our log has **36 requests** from it on four days. It identifies itself
honestly as `AgentReadinessScanner/1.0` with a link back to the site. It has
**never touched a honeypot path**. To be fair, that is expected rather than
admirable: it is an on-demand tool fetching a fixed list of well-known URLs,
not a crawler following links, and it comes only when someone presses the
button — on at least three of those four days, that was us.

The detail we did not expect is in the signature column. On 25 and 28 August
its requests carried no signature at all. Today every one of them arrived with
a valid **Web Bot Auth** signature, verified by this site's own verifier —
the [one that, until 17 November, had accepted one signed request out of
398](/blog/zero-verified). Somewhere between August and November, the
scanner that checks whether you publish a Web Bot Auth key directory started
signing its own requests. A checker that practises what it checks is rarer
than it should be.

## The point

A readiness score answers "have you published these files?". This site keeps
asking a narrower question: *does a signal tell you anything about
behaviour?* Here the answer cut both ways. The score missed a real mistake it
had detected and flagged a correct implementation as missing — and the scanner
itself, judged by its log entries, is one of the best-behaved bots that has
visited.

We will rerun the scan when the scanner's MCP check catches up with SEP-2127.
Until then, level 4 is the honest number.

## Sources and further reading

- [isitagentready.com](https://isitagentready.com) — the scanner; scans quoted here ran on 20 November 2026, and its checks may change after that.
- [SEP-2127: MCP Server Cards](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2127) — the chartering document, Final since 6 October 2026, including why cards exclude primitives.
- [experimental-ext-server-card: docs/discovery.md](https://github.com/modelcontextprotocol/experimental-ext-server-card/blob/main/docs/discovery.md) — the reserved `/server-card` location, the rejected `.well-known` alternative, CORS and caching.
- [experimental-ext-server-card: schema.ts](https://github.com/modelcontextprotocol/experimental-ext-server-card/blob/main/schema.ts) — the source of truth for the card's fields.
- [AI Catalog specification](https://github.com/Agent-Card/ai-catalog) — the `application/ai-catalog+json` media type and how catalogs embed Server Cards.
- [An AI catalog — from "findable" to "found"](/blog/ai-catalog) and [An MCP manifest — a specification with no standing](/blog/mcp-manifest) — the earlier discovery surfaces this post builds on.
- [Zero verified — our bug, not theirs](/blog/zero-verified) — why "verified" in this site's log only recently started meaning what it says.
