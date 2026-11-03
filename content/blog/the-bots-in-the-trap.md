---
title: The bots in the trap weren't the bots
date: 2026-11-03
summary: Of the 32 honeypot hits this site had charged to a named AI crawler, 18 came from eight clients that cycled through several crawlers' names from one address within seconds. Eight crawlers that looked guilty, ClaudeBot and Amazonbot among them, have no hit left once those are set aside. The scoreboard now does that automatically, with one limit we cannot get around: a client that borrows a single name still looks exactly like the real thing.
---

Since June, every visit to a honeypot path on this site has been charged to
whichever crawler the `User-Agent` header named. That was always the weak
point. [The files agents actually read](/blog/files-agents-actually-read)
called identification by user-agent "trivially spoofed", and the
[Unidentified bucket correction](/blog/unidentified-bucket) said it again: "A
scraper that sends `GPTBot` will be counted as GPTBot."

This time we went looking for that scraper, and it turned out we were
wrong in a more specific way.

## The pattern

On 4 June at 00:33:55 UTC, one address fetched all three visible link traps.
The first request said it was ChatGPT-User, the second PerplexityBot, the
third ClaudeBot. All three arrived within 26 milliseconds.

It was not a one-off. Grouping every visit by a named crawler by its
(hashed) address turns up eight clients that claim crawlers of *different
companies* within seconds of each other:

- **4 Jun 00:33:55:** ChatGPT-User, PerplexityBot, ClaudeBot. 3 trap hits.
- **29 Jun 09:44:06:** GPTBot, OAI-SearchBot, PerplexityBot. 3 trap hits.
- **8 Aug 07:27:27:** Amazonbot, Google-Extended, OAI-SearchBot. 2 trap hits.
- **10 Aug 10:05:34:** PerplexityBot, CCBot, Google-CloudVertexBot. 2 trap hits.
- **13 Aug 21:33:38:** ClaudeBot, Amazonbot. 1 trap hit.
- **20 Aug 16:49:07:** GPTBot, ClaudeBot, ChatGPT-User, Google-CloudVertexBot,
  PerplexityBot. 3 trap hits.
- **22 Aug 05:25:00:** Amazonbot, ChatGPT-User. 3 trap hits.
- **1 Nov 16:35:41:** cohere-ai, ChatGLM-Spider. 1 trap hit.

Times are UTC, and names are listed in the order the client used them.

The 20 August client used five names from four companies in about three
seconds. The 22 August client is the clearest about what it wanted: as
"Amazonbot" it asked for `/private/.env`, `/private/.env.production` and
`/private/aws_credentials.json`. None of those paths is linked anywhere. They
exist only as a `Disallow: /private/` line in `robots.txt`. Then it switched
to "ChatGPT-User". That is not an AI crawler misbehaving. It is a credential
scanner wearing AI crawlers' names, presumably because some sites wave those
names through.

Together these eight clients account for **18 of the 32 honeypot hits** this
site had attributed to a named crawler.

## What is left

With those 18 set aside, eight crawlers have no honeypot hit at all:
ClaudeBot, OAI-SearchBot, Amazonbot, PerplexityBot, CCBot, Google-Extended,
Google-CloudVertexBot and cohere-ai. Every hit those eight ever had came from
a rotating client. Four crawlers keep 14 hits between them:

- **PetalBot (Huawei): 6 hits** from five addresses between 8 and 16
  September. It has fetched `robots.txt` 39 times since it first appeared
  that month. This is the shape of a real crawler that reads the rules and
  then does not follow them, and it is the strongest case on the board.
- **Meta-ExternalAgent: 3 hits**, one per visible trap, from three addresses
  within three minutes on 4 July.
- **GPTBot: 3 hits** from one address in seven seconds on 6 June. This
  could be OpenAI, or a scanner that only ever borrowed one name. The
  data cannot tell those apart, which is the next section.
- **ChatGPT-User: 2 hits.** OpenAI's [own documentation](https://developers.openai.com/api/docs/bots)
  says this agent acts on a user's request, and "because these actions are
  initiated by a user, robots.txt rules may not apply." Whether that counts
  as a violation is a policy question. The scoreboard keeps counting it.

