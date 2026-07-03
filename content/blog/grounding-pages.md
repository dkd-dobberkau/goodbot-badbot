---
title: Grounding pages — something true to cite
date: 2026-07-02
summary: We published two grounding pages — factual, machine-readable entity definitions — and made every read a measurement signal. Here is what they are, and why they are not compliance theatre.
---

This site already speaks several dialects of "please read me correctly" to AI
systems: a `robots.txt` with Content Signals, an `llms.txt` summary, an
`agents.md` probe surface, and Web Bot Auth keys. This week it learned one
more: **grounding pages**.

## What a grounding page actually is

It helps to separate three things that get blurred together:

- **llms.txt** decides *what* goes into an AI's retrieval pool. It is a
  declaration of which pages are worth reading — a table of contents for
  machines.
- **Grounding** is the runtime step where a model, answering a question, pulls
  documents from that pool and reasons over them instead of over its training
  memory. It is a live inference-time operation.
- **A grounding page** is a citable factual source *inside* that pool: a real
  HTML page, with its own URL, that defines one entity as plainly and
  verifiably as possible. It states facts and leaves the conclusion to the
  model — the opposite of an "instructions for AI" page that tries to script
  what the model should say.

The idea travels under the "Grounding Page Standard" banner. Worth being honest
about its status: that is a generative-engine-optimisation discipline, **not**
an IETF or W3C standard — the same footing as llms.txt. What is useful about it
is the editorial rule set: name the entity in your headings, keep the tone
factual rather than persuasive, and never hard-code a number that will rot —
link to the live source instead.

## Why this site has two

We published exactly two, because we have exactly two things worth grounding:

- [**goodbot-badbot**](/facts/goodbot-badbot) — the experiment itself,
  described as a `Dataset` whose distribution is the live `/api/stats` feed.
- [**robots.txt compliance**](/facts/robots-txt-compliance) — the concept we
  measure, described as a `DefinedTerm`.

Each page carries schema.org JSON-LD generated straight from its frontmatter,
so the words a human reads and the structured facts a machine extracts can
never drift apart.

## Not compliance theatre

Regular readers know this project's allergy to publishing signals it cannot
back up. We do not ship a DNS-AID record or an agent manifest, because the site
has no agent endpoint to advertise — doing so would be theatre.

Grounding pages pass that test for two reasons. First, they describe things
that genuinely exist: a running experiment and a real, measurable concept.
Second — and this is the part that fits the project — they are themselves a
**measurement surface**. Every read of a grounding page is logged exactly like
a read of `llms.txt` or `agents.md`: a positive discovery signal, the opposite
of a honeypot violation. You can watch which crawlers fetch them in the
[Discovery Reads](/) table on the dashboard.

So the site now offers agents something true to cite — and, true to form,
writes down who takes it up on the offer.

## Sources and further reading

- [The Grounding Page Standard](https://groundingpage.com/facts/grounding-page-standard/) — the editorial rule set this post draws on (a GEO discipline, not a formal standard).
- [Grounding vs llms.txt](https://www.runoctopus.com/glossary/grounding/grounding-vs-llms-txt.html) — the retrieval-pool-versus-inference distinction, spelled out.
- [llms.txt](https://llmstxt.org/) — Jeremy Howard's original proposal for the LLM-oriented site summary.
- [schema.org/Dataset](https://schema.org/Dataset) and [schema.org/DefinedTerm](https://schema.org/DefinedTerm) — the two vocabulary types our grounding pages emit as JSON-LD.
- [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) — the Robots Exclusion Protocol, the standard behind the compliance we measure.
