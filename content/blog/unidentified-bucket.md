---
title: The Unidentified bucket — a correction
date: 2026-08-20
summary: In July we reported that grounding pages are the file agents actually read, and said we would keep watching before saying it louder. We kept watching, and then we looked inside the bucket the numbers were sitting in. Of 327 discovery reads, 9.5 % came from an identifiable AI crawler. The rest were SEO crawlers, proxy-rotating scrapers wearing browser user-agents, and — embarrassingly — our own deploy checks. The finding survives. The evidence base is a fifth of what we claimed.
---

Four weeks ago this blog published [The files agents actually
read](/blog/files-agents-actually-read): after 51 days of logging, grounding
pages were being fetched an order of magnitude more often than `llms.txt` and
`agents.md` combined. We called it "mildly heretical", noted that 136 reads is a
thermometer rather than a proof, and promised to keep watching before saying it
louder.

We kept watching. Then we did something we should have done first: we looked at
*who* those 136 reads came from.

That post contains this caveat, in its own words:

> "Anonymous" is not a synonym for "AI crawler".

We wrote that about the honeypot numbers. We did not apply it to the discovery
numbers on the same page. This post is the correction.

The numbers below are a snapshot as of 20 August 2026 — 78 days of logging,
2,544 requests. The live version is always at [`/api/stats`](/api/stats).

## What the bucket was hiding

The Discovery Reads table used to have one row called **Unidentified**, which
simply meant "the user-agent string did not match our AI-crawler registry". By
August that single row accounted for 92 % of every discovery read on the site.
A category holding 92 % of your data is not a category. It is a place where you
stopped looking.

Sorting the same reads by what the caller actually is:

- **Non-AI crawler** — self-declared SEO, search and scanning bots —
  **141 reads (43.1 %)**.
- **Browser UA** — the string claims to be a browser — **116 reads (35.5 %)**,
  across 30 distinct user-agent strings.
- **HTTP client** — a named library (curl, Go, httpx) and nothing more —
  **32 reads (9.8 %)**.
- **AI crawler** — a bot from the registry this site actually tracks —
  **31 reads (9.5 %)**.
- **Unidentified** — genuinely nothing to go on — **7 reads (2.1 %)**.

The heaviest reader of our grounding pages is not an AI crawler. It is
something calling itself `mOptimizer/1.0` behind a forged Chrome string: 56
reads from 20 different IP addresses. Second and third are a "Pixel 6" and an
"iPhone" — 25 reads from 25 IPs, and 24 reads from 23 IPs respectively. Roughly
one request per address is not how a browser behaves. It is how a residential
proxy pool behaves.

Of the 288 grounding-page reads logged in total, **27 came from an identifiable
AI crawler**. In July we reported 136 and drew a conclusion from it.

## The readers and the violators are the same actors

Those top three grounding readers have another line in the database. Between
them they account for 362 honeypot hits — fetches of paths this site forbids in
`robots.txt` and links nowhere a human would click.

- `mOptimizer/1.0` — 56 grounding reads, **192 honeypot hits**.
- "Pixel 6 / Chrome 114" — 25 grounding reads, **123 honeypot hits**.
- "iPhone OS 13_2_3" — 24 grounding reads, **47 honeypot hits**.

The same pattern holds across the whole honeypot table: of 867 violations,
**68 % come from something wearing a browser user-agent** and 28 % from
self-declared SEO crawlers. Identifiable AI crawlers account for 2.5 %.

So the surface we built as the opposite of a honeypot — a factual page offered
freely, where a read is a *positive* signal — is being consumed mostly by the
same clients that walk straight into the traps. The invitation and the trap have
largely the same audience. That is not what we expected to find, and it is worth
more than the reading we published in July.

One small forensic detail, since this project enjoys them. Several of the
heaviest violators send `Safari/537.3` where every real browser sends
`Safari/537.36` — a single missing character, in three otherwise different
user-agent strings. It is not our truncation; our cap is 1,024 characters and
the strings are 110 and 145. It is a bug in somebody's user-agent table, and it
ties their rotating identities together better than anything they disclose
voluntarily.

## What survives, and what does not

