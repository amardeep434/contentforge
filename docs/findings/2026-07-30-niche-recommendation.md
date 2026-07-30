# Niche recommendation — 2026-07-30

**Recommendation: long-form public-domain art history — single-artist biographies,
17–22 minutes, one artist per video.**

Claim IDs refer to [claims-ledger.md](claims-ledger.md).

---

## The two real candidates

The 146-channel scan produced seven repeatable channels (C-020). Only two niches
had more than one, or a profile a new channel could plausibly reach.

```
                      aviation                        art history
repeatable channels   2 of 14 (14%, best measured)    1 of 9 in history
exemplar              Pilot Debrief                   Art History Explained
  subscribers         1,030,000                       16,700
  median views        788,580                         112,326
  views per sub       0.8                             6.7
  skew                1.4                             1.0
  hit-rate            100%                            62%
  n                   43                              8
```

## Why art history wins on the criteria that bind

### 1. It is the only reachable profile (C-023)

Art History Explained produces a 112,326 median from **16,700 subscribers** —
6.7 views per subscriber, against 4.2 for the next best and under 2.0 for most
repeatable channels. It is doing this with 8 videos in 280 days.

Both aviation exemplars sit at 237K and 1.03M subscribers. A channel at that size
draws views from its subscriber base and its accumulated algorithmic standing.
Nothing about their performance tells us what a new channel can do — which is
precisely the error C-007 was withdrawn for.

### 2. Copyright position is materially better (C-033)

Faithful reproductions of public-domain 2D artworks carry no new copyright:
*Bridgeman v. Corel* in the US, Article 14 of the EU DSM Directive in Europe.
The Met, the Rijksmuseum and the Art Institute of Chicago all publish open-access
APIs. The primary visual asset is free, legal, and available at scale.

Aviation's compelling footage is news video and CCTV — Content ID territory
(C-030). NTSB reports and imagery are US federal works and public domain, but
they are documents, not watchable footage.

### 3. Aviation sits near an advertiser-suitability edge

YouTube's advertiser-friendly guidelines assign **limited ad earnings** to
accidents with "visible injury or extreme impact moments," and **no ad earnings**
to content that "profits from or exploits a sensitive event."

Pilot Debrief plainly clears this bar. But it is a standing risk applied per
video, to a channel with no track record, in a niche whose entire subject is
people dying. Art history has no equivalent exposure.

### 4. The format fits the architecture we already built

Artist biographies are dates, places, documented events and quotable
contemporaries — every claim resolves to a citable source. That is exactly what
`provenance.py` and `script/validate.py` enforce. Aviation incident analysis
needs technical accuracy about causes, where being wrong is both more likely and
more consequential.

### 5. Long runtime multiplies revenue per view

Art History Explained runs 17–22 minutes. Videos over 8 minutes carry multiple
mid-roll slots, so effective revenue per view sits well above the nominal RPM
for the same view count on a short video.

### 6. Evergreen, not news-pegged

A Cézanne biography is as valid in three years as today. Incident analysis
competes on speed against well-resourced incumbents.

## Where art history loses, stated plainly

**RPM is mid-tier.** `data/niches.csv` lists US history at $5–12 against tech at
$15–25. If aviation classifies as tech or education it earns more per view.

⚠️ **Those RPM figures are weakly sourced.** They come from `fluxnote.io` and
`becomeviral.com` — the same marketing-blog tier rejected as unusable for
research on 2026-07-29. They are directionally plausible and should not be
treated as measured. Real RPM is only knowable from our own Studio data.

**n=8 is the thinnest sample in the repeatable table.** One channel, eight
videos. This is a hypothesis (C-023), not an established result.

**The deciding capability is untested.** Art History Explained's advantage is
narrative writing — turning a biography into a story with stakes. Whether an
LLM pipeline produces that at quality is the single largest unknown, and nothing
observational can settle it (C-028).

## What the product actually is

- 17–22 minute single-artist biography, one artist per video
- Public-domain artworks from open-access museum APIs, slow pans
- Openly-licensed or public-domain b-roll for period and place
- TTS narration (edge-tts), no face, no captions burned in
- Chronological life story built around a documented reversal — obscurity,
  rejection, late start, personal crisis
- Every factual claim carries a source URL and retrieval timestamp

Start with artists who are unambiguously public domain and already carry
audience interest: Cézanne, Monet, Degas, Klimt, Klee, Kandinsky all clear
life+70. Avoid anyone still in copyright — Picasso is not public domain until
2043.

**On format: copy the exemplar's house style deliberately.** C-027 established
that opening style is a channel-level constant, not a per-video variable. It is
therefore a one-time decision, and there is no reason to invent one when a
measured format exists. Within Art History Explained the reversal-driven opening
coexists with a 112,326 median at skew 1.0 (C-014, valid at that scope).

## Monetisation-policy guard (C-032)

The inauthentic content policy targets "content made with a template" that
"doesn't deliver creative, educational, or other value". A rigid biography
template is exactly the shape it describes.

The winning channels pass because each video carries distinct authored
substance, not because their template varies. So:

- Each video must contain research specific to that artist — not a name
  substituted into a fixed frame.
- Never read source material verbatim; the overlap ceiling in
  `script/validate.py` is a monetisation control, not a stylistic one.
- Visuals must be selected for the specific narrated beat.

## What would change this recommendation

- Art History Explained's next 4–6 videos regressing toward its 3.7K–5.2K floor
  would show the 112,326 median was a short run, not a profile. **Cheap to check
  — 2 quota units. Worth rechecking before the first upload.**
- Finding a repeatable channel under ~30K subscribers in a higher-RPM niche
  (finance $20–40, business $15–30, tech $15–25). The scan covered none of those
  three properly: economics returned 3 channels, technology 4.
  **`scan-rev2-all-candidates.csv` holds 1,189 channels already found — re-filtering
  costs zero quota.**
- Our own first videos showing the narrative-writing gap is unbridgeable, in
  which case a format that leans on structure rather than storytelling is better.

## Recorded as

C-034 in the claims ledger — status `HYPOTHESIS`, since it rests on C-023 (n=8)
and C-021 (n=14 channels), neither confirmed.
