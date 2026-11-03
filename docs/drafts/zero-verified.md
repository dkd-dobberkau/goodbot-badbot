---
title: Zero verified — our bug, not theirs
date: 2026-11-XX
summary: Twice this blog reported that Web Bot Auth sat at zero verified requests, and read that as crawlers not signing. They were signing. Since June, 314 signed requests reached this site, 297 of them from AhrefsBot, and our verifier rejected every one of them. It had been written against a version of the protocol that was already seven months out of date. This is what went wrong, how it was fixed, and what the number says now.
---

<!-- TODO before publishing:
     - Fill in the date and the "What the number says now" section from the
       Friday query (rows since 2026-11-03 10:25 UTC). Publish only if
       production shows `verified` rows; if not, this post waits.
     - Publish together with docs/drafts/signed-requests-primer.md and fix the
       link below to its final slug.
     - Add dated correction blockquotes under the two quoted claims in
       files-agents-actually-read.md and unidentified-bucket.md. -->

In July, [The files agents actually read](/blog/files-agents-actually-read)
listed Web Bot Auth among the things nobody uses: "**Zero verified requests
in 51 days.**" In August, [the Unidentified bucket
correction](/blog/unidentified-bucket) repeated it: Web Bot Auth "still sits
at zero verified requests." Both times the number was right, and both times
we drew the wrong conclusion from it. Zero meant our verifier accepted
nothing, not that nobody was signing.

## What was actually arriving

Every request that carries a signature is checked and its result stored with
the visit. Since 12 June the log holds **314 signed requests**, and all 314
are marked `failed`:

- **AhrefsBot: 297**, from 285 different addresses. AhrefsBot signed every
  request it sent here. There is not a single unsigned AhrefsBot visit in
  the log.
- **ibou-search and IbouBot: 14**, since October.
- **Pandalytics: 3**, since July.

The weekly count grew from three in June to around twenty since late
August.
None of the 314 touched a honeypot. They read `robots.txt` and the sitemap
and occasionally a grounding page, which is what a well-behaved crawler does.

A dashboard column of failures from one large, well-documented crawler,
with no successes from anyone, should have looked like a verifier problem
from the start. Nobody here looked at the failure column.

## Why every signature failed

AhrefsBot publishes its keys where the protocol says, at
`/.well-known/http-message-signatures-directory`: two Ed25519 keys, each
labelled with its own thumbprint. Their directory was in order. Our
verifier had three faults. For a crawler signing in the current form of the
protocol, any one of them was enough to reject every request. Which form
AhrefsBot sends we cannot see, because the header is not stored. The
section after the fixes shows what happened once they went live.

**1. We parsed the header in its old format.** A signed request names the
location of its keys in a `Signature-Agent` header. Early drafts made that
a plain string:

```
Signature-Agent: "https://crawler.example/…"
```

Revision -04 of the directory draft, published on 20 October 2025, changed it
to a dictionary keyed by the signature's label:

```
Signature-Agent: sig1="https://crawler.example/…"
```

We wrote our verifier on 3 June 2026, more than seven months later, and wrote
it against the string form. It was out of date on the day it shipped. Every
request in the current form was rejected before a single key was fetched.

**2. Our library signed the wrong thing.** The new form signs one dictionary
member, written as `"signature-agent";key="sig1"`. Version 2 of the Python
library we use ignored that `key` parameter and computed the signature
over the whole header instead. The recomputed signature could never match.
Version 3 resolves the member correctly. We now require it.

**3. We checked the required parts by exact text.** The protocol requires
the signature to cover the site's address and the `Signature-Agent` entry.
We compared against the literal string `"signature-agent"`, which the
keyed form, `"signature-agent";key="sig1"`, never equals.

## Fixing it took three attempts

The first fix handled all three faults and passed its tests. In production
it still failed, because the deployed image had installed version 3 of the
library while the development machine still had version 2.
`requirements.txt` only set a minimum version, so every build picked up
whatever was newest. Our workaround for version 2 broke version 3. The
second fix pinned the library to version 3 and removed the workaround.

Rereading the protocol for this post turned up the third problem. The drafts
we had followed expired in September 2026. Their successor is now an IETF
working group document,
[draft-ietf-webbotauth-httpsig-protocol-01](https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/)
(29 October 2026), and our verifier fell short of it in three ways. It
required `@authority` where `@target-uri` is equally valid. It did not fall
back to a key's thumbprint when the directory labels its keys differently.
And one gap mattered more than the rest: it merged the keys of every
directory a request listed. A signature covering one directory could
therefore verify with a key from another. The draft forbids that outright
(§5.2.2): "A verifier MUST NOT attribute a signature to a member that
signature does not cover." Because nothing was ever verified, this never
produced a false result. Once the first fix worked, it could have.

All three are fixed. The test suite now also checks the working group's
own example signature against the pinned library, so a future update that
breaks this again fails before it ships.

## What the number says now

<!-- TODO Friday 2026-11-06: replace with the result.
     If verified: "Since the fix went live on 3 November at 10:25 UTC, N
     signed requests have arrived; N verified, N failed." Name the agents.
     Note that a verified AhrefsBot proves only that the requests came from
     whoever controls ahrefs.com's key directory — which, at the well-known
     path on its own domain, is Ahrefs.
     If some still fail: say so and say what is known about why.
     A verified AhrefsBot also settles which header form it sends (the
     dictionary form, since the old verifier handled the string form) —
     only then may the "why every signature failed" section say so. -->

## What a verified request does and does not tell you

A valid signature proves that whoever controls the key directory named in
the request signed it. It does not prove that the signer is honest, and
anyone can host a directory. What it does give is a stable identity that
cannot be borrowed: the bursts in [The bots in the trap weren't the
bots](/blog/the-bots-in-the-trap) only worked because a User-Agent costs
nothing to fake. A signature from ahrefs.com's directory cannot be faked
without Ahrefs' private key. [How a crawler signs a request — and what that
proves](/blog/signed-requests-primer) explains the mechanism from the ground
up.

## Corrections

- **"Zero verified requests in 51 days"** in [The files agents actually
  read](/blog/files-agents-actually-read) and **"still sits at zero verified
  requests"** in [The Unidentified bucket](/blog/unidentified-bucket) were
  accurate counts with the wrong reading. AhrefsBot had been signing since
  12 June, and our verifier rejected it. Both posts now carry a correction
  pointing here.

## Sources and further reading

- [draft-ietf-webbotauth-httpsig-protocol-01](https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/) — the current protocol, §5.2 (components), §5.2.1 (`Signature-Agent`), §5.2.2 (one signature, one directory).
- [draft-meunier-http-message-signatures-directory-04](https://datatracker.ietf.org/doc/draft-meunier-http-message-signatures-directory/04/) — 20 October 2025, the revision that made `Signature-Agent` a dictionary.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421.html) — §2.1.2, the `key` parameter our library ignored.
- [How a crawler signs a request — and what that proves](/blog/signed-requests-primer) — the mechanism, from the ground up.
- [The bots in the trap weren't the bots](/blog/the-bots-in-the-trap) — why an unforgeable identity matters here.
