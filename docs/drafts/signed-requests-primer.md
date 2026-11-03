---
title: How a crawler signs a request — and what that proves
date: 2026-11-XX
summary: A User-Agent string is a claim anyone can type. Web Bot Auth replaces it with a signature: the crawler signs each request with a private key and says where its public keys live, and the site checks one against the other. This is how that works, which standard it rests on, and — the part most write-ups skip — exactly how little a valid signature proves.
---

Every visit this site logs carries a `User-Agent` header, and every
honeypot statistic on the dashboard is grouped by it. That is a weak
foundation, and we know it. A User-Agent is a string the client picks.
Typing `ClaudeBot` costs nothing, and the log is full of clients that try
several names in a row: one address announcing itself as ClaudeBot,
ChatGPT-User, GPTBot and PerplexityBot within four seconds. A
[follow-up post](/blog) looks at that pattern in the honeypot data.

[Web Bot Auth](https://datatracker.ietf.org/wg/webbotauth/about/) is the
attempt to replace that claim with something checkable. This post explains
the mechanism from the ground up, because we are about to publish numbers
that depend on it, and those numbers only mean something if it is clear
what they measure.

## The standard underneath: RFC 9421

The cryptography is not new. [RFC 9421, HTTP Message
Signatures](https://www.rfc-editor.org/rfc/rfc9421.html), was published in
February 2024 and is a general way to sign parts of an HTTP message. It
defines three things:

- **Components.** The parts of the message being signed. Some are header
  fields (`content-type`). Others are *derived* components that start
  with `@` and describe the request itself: `@authority` is the host
  (`goodbot-badbot.com`), `@path` the path, `@method` the verb.
- **The signature base.** A canonical text, one line per covered
  component, ending with a line that lists the components and the
  signature's parameters. Signer and verifier both build this text from
  the message. If a single byte differs, the signature fails.
- **Two headers.** `Signature-Input` names the components and parameters,
  `Signature` carries the bytes. Both are keyed by a label, so one request
  can carry several signatures.

For a crawler fetching `/robots.txt` here, the signature base looks roughly
like this:

```
"@authority": goodbot-badbot.com
"signature-agent";key="sig1": "https://crawler.example/.well-known/http-message-signatures-directory"
"@signature-params": ("@authority" "signature-agent";key="sig1");created=1793700000;expires=1793700300;keyid="…";alg="ed25519";tag="web-bot-auth"
```

The crawler signs that text with its private key. The site rebuilds the
same text from the request it received and checks the signature against
the public key.

## What Web Bot Auth adds

RFC 9421 says how to sign. It does not say *who* is signing or where to
find their key. The IETF chartered the Web Bot Auth working group to fill
that gap for automated traffic. Its protocol document,
[draft-ietf-webbotauth-httpsig-protocol](https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/),
is on revision 01 (29 October 2026) and aims for the Standards Track. It
grew out of two individual drafts by the same authors, from Cloudflare and
Google, which expired in September 2026. It is still a draft, and it has
changed under implementers before. The next section shows how.

The working-group draft fixes a profile on top of RFC 9421:

- **`tag="web-bot-auth"`** marks the signature as this protocol's.
- **`created` and `expires`** are mandatory. The draft recommends a
  lifetime of no more than 24 hours.
- **`keyid` is a thumbprint of the key**, a SHA-256 hash of the public key
  per [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638.html), not a name
  the operator chooses.
- **At least `@authority` or `@target-uri` must be covered**, so the
  signature is bound to this site and cannot be replayed against another.
- **A `Signature-Agent` header** says where the public keys are: an `https`
  URL that serves a JSON Web Key Set, by convention at
  `/.well-known/http-message-signatures-directory`. The member of that
  header that belongs to the signature must itself be covered by the
  signature.

## The header that changed shape

`Signature-Agent` is where we got caught. Early drafts defined it as a bare
string:

```
Signature-Agent: "https://crawler.example/…"
```

The current draft makes it a *dictionary* keyed by the signature label,
and covers the member with a `key` parameter:

```
Signature-Agent: sig1="https://crawler.example/…"
Signature-Input: sig1=("@authority" "signature-agent";key="sig1");…
```

The two forms differ by a few characters on the wire, and a verifier that
expects one cannot read the other. The draft allows verifiers to keep
accepting the old form during the transition, but signers must send the
new one. A verifier written against an earlier draft rejects every
up-to-date signer. That is what happened here, and [the correction](/blog)
has the numbers.

## What a valid signature proves

This is the paragraph to keep in mind when reading the dashboard. The
working-group draft puts it unusually plainly (§4.1):

> A valid signature over a resolved URL proves that a holder of a key that
> URL publishes signed the covered message. […] It says nothing about who
> operates the Agent, whether the Agent is benign, or whether the request
> is authorized.

In practice:

- **The identity is the URL, not a name.** A verified request means
  "whoever controls `https://crawler.example/…` signed this." Anyone can
  host a key directory, so a scraper can sign perfectly valid requests
  under its own URL. A signature makes a visitor *recognisable across
  requests*. It does not make them *trustworthy*.
- **The URL is only worth what its host is worth.** The draft notes that
  TLS authenticates the host, not the path. A directory at the well-known
  path is vouched for by the domain operator. One at an arbitrary path
  only shows that someone could put a file on that host.
- **Replay is bounded, not prevented.** A signature over `@authority` alone
  is valid for any request to this site until it expires. Covering
  `@method` and `@path` narrows that, but the draft does not require it.
- **An unsigned request proves nothing either.** Most legitimate crawlers
  do not sign yet. "Unsigned" means "no claim was made," not "suspicious."

So the dashboard's *verified* column does not mean "this really was
Anthropic" or "this bot is good." It means "this request came from the same
key holder as every other request under that URL," which turns a guessable
string into a stable identifier. For a site that ranks crawlers by
behaviour, that is exactly what is missing: if a signed crawler walks into
a honeypot, it cannot be blamed on someone wearing its name.

## What this site does with it

Every request that carries `Signature` and `Signature-Input` is checked,
one signature label at a time (at most three per request). For each label
the site:

1. requires that it covers `@authority` or `@target-uri`, plus the
   `Signature-Agent` member keyed to that label;
2. takes the directory URL from *that* member only, ignoring members with
   parameters and anything that is not `https`;
3. fetches that directory (cached for an hour) and finds the key by `kid`
   or, failing that, by its thumbprint;
4. rebuilds the signature base and verifies it, with an age limit of one
   day.

A visit is stored as *verified* if any label passes, as *failed* if the
request was signed but none did, and with no status if it was unsigned.
The site does not block or favour anyone based on the result. As with
robots.txt, the point is to measure, not to enforce.

<!-- TODO before publishing:
     - Fill in date, and the two /blog links (spoofing post, correction post).
     - If we start storing the verifying URL, say so here: it is what makes
       "verified" an identifier rather than a checkbox. -->

## Sources and further reading

- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421.html), the signing mechanism.
- [draft-ietf-webbotauth-httpsig-protocol-01](https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/), the Web Bot Auth protocol: `Signature-Agent`, key directory, well-known URI.
- [IETF Web Bot Auth working group](https://datatracker.ietf.org/wg/webbotauth/about/), charter, mailing list and documents.
- [RFC 7638 — JWK Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html), how `keyid` is derived from the key.
- [RFC 9651 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc9651.html), the string-versus-dictionary distinction that broke our verifier.
- [Good bot, bad bot](/blog/good-bot-bad-bot), how the site measures in the first place.