The July claim was that grounding pages are read far more than `llms.txt` and
`agents.md`. Restricted to identifiable AI crawlers, the current numbers are:

- **Grounding pages** — 27 reads.
- **`llms.txt`** — **0 reads.**
- **`agents.md`** — **0 reads.**

The direction survives. In fact it is starker than we claimed: not "read less",
but *not read at all* by any named AI crawler in 78 days. What does not survive
is the magnitude, and the confidence that came with it. We built a story about
inference-time retrieval beating crawl-planning on 136 data points. The honest
figure is 27, and 27 reads will not carry that story.

There is a second finding hiding in the same table. `llms.txt` has been read 18
times overall, and the split is: 6 by self-declared non-AI crawlers — BuiltWith
and Dataprovider among them — 7 by browser-shaped strings, 4 by scripted HTTP
clients, 1 unidentified, and none at all by a named AI crawler. Its demonstrated
audience right now is **technology-profiling and SEO tooling**. The file
everyone is told to publish is being consumed, just not by the readers it was
written for.

## What changed on the dashboard

Three things, all of them subtraction rather than addition:

**Our own traffic is gone.** Deploy and verification requests from this project
now identify themselves with a marker and are dropped before they are logged —
including retroactively, so the historical rows stop counting too. The July post
noticed this and shrugged it off in a sentence: *"The two the dashboard shows
are our own `curl` verifying the deploy."* We wrote it down and kept counting it
anyway. A site that measures crawlers should not have itself in the numerator.

The sharpest example only turned up while verifying the deploy of this very
change. The dashboard had been reporting **1 HEAD probe** since August. There is
exactly one `HEAD` row in the entire database, and it reads
`probe-split-check/1.0` — the throwaway user-agent we used on 5 August to test
that reads and probes were being counted separately. The probe column's only
entry was the test that built it. It now reads zero, which is the honest number:
since this site stopped answering `HEAD` with `405`, no crawler has probed a
single file.

**The bucket is now five classes**, assigned from the user-agent at query time.
Nothing is stored, so improving the classifier reclassifies the entire history
at once.

**"Browser UA" is deliberately not called "Browser."** The class name describes
what the string *claims*, not what the client *is* — because on the evidence
above, most of the traffic in it is not a person with a browser. Naming it
"Browser" would have replaced one misleading label with a more confident one.

We also found `DeepSeekBot` sitting in the unidentified pile: a real AI crawler,
absent from our curated list *and* from the Cloudflare Radar dataset we vendor.
It is registered now. There are certainly others.

## The caveats, stated plainly

- **Classification is still by user-agent string**, which is exactly as
  spoofable as it was before. A scraper that sends `GPTBot` will be counted as
  GPTBot. This moves the resolution from one bucket to five; it does not solve
  identity. [Web Bot Auth](/blog/good-bot-bad-bot) is the thing that would, and
  it still sits at zero verified requests.
- **"Non-AI crawler" is a claim too.** SeznamBot and AhrefsBot are counted as
  what they say they are.
- **27 reads is a smaller thermometer than 136.** Every hedge in the July post
  applies here with more force, not less.
- **This correction does not touch the honeypot verdicts.** Those were always
  computed per named bot, and no named bot's compliance record changes.

The uncomfortable part is not that the numbers moved. It is that we published a
caveat about anonymous traffic in one section and then reasoned as though it did
not apply two sections above. Running the experiment in the open is supposed to
catch that — so here it is, caught, with the table rebuilt so the next person
reading it cannot make the same mistake as easily as we did.

## Sources and further reading

- [The files agents actually read](/blog/files-agents-actually-read) — the July post this one corrects.
- [Discovery Reads](/) — the rebuilt table, live.
- [`/api/stats`](/api/stats) — the raw JSON behind every number above.
- [Dark Visitors](https://darkvisitors.com/agents) — the AI-crawler user-agent registry this site's curated list draws on.
- [Cloudflare Radar's verified bots](https://radar.cloudflare.com/traffic/verified-bots) — the second source we merge in, and the one that was also missing DeepSeek.
- [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) — the Robots Exclusion Protocol, the standard behind the compliance we measure.
