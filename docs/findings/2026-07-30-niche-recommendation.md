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

---

# Revision after falsifiers — 2026-07-30

Both falsifiers were run before building. Results below; the recommendation
**stands but its justification changes materially**.

## F2 — no better alternative exists. Recommendation survives.

Proper searches of finance, investing, business, software, tech and economics
(niches the main scan covered badly) profiled 31 channels and found **zero
repeatable ones** (C-036). Re-filtering the 1,189 stored candidates at zero quota
and scanning the 6 that qualified added none.

Best reachable performers anywhere in a high-RPM niche:

```
Tech Explained        13,200 subs   median 38,826   hit 21%   v/sub 2.9
Tech Explainer Guy    10,200 subs   median 24,684   hit 22%   v/sub 2.4
```

Both miss the 40% hit-rate bar.

## F1 — the exemplar held, but the niche does not. This damages the case.

Two separate results, pulling opposite ways.

**The exemplar forward-tested clean (C-037).** Art History Explained published a
9th video between scans. Median moved from 112,326 to 111,040 — under 1.2% — and
skew stayed at 0.9. The prediction was made before the video existed. It did not
regress.

**But no peer replicates it (C-035).**

```
channel                      subs      n     median  skew  hit%  v/sub
Art History Explained      16,700      9    111,040   0.9   56%   6.6
Narrative Art History      23,300     16     26,106   1.8    6%   1.1
FINE ART EXPLAINED            994     18      1,312   4.9    0%   1.3
Chronicles & Chills        11,900     16        617   1.7    0%   0.1
```

Narrative Art History is **larger and earns 6x less per subscriber**.

So Art History Explained is an outlier *within* art history, not evidence that
art history is a strong niche. The original recommendation leaned on "this is the
only reachable repeatable profile" as though the niche carried the property. It
does not. Entering art history does not buy those numbers.

## What the recommendation now rests on

Across 177 channels profiled in total, exactly **one** reachable repeatable
channel exists, in any niche. That is n=1. **The niche choice cannot be justified
on measured demand — there is no pattern to point at**, and C-028 already
established the deciding variable is invisible from outside.

So the decision falls to the criteria that *are* well-evidenced:

| Criterion | Winner | Evidence quality |
|---|---|---|
| Copyright position, asset cost | **art history** | case law + EU directive (C-033) |
| Advertiser suitability | **art history** | official policy text |
| Architecture fit (provenance) | **art history** | our own codebase |
| RPM | tech | ⚠️ marketing blogs — untrustworthy |
| Views at typical execution | roughly a wash | 1.1 v/sub vs 2.4–2.9 |

Art history wins three well-sourced criteria. Tech wins one criterion sourced
from exactly the tier of evidence this project rejects.

**Recommendation stands: long-form public-domain art history.** But on
risk-and-feasibility grounds — free legal assets, no advertiser exposure, fits
the provenance architecture — *not* because the demand data supports it. It does
not.

## Revised expectations

Plan against **Narrative Art History**, not the exemplar:

```
realistic target    ~26,000 median views, ~1.1 views per subscriber
outlier case         111,040 median, 6.6 views/sub  — do not plan for this
```

At a nominal $8 RPM that is roughly **$200 per video**, not $900. The exemplar is
the ceiling, not the forecast.

## The runner-up, and when to switch

Tech explainers are the live alternative. Their case rests entirely on the RPM
gap ($15–25 vs $5–12), and those figures are marketing-blog sourced. **Measuring
real RPM in Studio after the first monetised videos is the cheapest way to settle
it** — and that is the same argument as C-028: our own data is the only data that
answers the questions that matter.

If real art-history RPM comes in at the bottom of its range while views track
Narrative Art History rather than the exemplar, switching to tech is the correct
move and the pipeline is niche-agnostic by design.