## The rule, and its limit

The [scoreboard](/#scoreboard-title) now applies this automatically:

> A visit by a named crawler is treated as spoofed when the same address
> sent a visit naming a crawler of a **different operator** within 60
> seconds.

It compares operators, not names, on purpose. OpenAI runs GPTBot and
OAI-SearchBot and could reasonably send both from shared infrastructure.
That is not deception, so it does not count. Within a burst, every named
visit is marked as spoofed, its `robots.txt` fetches included. What the
scoreboard subtracts is the trap hits. Visit counts stay as logged. Sixty
seconds is our choice. The longest of the eight bursts above took 14.3
seconds.

Spoofed hits are not deleted. They move to a [Spoofed hits](/#spoof-title)
panel of their own, and the API reports them separately. From now on
`violations` in [`/api/stats`](/api/stats) and in both MCP tools excludes
them. The new `spoofed_hits` field carries them, and the good-bot/bad-bot
verdict follows the cleaned number. This changes the meaning of a public
field, and anyone reading `violations` should know it did.

The limit is the 6 June GPTBot case. A client that picks one name and
sticks to it produces exactly the record the real crawler would. Nothing in
a User-Agent string can separate the two. The filter only catches clients
careless enough to rotate. A clean scoreboard row means "no hit we can
charge to this name," not "this crawler is proven well-behaved."

The thing that could close that gap is a cryptographic signature on the
request, [Web Bot Auth](/blog/good-bot-bad-bot). As of today no request to
this site has been verified with it. A separate post will explain why that
number is lower than it should be.

## The bigger number is untouched

The rule only reaches visits that carry a known crawler's name. The other
**1,370 honeypot hits** come from clients that name no AI crawler at all:
`mOptimizer`, a Chrome 129 user-agent with a truncated version string, a
"Pixel 6", and hundreds more. Those hits came from 420 hashed addresses, and
only 19 of those fetched `robots.txt` before their first trap.

That changes how the headline should be read. For almost all of the
anonymous traffic, the honest description is not "ignores `robots.txt`" but
"never asked." Ignoring a rule you have read and never reading it are
different behaviours, and only the first is a compliance question.

## Two corrections

- **July's "fairly clean" was not.** [The files agents actually
  read](/blog/files-agents-actually-read) called the named honeypot
  signal "small and, for once, fairly clean." Six of the named hits logged
  by then came from the 4 June and 29 June scanners above, and every
  Anthropic and Perplexity hit among them was one of those six.
- **Eight crawlers were shown as bad bots on a scanner's word.**
  ClaudeBot and PerplexityBot were listed as bad bots from 4 June,
  OAI-SearchBot from 29 June, four more from August, and cohere-ai from
  1 November, all on the strength of a scanner's guesses. That was our
  attribution, not their behaviour.

## Caveats

- **Addresses are hashed, not compared.** Bursts are detected on a salted
  hash of the IP address, which is never published, not even in the
  Spoofed hits panel. The salt was introduced on 7 September, so hashes from before and
  after that date are not comparable. That matters for distinct-address
  counts across months, not for a burst that lasts seconds.
- **Shared addresses could produce false positives.** Two unrelated
  crawlers behind one NAT or proxy, a minute apart, would be flagged. All
  eight bursts here are seconds apart and include obvious tells. A borderline
  case would show up in the Spoofed hits panel for anyone to check.
- **The rule judges names, not intent.** A real crawler and a scanner
  using its name at the same moment from different addresses never meet in
  this rule, so the real crawler keeps its record.

## Sources and further reading

- [Spoofed hits panel](/#spoof-title) — the bursts, live.
- [`/api/stats`](/api/stats) — `violations`, `spoofed_hits`, `spoof_bursts`.
- [OpenAI: Overview of OpenAI crawlers](https://developers.openai.com/api/docs/bots) — ChatGPT-User and robots.txt.
- [The Unidentified bucket — a correction](/blog/unidentified-bucket) — where the anonymous traffic was first taken apart.
- [The files agents actually read](/blog/files-agents-actually-read) — the July snapshot corrected above.
