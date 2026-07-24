---
title: An AI catalog — from "findable" to "found"
date: 2026-07-24
summary: A week after the API catalog, we added a /.well-known/ai-catalog.json — an Agentic Resource Discovery manifest. The API catalog helps an agent that already knows this site; the AI catalog is what gets the site into agent-facing registries so it can be discovered in the first place. It is a fourth discovery axis, it points at the same OpenAPI we already had, and — following Dries Buytaert again — we fully expect the column to read zero until the registries that would crawl it actually exist.
---

Last week this site published an [API catalog](/blog/api-catalog): a
`/.well-known/api-catalog` that hands an agent a documented way into our stats
API. But that catalog has a precondition baked in — an agent only finds it *if
it already knows to look at goodbot-badbot.com*. It answers "how do I use this
site", not "does this site exist". This week we added the missing half: a
**`/.well-known/ai-catalog.json`**, an [Agentic Resource
Discovery](https://dri.es/helping-agents-discover-my-site-search-with-agentic-resource-discovery)
manifest, again following [Dries Buytaert's](https://dri.es/) lead.

## What it is

ARD brings search-engine-style discovery to agents. The idea: publish a small
manifest advertising your machine-readable resources, and **registries crawl
the web, index those manifests, and return ranked results when an agent asks a
question**. An agent that has never heard of this site can then be pointed at it
because its question matched what we advertise. Ours declares a single entry:

```json
{
  "specVersion": "1.0",
  "host": { "displayName": "goodbot-badbot" },
  "entries": [
    {
      "identifier": "urn:air:goodbot-badbot.com:stats",
      "displayName": "robots.txt compliance statistics",
      "type": "application/openapi+json",
      "url": "https://goodbot-badbot.com/openapi.json",
      "description": "Live statistics on which AI crawlers obey robots.txt …",
      "representativeQueries": [
        "Which AI crawlers ignore robots.txt?",
        "Show robots.txt compliance rates by bot operator",
        "Does GPTBot respect crawl directives?",
        "How many bots tripped the honeypot?",
        "Is a given AI crawler a good bot or a bad bot?"
      ]
    }
  ]
}
```

Note what it points at: the exact same `/openapi.json` the API catalog already
reuses. Like Dries, we spent almost no time on this because we had nothing new
to describe — the interface, the OpenAPI document, and the prose all existed.
The manifest is a second doorway onto one room.

The one field that is genuinely new is **`representativeQueries`** — the sample
questions a registry matches against an agent's intent. Dries' are broad
("Find posts about the future of Drupal") because his resource is full-text
search. Ours are narrow on purpose: this site can answer exactly one kind of
question well — *which crawlers obey `robots.txt`* — so the queries name that
subject directly instead of pretending to be a general search box.

## Why it fits: a fourth axis

This project's whole discipline is keeping distinct signals distinct, and ARD is
a genuinely new one, not a rename of the last:

- A **honeypot** tests a *rule* — visit a `Disallow` path, get logged as a
  violation. Feeds the verdict.
- A **discovery read** (`llms.txt`, `agents.md`, grounding pages) tests
  *curiosity* — an agent that already found us reading a hint.
- The **API catalog** tests an *offer taken up* — an agent that already found us
  using the documented interface instead of scraping.
- The **AI catalog** tests *findability itself* — whether the registries that
  would surface this site to agents who have never heard of it are real yet.

So it gets its own **`ai catalog`** column in the [Discovery Reads](/) table,
separate from the API catalog rather than folded into it. The two look similar
on the wire — both are just a bot fetching a JSON offer — but they answer
different questions, and on a *measurement* site the difference is the data.
A read here most likely means an ARD registry crawler, not an end-user agent;
keeping the column separate is how we would ever see one show up. And like every
other offer, it stays **out of the good/bad verdict** — not being in a registry
is not misbehaviour.

## The honest part

The API-catalog post ended by predicting the column would read zero for months,
because almost nothing queries API catalogs yet. The AI catalog is a rung *below*
that on the honesty ladder, and it is worth being blunt about why.

An API catalog at least has a defined consumer: any agent that reaches your
`.well-known/` directory. ARD's consumer is a **registry**, and the registries
have to exist and be crawling before a single manifest gets indexed. As Dries
notes, whether this matters at all depends on whether the big agent platforms
start querying ARD registries — and, tellingly, **OpenAI and Anthropic are not
in the ARD working group** today; Microsoft, Google and GitHub are. So we are
publishing into an ecosystem whose readers are not confirmed to exist.

For most sites that is a reason to wait. For this one it is the assignment. "Six
months live, zero registry reads" is exactly the kind of negative evidence this
site exists to publish instead of hype. A quiet `ai catalog` column is not a
failed feature — it is a dated, honest measurement of how far the agent
ecosystem is from the discovery story everyone is already narrating. If the
column ever turns non-zero, we will know which registry got there first, and
when.

## Keeping the trap out, again

The same rule as last week applies, for the same reason: the manifest advertises
only the real, public API. No honeypot path appears in it — an offer contains
only what you actually mean to give. The one wrinkle is that our
`representativeQueries` literally include the word *honeypot* ("How many bots
tripped the honeypot?"), because the honeypot is the site's subject, not a
secret. So the test that guards the manifest checks for honeypot *paths* (with
their leading slash), not the bare word — the invariant is that no trap URL
leaks, not that we never say what the site is about.

So the site now has two doorways for agents: one for the agent that already
found us, one aimed at the machinery that might help an agent find us at all —
and, true to form, a column that will quietly record whether either gets used.

## Sources and further reading

- [Dries Buytaert — Helping agents discover my site search with Agentic Resource Discovery](https://dri.es/helping-agents-discover-my-site-search-with-agentic-resource-discovery) — the experiment this post follows, including who is and isn't in the working group.
- [Dries Buytaert — Helping agents discover my site search with an API catalog](https://dri.es/helping-agents-discover-my-site-search-with-an-api-catalog) — the predecessor, and our own [API catalog post](/blog/api-catalog).
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — the description format served at `/openapi.json`, which both catalogs point at.
