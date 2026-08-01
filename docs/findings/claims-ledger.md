# Claims ledger

Every load-bearing claim this project has made, and what happened to it.

This file exists because the same failure kept recurring: a pattern read off a
sample too small to support it, written into a spec as a conclusion, then acted
on for days before something cheap refuted it. Three separate rules died that
way. Keeping the corpses visible is cheaper than rediscovering them.

## How to use this

**Before acting on a claim, look it up here.** A claim not in this file has not
been examined. A claim marked HYPOTHESIS has not been tested — it may be quoted
as a guess and must not be built on.

**When evidence lands, update the row rather than adding a new one.** A claim
that flips keeps its ID and gains a `Refuted by` line. The history is the point;
overwriting it destroys the only defence against repeating the error.

**Status meanings**

| Status | Meaning |
|---|---|
| `CONFIRMED` | Survived a test that could have refuted it, at a stated sample size |
| `HYPOTHESIS` | Consistent with observed data, never tested against held-out data |
| `REFUTED` | A test contradicted it |
| `WITHDRAWN` | Retracted for method error, not contradicting evidence — usually wrong identity or bad metric |
| `SUPERSEDED` | Replaced by a sharper claim; see the successor |
| `OPEN` | Asked, not yet answered |

**Sample size is part of the claim.** `n` is recorded on every row. A claim at
n=4 is a hypothesis no matter how clean it looks — see C-004, C-007, C-014.

---

## Metric and method

### C-001 · Mean views-per-video ranks channels usefully
**Status:** `REFUTED` · 2026-07-29 · n=146

Mean overstates median by more than 2x on **84 of 146** channels (58%); median
skew 2.3x, worst case 98.3x. On distributions this skewed the mean measures one
or two viral hits, not the channel's typical output.

*Refuted by:* `docs/evidence/2026-07-29/scan-rev2-channel-profiles.csv`.
*Consequence:* every ranking produced before 2026-07-29 used it, including the
"201,427 views/video" figure for Explainer Chris — see C-002.
*Replaced by:* C-003.

### C-002 · Explainer Chris averages 201,427 views/video
**Status:** `WITHDRAWN` · 2026-07-29 · n=24

True as arithmetic, worthless as a description. Median is **34,518**; the mean
sits 5.7x above it, carried by hits up to 1,736,716 against a floor of 1,177.
Nine hits, fifteen flops.

*Withdrawn because:* the statistic was broken, not the measurement. See C-001.

### C-003 · Rank channels on median views and hit-rate, never mean
**Status:** `CONFIRMED` · 2026-07-29 · n=146

Median plus hit-rate (share of videos above a fixed threshold) plus skew
(mean/median) separates repeatable operations from lottery ones. Mean cannot.

*Evidence:* `docs/evidence/2026-07-29/scan-rev2-channel-profiles.csv`.

### C-004 · Volume is the least efficient strategy
**Status:** `REFUTED` · 2026-07-26 · n=4 → n=5

Drawn from four channels where views-per-video fell as video count rose. Family
Life English broke it: 42 videos in 44 days — the highest cadence in the sample
— at 272,468 views/video, second-highest efficiency.

*Refuted by:* verifying a fifth channel.
*Lesson:* four data points produce a hypothesis, not a law. This is the first
of three identical failures — see C-007, C-014.

### C-007 · Its Just Cars! is a model worth building videos from
**Status:** `WITHDRAWN` · 2026-07-28 · n=4

Recommended on the strength of being *verifiable* — the channel's numbers checked
out — which is not the same as being *good*. At 43,184 views/video it was the
weakest operation in the sample it was drawn from, and the sample was four
channels.

*Withdrawn because:* "I can verify this channel exists and has these numbers" was
substituted for "this channel is worth copying". The tech-explainer
recommendation that replaced it was structurally the same mistake.
*Second instance of the small-sample error* — see C-004, C-014.

### C-026 · Breakout-trajectory scoring identifies growing channels
**Status:** `REFUTED` · 2026-07-26

Research engine v2 ranked channels by recent-vs-lifetime view velocity. The
metric is confounded by view front-loading: a video's views concentrate in the
days after publication, so `views / days_since_publish` inflates anything recent
regardless of trend. Demonstrated by MrBeast scoring a 3.0x "lift" during a
period of decline.

*Consequence:* both research engines were abandoned. The replacement is C-005,
which sidesteps the problem by never comparing across channels — with C-006 as
the guard against the same confound reappearing within one.

### C-005 · Within-channel view distribution is a valid demand signal
**Status:** `CONFIRMED` · 2026-07-29 · n=8 (Art History Explained)

Comparing a channel only to itself holds producer, style, subscriber count and
production budget constant, so view differences are attributable to the video.
This is what both failed research engines lacked: rev 1 was bounded by sample
size, rev 2 was confounded by view front-loading, and both compared *across*
channels where every variable moves at once.

*Caveat:* only valid between videos of **similar age**. See C-006.

### C-006 · Age matching is mandatory when comparing videos
**Status:** `CONFIRMED` · 2026-07-29

Views accumulate, so an old video outscores a young one for no editorial reason.
Air Crash Investigation was excluded from the cross-channel test precisely
because its "hits" were 639–881 days old and its "flops" 49–110 days — the exact
front-loading confound that killed research engine v2.

### C-016 · Rev 1 of the channel scan was biased by its own prefilter
**Status:** `CONFIRMED` · 2026-07-29 · n=76 vs n=146

Rev 1 selected the top 12 channels per niche by `total_views / video_count` —
the mean, the statistic the same run then proved broken. Channels with a steady
median but no viral hit were discarded before measurement.

*Measured effect:* rev 1 channels were 26% more skewed (2.9x vs 2.3x median) and
its median-of-medians was inflated 49% (3,136 vs 2,104). Direction as predicted;
the headline conclusion survived the redo.

---

## Channel identity

### C-008 · Channel handles must never be guessed from display names
**Status:** `CONFIRMED` · 2026-07-30 · 4 failures out of 4 attempts

Every attempt to guess a handle hit the wrong channel:

| Guessed | Reality |
|---|---|
| `@BikeGenMountain` | irreconcilable numbers; a revenue claim was withdrawn on bad data |
| `@Brainosophy` | a 1,674-view channel; the real one is `@brainosophic` |
| `@PaintProfessor` | 154 subs, 1,579 lifetime views — not the channel cited |
| `@ultrasfctv` | invented by completing a tooltip-covered `@ultrasfct…`; resolved to an unrelated 217-sub channel while the screenshot showed 1.3M views |

`channels.list` with `forHandle` costs 1 unit and returns the exact channel;
`search.list` costs 100 and returns a guess.

*Consequence:* the `paintprof_*.jpg` reference thumbnails in `data/samples/refs/`
are of unverified provenance and must not be cited.

*The fourth failure happened while building the skill designed to prevent it* -
a truncated handle in a screenshot is as dangerous as a display-name search. The
`leads-verify` stage caught it because the profile (median 342) contradicted the
screenshot (1.3M views), which is now the documented check: a contradiction means
a bad handle, not a surprising channel.

### C-009 · Paint Professor is a successful channel worth emulating
**Status:** `WITHDRAWN` · 2026-07-29 · n=6

`@PaintProfessor` has 154 subscribers, 6 videos and a **median of 239 views**.
Every title follows "Every X Explained in N Minutes". Its videos are 856+ days
old, so it *predates* the channels it appeared to be copying.

*Withdrawn because:* wrong channel identity (C-008). The 6.1M "Reality Glitch"
video attributed to it belongs to some other channel, still unidentified.

---

## Format and production

### C-010 · The "Every X Explained" format is itself the driver of success
**Status:** `REFUTED` · 2026-07-29 · n=2, direct comparison

Paint Professor runs the identical title template and gets a 239 median. Bluntly
Explained runs it and gets 129,635. **1,300x apart on the same format.** The
format is free to copy and worth nothing alone.

### C-011 · Asset polish drives views
**Status:** `REFUTED` · 2026-07-29 · n=2 within one channel

Bluntly Explained's 532,684-view video uses crude black doodles on white and
ships a visible typo ("Nineth Dimension"). The same channel's 9,343-view video
uses polished full-colour illustrated space art. **The better-looking video lost
by 57x.**

*Consequence:* the thumbnail generator in `src/contentforge/visuals/thumbnail.py`
was built to reproduce a labelled-grid template that the *failing* copycat opens
with. It optimises the wrong variable.

### C-012 · Cut rate / pacing differentiates winners
**Status:** `REFUTED` · 2026-07-29

The 532K video cuts every 4.3s; the 409-view copycat cuts *faster*, every 2.6s.

### C-013 · Winning explainers use whiteboard-animation software
**Status:** `REFUTED` · 2026-07-29

Frames show complete line-art images held statically, one per narration beat —
no progressive draw-on anywhere. No whiteboard tool is involved, and none of the
open-source ones (scriptimate, SVGVideoMaker) is worth adopting.

### C-017 · Authored-per-beat visuals beat assembled stock
**Status:** `HYPOTHESIS` · 2026-07-29 · n=2

The 532K video's drawings each serve one narrated idea. The 409-view copycat
pastes in found reference charts, including a Kung Fu stance diagram still
labelled in French. Consistent with YouTube's "inauthentic content" policy line,
and the copycat is additionally using material it does not own.

*Untested:* no controlled comparison isolates this from everything else that
differs between those two channels.

---

## Script structure

### C-014 · A concrete reversal in the first 60s separates hits from flops
**Status:** `REFUTED as general rule` · 2026-07-29 · confirmed n=8 in one channel, failed 1 of 4 across channels

Within **Art History Explained** this holds cleanly at n=8 with production held
constant: all six hits (94K–216K) open on a specific sourced obstacle plus a
turn; both flops (3.7K, 5.2K) have none. Caravaggio opens with praise —
"powerful images of passion, pain and devotion come to mind" — and lost 20–40x
to its own siblings.

Across channels it does not generalise:

| Channel | Verdict |
|---|---|
| Joe Bart Philosophy | holds — hits carry dates, altitudes, names; flops open "it's midnight and I want to rant" |
| How Money Works Uncut | holds — hits carry absurd specifics; flops open on abstractions |
| Pilot Debrief | partial — *all four* have turns; hits differ by naming a single identifiable person |
| Imagine the Physics | **fails** — hits and flops run the identical setup-then-subvert structure |

Imagine the Physics was the tightest age match in the set (hits 149–203d, flops
147–182d), so the refutation comes from the best-controlled comparison available.

*Scope it survives at:* "this is how Art History Explained works."
*Third instance of the same error* — see C-004, C-007.

### C-015 · Hits open on something the viewer already possesses
**Status:** `REFUTED` · 2026-07-29 · preregistered blind test, n=31 usable across 8 held-out channels

Tested under [the preregistered protocol](2026-07-29-C015-preregistration.md):
channels selected by fixed rule, hits and flops chosen by view rank before any
caption was read, classifications made blind and committed before unblinding,
ambiguous cases resolved *against* the hypothesis.

```
A = share of HITS  labelled ATTACHES = 10/16 = 0.62
B = share of FLOPS labelled ATTACHES = 11/15 = 0.73
A - B = -0.11          (preregistered refutation threshold: <= +0.15)
```

Flops attached marginally *more* than hits. Caption attrition was balanced —
8 hits and 9 flops dropped for missing captions — so the loss is not the cause.

*Superseded by:* C-027, which explains the result.

### C-027 · Opening style is a channel-level constant, not a video-level variable
**Status:** `CONFIRMED` · 2026-07-29 · n=31 across 8 channels

In the blind test, **every channel scored a difference of exactly +0.00** — hits
and flops within a channel received identical classifications, without exception.

```
Tech Explained        hits 0.00  flops 0.00    always definitional
Geo Study             hits 0.00  flops 0.00    always exam-prep announcements
Plane Curious         hits 1.00  flops 1.00    always a dated historical scene
Rumi English Stories  hits 1.00  flops 1.00    always dramatized dialogue
WILD NATURE           hits 1.00  flops 1.00    always a named animal confrontation
143 Explained         hits 1.00  flops 1.00
```

The opening belongs to the channel's format, so it is constant where it matters
and cannot explain within-channel variance.

**This also explains C-014's false positive.** Art History Explained is unusual
in containing two videos that break its *own* house format — Caravaggio reads as
a different or licensed script, Bruegel predates the format settling. The rule
was detecting format deviation, not a principle about openings. Channels that
apply their format consistently show no such signal.

*Lesson:* a pattern that separates hits from flops in one channel may be
measuring that channel's inconsistency rather than anything general.

### C-028 · Public data cannot explain within-channel variance
**Status:** `CONFIRMED` · 2026-07-29 · by exhaustion, 8 refuted hypotheses

Everything externally observable has now been tested and refuted: mean-based
ranking (C-001), format (C-010), asset polish (C-011), cut rate (C-012),
production tooling (C-013), narration start time (C-018), opener formula (C-019),
and opening style (C-015/C-027).

The remaining candidate is topic selection, and the variable that would decide it
— click-through rate against impressions — is visible **only to the channel
owner**. It is not in the Data API for third parties at any quota cost.

*Consequence:* further observational analysis has negative expected value. It
generates hypotheses faster than it can test them, which is how eight died. The
next real evidence must come from our own published videos, where retention and
CTR are visible in Studio. This is what Plan 2 already proposed; what has changed
is knowing which variables not to spend effort on.

A belief they hold (gravity, time dilation), a person they can picture (Jenny,
Sarah, McCandless 317 miles up), a grievance they've lived (a $15/hr job ad
demanding 10 years on a 20-month-old program). Flops open on an abstraction the
viewer must already care about: specialised labour, business ethics, antimatter,
corporate social responsibility, electron-photon scattering.

**This rule was generated from the same 16 videos that refuted C-014.** Fitting
a new rule to the data that killed the old one is not evidence. It requires a
held-out set: channels not yet examined, with hits and flops chosen by view rank
*before* any caption is read.

*Do not build on this until it has a fresh test.*

### C-018 · Narration start time affects retention
**Status:** `REFUTED` · 2026-07-29

Klee starts narrating at 00:38 and got 136,680; Degas and Monet start at 00:03.
Within Art History Explained the delay does not track views.

### C-019 · The "This is the story of an artist who…" opener is required
**Status:** `REFUTED` · 2026-07-29

Monet skips it entirely — opens "Claude Monet is today thought of as the
archetypal Impressionist artist", the same assumed-familiarity move that
Caravaggio flopped with — and still got 110,845. What Monet has and Caravaggio
lacks is what follows: "aged just 27, he stood on the edge of the Seine and
considered ending his life."

---

## Niche selection

### C-020 · Only ~5% of channels are repeatable rather than lottery-shaped
**Status:** `CONFIRMED` · 2026-07-29 · n=146

7 of 146 channels meet skew ≤3, hit-rate ≥40%, n ≥8. The other 95% depend on
occasional viral hits.

### C-021 · Aviation is the strongest niche measured
**Status:** `HYPOTHESIS` · 2026-07-29 · n=14 channels

14 channels, 2 repeatable (14%) — Pilot Debrief at 100% hit-rate and Air Crash
Investigation at 84%. Plausible mechanism: incident analysis has narrative
structure built into the subject matter, so the niche supplies it for free.

*Untested:* mechanism is inferred, and 14 channels from one search query is thin.

### C-022 · Psychology, math, space and language are graveyards
**Status:** `HYPOTHESIS` · 2026-07-29 · n=10, 5, 4, 21 channels

Median-of-medians 475, 367, 420 and 5,150 respectively; zero repeatable channels
in any of them. Language had the most channels of any niche (21) and produced
none. Psychology was the most crowded of the "obvious" niches and the worst
performing, at 8.1x median skew.

*Caveat:* one search query per niche. A niche is not proven empty by one query.

### C-023 · Art History Explained is the only reachable repeatable profile found
**Status:** `WITHDRAWN` · 2026-07-30 · n=8 videos

> **Withdrawn:** the channel is Christopher P Jones, an art-history writer
> narrating his own work, with a 6,000-subscriber Substack behind him (C-048).
> Reachable in subscriber count, repeatable in output — but not by an AI-assisted
> pipeline, and not from a standing start.

16,700 subs producing a 112,326 median — **6.7 views per subscriber**, against
4.2 for the next best and under 2.0 for most — at skew 1.0. Small, recent,
consistent. The other six repeatable channels sit at 69K–1.03M subs, where a new
channel cannot infer anything about its own prospects.

*Caveat:* 8 videos is the thinnest sample in the repeatable table.

---

## Open questions

### C-024 · What actually changed to make this format work recently?
**Status:** `OPEN`

Paint Professor ran the identical titles 856 days ago for a 239 median. All three
recent winners launched within ~5 months (100, 110, 142 days). Either something
changed, or the three are riding a wave that will pass. Execution differences
confound this and it is not resolved.

### C-025 · Does the winning format survive the "inauthentic content" policy?
**Status:** `OPEN`

The policy (renamed 2025-07-15) bans mass-produced templates and verbatim
readings. A rigid per-video template is exactly what these channels run. Whether
the authored-visuals distinction (C-017) is what keeps them compliant is
untested and consequential — it gates monetisation.

---

## Legal and policy risk

### C-029 · Copying a format or template risks a copyright strike
**Status:** `REFUTED` · 2026-07-30

Copyright protects expression, not ideas, formats, systems or titles. A title
pattern ("Every X Explained in N Minutes"), a video structure, a chapter scheme
and a niche are all unprotectable. Nothing in copying a *format* creates strike
exposure.

A copyright strike arises only from a **valid legal removal request** over
specific copied expression — footage, images, music, or text. Three strikes
terminate the channel; each expires after 90 days with Copyright School.

*Source:* [Understanding copyright strikes](https://support.google.com/youtube/answer/2814000).

### C-030 · Content ID claims are copyright strikes
**Status:** `REFUTED` · 2026-07-30

Distinct mechanisms. "Content ID claims are different from copyright strikes. If
you get a Content ID claim on your video, it typically doesn't result in a
copyright strike." A claim redirects or blocks monetisation; it is not a channel
penalty. **Disputing one without valid grounds** can escalate into a removal
request, which does strike.

*Consequence:* the practical music/footage risk is silent demonetisation via
Content ID, not termination.

*Source:* [Understanding copyright strikes](https://support.google.com/youtube/answer/2814000).

### C-031 · Reusing found assets is the actual strike exposure
**Status:** `CONFIRMED` · 2026-07-30

The failing copycat examined on 2026-07-29 pasted in third-party reference
charts, including a Kung Fu stance diagram still labelled in French. That is
copying of protected expression and is actionable, regardless of format.

*Build rule:* no found images, no scraped diagrams, no third-party footage, no
unlicensed music. Every visual asset must be public domain, openly licensed with
attribution recorded, or generated for the video.

### C-032 · The binding risk is monetisation eligibility, not strikes
**Status:** `CONFIRMED` · 2026-07-30

YouTube's inauthentic content policy — renamed from "repetitious content" on
**15 July 2025** — makes ineligible for monetisation:

- "Similar or repetitive content with low educational value"
- "AI-generated content made with generic or unoriginal templates"
- content "made with a template" where each video "doesn't deliver creative,
  educational, or other value"
- "Content downloaded or copied from another online source without any
  substantive modifications"

Separately the reused content policy requires that borrowed material be changed
"significantly", with "significant original commentary, substantive
modifications, or educational or entertainment value".

**This is aimed squarely at what this project builds.** It does not strike the
channel; it withholds the money, which for the stated goal is equally fatal, and
it is judged by human review at YPP application.

*Consequence:* the per-video differentiation mechanisms in the spec (§4) are not
optional polish — they are the monetisation gate. Note the tension with the
2026-07-29 finding that winning channels run rigid templates (C-010): they pass
because each video carries distinct authored substance, not because the template
is varied.

*Source:* [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392).

### C-033 · Public-domain artworks are a low-copyright-risk visual source
**Status:** `CONFIRMED` · 2026-07-30 · with jurisdictional caveats

Faithful photographic reproductions of public-domain 2D artworks carry no new
copyright. *Bridgeman Art Library v. Corel*, 36 F. Supp. 2d 191 (S.D.N.Y. 1999)
held such transparencies lack originality: a change of medium from painting to
photograph is not itself original. In the EU, Article 14 of the 2019 Copyright in
the Digital Single Market Directive was written specifically to stop museums
asserting rights over reproductions of public-domain visual art, and applies to
any reproduction, not only photographs.

**Caveats that matter:** Bridgeman is a district-court decision — persuasive, not
binding nationally. Museums may still impose *contractual* terms on downloads
even where copyright does not apply. And the artwork itself must actually be
public domain: Cézanne (d. 1906), Degas (d. 1917), Klimt (d. 1918), Monet
(d. 1926), Klee (d. 1940) and Kandinsky (d. 1944) all clear life+70, but a 20th
century artist such as Picasso (d. 1973) does not until 2043.

*Consequence:* an art-history format has a **better** copyright position than an
aviation one, which leans on news footage and broadcast material. US federal
works (NTSB reports and imagery) are public domain, but network news video is
not.

*Sources:* [Bridgeman v. Corel](https://law.justia.com/cases/federal/district-courts/FSupp2/36/191/2413183/),
[Article 14 and the public domain](https://pro.europeana.eu/post/article-14-and-the-public-domain-the-state-of-play-across-europe).

---

## Decisions

### C-034 · Long-form public-domain art history is the right niche to enter
**Status:** `HYPOTHESIS` · 2026-07-30 · now rests on risk and feasibility alone

> **Revised 2026-07-30:** C-023, one of the two claims this rested on, is
> withdrawn — the exemplar is a human art writer, not a faceless operation
> (C-048). The demand argument is gone. What survives is the copyright position
> (C-033), the absence of aviation's advertiser-suitability exposure, and the fit
> with the provenance architecture. The 2026-07-30 revision below had already
> concluded those were the real grounds.

Full reasoning: [2026-07-30-niche-recommendation.md](2026-07-30-niche-recommendation.md).

Chosen over aviation — the strongest niche by repeatability (C-021) — on four
grounds that bind harder than raw niche strength:

1. **Reachability.** Art History Explained produces a 112,326 median from 16,700
   subscribers (6.7 views/sub, C-023). Both aviation exemplars sit at 237K and
   1.03M, where nothing can be inferred about a new channel — the error C-007 was
   withdrawn for.
2. **Copyright.** Public-domain artworks carry no reproduction copyright (C-033)
   and open-access museum APIs supply them at scale. Aviation's watchable footage
   is news and CCTV (C-030).
3. **Advertiser suitability.** Accident content with "visible injury or extreme
   impact moments" earns limited ads; content that "profits from or exploits a
   sensitive event" earns none. A crash-analysis channel carries that risk on
   every video.
4. **Architecture fit.** Biographical facts resolve to citable sources, which is
   what `provenance.py` and `script/validate.py` already enforce.

**Known weaknesses, not hidden:** history RPM is mid-tier at a nominal $5–12
against tech's $15–25 — and those figures come from marketing blogs of the tier
rejected as unusable on 2026-07-29, so they are directional at best. n=8 is the
thinnest sample in the repeatable table. And the deciding capability — turning a
biography into a narrative with stakes — is untested and unresolvable
observationally (C-028).

*Falsifiers, both cheap:* Art History Explained's next 4–6 videos regressing to
its 3.7K–5.2K floor (2 quota units to check); or a repeatable channel under ~30K
subscribers surfacing in finance, business or tech, none of which the scan
covered properly — re-filterable from the 1,189 stored candidates at zero quota.

*Source for advertiser suitability:* [Advertiser-friendly content guidelines](https://support.google.com/youtube/answer/6162278).

### C-035 · The art history *niche* confers the Art History Explained profile
**Status:** `REFUTED` · 2026-07-30 · n=12 art/art-history channels

Searching specifically for art-biography and art-history channels found no peer
that replicates it:

```
channel                      subs      n     median  skew  hit%  v/sub
Art History Explained      16,700      9    111,040   0.9   56%   6.6
Narrative Art History      23,300     16     26,106   1.8    6%   1.1
FINE ART EXPLAINED            994     18      1,312   4.9    0%   1.3
Chronicles & Chills        11,900     16        617   1.7    0%   0.1
```

Narrative Art History is *larger* and earns 6x less per subscriber. Niche
med-of-medians: art_history 338, art_bio 617.

**Art History Explained is an outlier within its own niche, not an example of a
strong niche.** Entering art history does not buy its numbers. Whatever produces
them is channel-specific and not visible from outside (C-028).

*Consequence:* C-034's expected outcome must be anchored to Narrative Art History
(~26,000 median, 1.1 views/sub), not to the exemplar.

### C-036 · A reachable repeatable channel exists in a higher-RPM niche
**Status:** `REFUTED` · 2026-07-30 · n=31 across 6 niches, plus 5 re-filtered

Proper searches of finance, investing, business, software, tech and economics —
niches the main scan covered badly — produced **zero repeatable channels** of 31
profiled. Re-filtering the 1,189 stored candidates (zero quota) and deep-scanning
the 6 that qualified added none.

Best reachable performers found:

```
Tech Explained        13,200 subs   median 38,826   skew 1.6   hit 21%   v/sub 2.9
Tech Explainer Guy    10,200 subs   median 24,684   skew 2.6   hit 22%   v/sub 2.4
```

Both miss the 40% hit-rate bar. Niche med-of-medians: investing 10,555, finance
1,678, software 940, tech 723, economics 452, business 159.

*Consequence:* no better alternative was found, so C-034 survives this falsifier.
But note the runner-up case: tech at ~2.9 views/sub with a nominal $15–25 RPM
could out-earn art history at ~1.1 views/sub and $5–12 — **if** those RPM figures
were trustworthy, which they are not (marketing-blog sourced, see C-034).

### C-037 · The Art History Explained profile is a short run that will regress
**Status:** `REFUTED` · 2026-07-30 · forward test, n=8 → n=9

The channel published a 9th video between the two scans. The profile held:

```
             n    median   skew   hit-rate
before       8   112,326    1.0        62%
after        9   111,040    0.9        56%
```

The new video landed below 100,000 (hit-rate fell 62% → 56%) but the median moved
less than 1.2% and skew stayed at ~1.0. This is a genuine forward test — the
prediction was made before the video existed — and it did not regress.

### C-038 · Threads research needs an opencli adapter or the official API
**Status:** `REFUTED` · 2026-07-30

Neither is needed for **reading**. Public Threads profiles *and* keyword search
are both readable through Jina Reader with no login, no browser extension, and no
adapter:

```bash
curl -s "https://r.jina.ai/https://www.threads.net/@HANDLE"
curl -s "https://r.jina.ai/https://www.threads.net/search?q=QUERY&serp_type=default"
```

Returns post text, author handle, permalink, date and engagement counts. Jina
Reader is agent-reach's `web` backend, which `doctor` reports as `ok`.

*Context:* opencli has no Threads adapter among ~180, and its Instagram/Facebook
adapters are currently non-functional anyway — `doctor` reports every
login-backed platform as `warn`, cause: "OpenCLI installed, but no connected
browser extension detected". One extension install would fix all of them at once.

*Still requires the official Threads API:* **publishing**. Reading is not the
blocker; posting is (`threads_basic`, plus `threads_keyword_search` for
sanctioned search). The Meta app remains on the critical path for that reason
alone.

*Caveat on what the reading returns:* a search for "faceless youtube" surfaces
exactly the evidence tier this project rejects — e.g. a post claiming "$3,084 in
the last 28 days, 308K subscribers, 9 videos" with **no channel named**, so it
cannot be verified with the 1-unit handle lookup that exists for precisely this
purpose. Cheap access to unverifiable claims is not the same as evidence
(C-028).

### C-039 · Threads earnings claims are verifiable leads worth researching
**Status:** `CONFIRMED` · 2026-07-30 · corrected same day; 2 of 2 attempted checks verified

> **This row was first recorded as REFUTED and that was wrong.** The measurement
> below counted only post *text*. These posts attach screenshots - YouTube Studio
> panels, channel pages - and the channel is routinely named there and nowhere
> else. Measuring the captions and concluding "unverifiable" measured my own
> parser, not the platform.

Reading the attached images instead:

```
@someunfilteredguy   claimed "308K subscribers, 9 videos"
                     API: 336,000 subs, 10 videos, 651d
                     median 338,062  mean 1,083,783  skew 3.2      VERIFIED
@eonatlas            named in a "CHANNEL SPOTTED" post, niche 4K travel docs
                     API: 2,730 subs, 14 videos, 58d
                     median 15,194  mean 40,363  skew 2.7          VERIFIED
```

Both matched, allowing for growth since posting. Cost: 8 quota units total.

A whole genre of post exists for this - "CHANNEL SPOTTED", naming a small channel
with its niche and format - inside a 190K-member Threads community. That is a
lead source, and the 1-unit handle lookup turns a lead into a fact.

*Note the same mean/median trap in the wild:* the `@eonatlas` post advertised
"24.7K+ avg views". The mean is now 40,363 and the median 15,194 (C-001).

*Original text-only measurement, retained:* of 20 posts matching "faceless
youtube", 9 made a specific monetary claim and none named a channel **in the
caption**.

Searching "faceless youtube" returned 20 posts, 9 of them making a specific
monetary claim. **Zero named a channel.**

```
"$3,084 in the last 28 days, 308K subscribers, 9 videos"     no channel
"$116,900 in 12 months from ONE faceless YouTube channel"    no channel
"This AI Sleep channel made me $61,323 in my first year"     no channel
"22 faceless channels, one made $30,626 last month"          no channel
"My faceless YouTube channels make me $109K+/month"          no channel
"I asked Claude to build me a channel... over $6,000"        no channel
────────────────────────────────────────────────────────────────────────
monetary claims 9/20        verifiable against the API 0/9
```

The omission is structural, not incidental: naming the channel is the single
detail that would let a 1-unit `channels.list` call check the claim, and it is
the one detail every post leaves out.

*Consequence:* Threads is not a research source for niche or revenue data. Its
value, if any, is as a **lead generator** — a post naming a channel can be
verified for 1 unit — and 0 of 9 qualified.

*Separately, the `#youtubecreators` tag is a beginner support community*
("my first $10", "first 10 subscribers", "drop your channels below"), not a
strategy source. It is a plausible market for the client-services line mentioned
in the spec's revenue model, and nothing else.

### C-040 · Faceless-channel RPM is around $4, not the $5–25 in the niche table
**Status:** `HYPOTHESIS` · 2026-07-30 · n=2 self-reported screenshots

Two independent YouTube Studio screenshots found on Threads give a directly
computable RPM:

```
@wannercashcow   $116,900.74 over 29,812,205 views (365d)   = $3.92 per 1,000
@onlinemoneyai1  $3,084 over 784,928 views (28d)            = $3.93 per 1,000
```

Two unrelated posters landing within a cent of each other is notable. Both sit
**below** every US figure in `data/niches.csv` — history $5–12, tech $15–25 —
which are themselves marketing-blog sourced and already flagged as untrustworthy
(C-034).

*Why this is a hypothesis and not a finding:* screenshots can be fabricated,
neither names its niche or audience geography, and revenue mix (Shorts vs
long-form) is invisible. But it is the first RPM evidence in this project that
derives from a number someone actually saw in Studio rather than a blog estimate.

*Consequence if true:* the ~$200/video expectation set in the niche
recommendation is roughly halved, to ~$100 at Narrative Art History's ~26,000
median. Real RPM remains knowable only from our own Studio data.

### C-041 · The winning visual style keeps showing up as crude line art
**Status:** `HYPOTHESIS` · 2026-07-30 · n=3 channels, converging from separate searches

`@someunfilteredguy` — 336,000 subscribers, median 338,062, **10 videos in 651
days** — runs white stick figures on black with bold captions carrying one
coloured word ("kill **excuses**", "non-**awkward**", "learn **3x** faster").

That is the third independent arrival at the same aesthetic: Bluntly Explained's
crude doodles beating its own polished space art by 57x (C-011), Brainosophy's
line art, and now this. All three are cheap to produce and none is polished.

*Still a hypothesis:* three channels found by different routes is suggestive,
not a controlled comparison, and C-011 is the only one where production was held
constant. Do not treat as established — that is the C-004/C-014 error.

### C-042 · The prevailing "guru" method is to ask an LLM for niche RPMs
**Status:** `CONFIRMED` · 2026-07-30 · n=1 fully expanded walkthrough

Expanding the "$6,000 in 30 days with Claude" thread recovers its steps, which
are posted as reply images. Step one reads: *"First, ask Claude to give you
high-paying YouTube niches. Align that prompt to how much you want to earn (e.g.
$10k/mo)."* The attached screenshot shows the model returning:

```
01  Personal finance / wealth building   RPM $12-30   ~80k-150k views/mo
02  Real estate investing                RPM $15-35   ~60k-100k views/mo
```

Those RPM figures are **model output, not measurement** — the same class of
unsourced estimate as the marketing-blog table in `data/niches.csv` (C-034), and
they sit 3-8x above the $3.92 computed from actual Studio screenshots (C-040).

*Why this matters:* the widely-shared method is exactly the assumption-driven
research this project spent a week refuting. It produces confident numbers with
no provenance, and anyone following it plans against an RPM that the only
measured evidence available contradicts by a factor of 3 or more.

*It also explains the ecosystem:* these posts circulate LLM estimates as fact,
other posts cite those posts, and nothing in the chain is ever checked against
the API — which costs 1 unit.

### C-043 · Reddit is a better research source than Threads
**Status:** `CONFIRMED` · 2026-07-30 · n=15 posts, first run

Three structural advantages, all verified on a live run:

- **`selftext` is the whole post.** No login wall, no teaser-plus-reply-images
  split. Threads needed a JS-rendered second fetch per post to recover the
  content (C-038 route); Reddit returns it in one call.
- **`score` and comment count** give a quality signal Threads does not expose.
  Expansion ranking now uses it where present.
- **Subreddits are topic-scoped**, so r/aitubers beats a keyword search for
  precision.

*The two are complementary, not redundant.* A 15-post r/aitubers run contained
**zero dollar figures**; Threads' "faceless youtube" run had 13 monetary claims
in 20 posts. Reddit carries advice and workflows, Threads carries earnings
flexes with Studio screenshots. Both are worth gathering.

*Independent corroboration worth noting:* a 1000+ video creator's r/aitubers
writeup arrives at four of this ledger's conclusions without knowing them —
look for sub-1000-sub channels with outsized views (our `reachable` test), copy
the title format but not the content (C-010), every niche has its own visual
language (C-027), and "don't try to build a Pixar movie… simple slideshows work
better than flashy effects" (C-011).

*Requires:* the OpenCLI Chrome extension and a running daemon. Note that
`agent-reach doctor` reports these platforms as `warn` even when the bridge is
connected, because it deliberately never runs a platform command to verify a
login. `warn` is not a fault.

### C-044 · Varying script structure per video is required by policy
**Status:** `REFUTED` · 2026-07-30 · n=9 (Art History Explained) + every channel measured

The spec's §4 founding principle read: *"No two consecutive videos share a shape.
There is no script template in this codebase."* It was written to satisfy the
inauthentic-content policy by structural variation.

Every channel measured contradicts it. **All of them run rigid templates.** Art
History Explained uses the identical "The Life and Art of X" structure nine times
for a 111,040 median; Bluntly Explained, Explainer Chris and Pilot Debrief are
equally formulaic. Opening style is a channel-level constant, not a per-video
variable (C-027) — so deliberately varying structure would be imitating the
channels that fail, not the ones that work.

*What actually satisfies the policy* is per-video **authored substance**: research
specific to that subject rather than a name substituted into a frame (C-032). The
template is the format; the substance is the differentiator. YouTube's wording
targets content where "each video doesn't deliver creative, educational, or other
value" — not repeated structure.

*Consequence:* `script/generate.py`'s rotating "narrative shapes" mechanism
optimises against the evidence. Plan 3 holds structure fixed and varies content.

*Note the asymmetry this project keeps rediscovering:* a rule adopted to be safe
can be as wrong as one adopted to be clever, and costs just as much.

### C-045 · One museum's open-access collection is enough for the video pipeline
**Status:** `REFUTED` · 2026-07-30 · n=9 artists surveyed at the Met

Open-access coverage varies enormously by artist and is **not** predictable from
fame or death date:

```
artist        usable PD artworks in the first 12 search results
Degas          3     Van Gogh   3
Cezanne        2     Gauguin    2     Manet   2     Seurat  1
Renoir         0     Monet      0     Klimt   0
```

Monet is the instructive case. He died in **1926** — comfortably public domain —
yet every Met record for him is `isPublicDomain: false` with **no image at all**.
The museum has not released those digitisations. Copyright expiry does not imply
an available file.

*Caveat on these numbers:* the survey scans only the first 12 search results per
artist, so they measure *readily reachable* coverage, not total holdings. Monet
was separately checked across 14 results with the same outcome; the others are a
signal, not a census.

*Consequences for Plan 3:*
1. **Survey before choosing a subject.** `survey_artists()` exists for this. A
   video planned around an artist whose images cannot be obtained is wasted work.
2. **The Met alone will not sustain a 17–22 minute video**, which needs 40–60
   artworks. **Resolved 2026-07-30:** Wikimedia Commons was added as a second
   source and fills exactly the Met's gaps — Monet 22 works, Renoir 28, Klimt 15,
   all of which the Met had none of. Picasso still correctly returns 0. Together
   the two sources cover every candidate artist tried.
3. Two candidate first subjects that do check out: **Degas** and **Van Gogh**.

*Also recorded:* the Art Institute of Chicago was tried first and dropped — its
metadata is good, but its IIIF image host returns a Cloudflare HTML challenge
instead of a JPEG for every user agent tried. And the Met's documented
`artistOrCulture=true` search flag returns **0 results for every artist tested**
while the same query without it returns ~170, so artist filtering is done in our
code instead.

### C-046 · On Commons, the `Artist` field names the painter
**Status:** `REFUTED` · 2026-07-30

`extmetadata.Artist` is the **photographer or uploader**. For
`File:Claude Monet.- Le Pont d'Argenteuil` it names the Commons user who
photographed the canvas. Using it for authorship would misattribute every work
in the pipeline.

Authorship is taken from the file's **categories** instead, and the category must
say *paintings **by*** the artist. Merely containing the name is not enough: a
search for Monet returns Édouard Manet's portrait *of* Monet, which sits in a
category naming Monet and is by someone else.

*Two further traps, both from live results:*
- Commons hosts **CC-BY alongside public domain** — `File:Claude Monet Painting
  in his Studio` is `cc-by-4.0`. Only `pd`/`cc0` are accepted; attribution-required
  is a different obligation, not a weaker one.
- `ObjectName` carries spliced Wikidata markup —
  `At Petit-Gennevillierslabel QS:Lfr,"Au Petit-Gennevilliers"` — which would
  otherwise render on screen as a chapter title.

### C-047 · Narration pace can be matched to the exemplar by measurement
**Status:** `CONFIRMED` · 2026-07-30 · n=2,592 words

Almost nothing about a voice is measurable without ears. Pace is the exception,
and it was measurably wrong.

```
Art History Explained    142 wpm   (2,592 words across its Cezanne video)
edge-tts, default rate   162 wpm   14% faster
edge-tts, rate="-12%"    143 wpm
```

Speech rate is computed from caption timings, which are free and need no audio.
`DEFAULT_RATE = "-12%"` is now the pipeline default and `Narration.wpm` exposes
the figure so a drift is visible rather than inferred.

*What remains unmeasurable here:* timbre, accent, warmth, whether a voice holds
attention for twenty minutes. Those need a human listener, and the samples are
in `data/samples/` beside a 45-second reference clip for comparison.

*Not to be confused with a finding about retention.* Matching the exemplar's pace
is a reasonable default, not evidence that 142 wpm performs better than 162. That
would need our own data (C-028).

### C-048 · Art History Explained is a faceless AI-assisted channel
**Status:** `REFUTED` · 2026-07-30

It is **Christopher P Jones**, a writer on art history, narrating his own work.
The video descriptions carry "you can leave me a tip at ko-fi.com/christopherpjones"
and link a personal Substack with 6,000+ subscribers.

Found because the narration sounded human to a listener and I went looking for
why. I had watched four of its videos, read every transcript and profiled the
channel across three scans without ever noticing it was a named person with a
tip jar in the description.

**What this invalidates.** The channel was selected as our exemplar (C-023) and
carried the niche recommendation (C-034) on the strength of being the only
*reachable repeatable* profile found. It is reachable in subscriber count and it
is repeatable — but not by us:

- Its advantage is plausibly domain expertise and writing quality, and an
  audience already assembled elsewhere. A 6,000-subscriber newsletter is a
  launch platform a new channel does not have.
- **C-035 is now explained rather than merely observed.** "The niche does not
  confer the profile" was recorded as a puzzle; the answer is that the profile
  belongs to Christopher P Jones, not to art history.
- Its skew of 1.0 across nine videos may reflect a consistent author rather than
  a reproducible format.

**What survives.** The niche recommendation's other grounds are untouched: the
public-domain copyright position (C-033), absence of the advertiser-suitability
exposure that aviation carries, and the fit with the provenance architecture.
Those were always the stronger arguments — see the 2026-07-30 revision, which
already concluded the recommendation rested on risk and feasibility rather than
on demand evidence.

**Consequence for expectations.** Anchoring on Narrative Art History (~26,000
median) rather than the exemplar was already the plan. That now looks
conservative in the right direction, and even it is a channel whose production
model we have not verified.

*The general lesson, and this project keeps paying for it:* a channel's
measurable properties say nothing about who is behind it, and "faceless" was
assumed from the format rather than checked. One line in a video description
would have settled it at any point in the past week.

### C-049 · A free TTS voice can match the exemplar's narration
**Status:** `REFUTED` · 2026-07-30 · six voices rejected by a listener

Six edge-tts voices were generated reading the exemplar's actual Cezanne
opening — including the newer Multilingual tier (Andrew, Brian) that
`en-GB-RyanNeural` predates. A human listener judged all six as obviously
synthetic against a reference clip that sounded natural.

They were right, and for a structural reason: **the reference is not TTS at
all** (C-048). No text-to-speech setting matches a person reading their own
prose.

*Options, none free-and-equal:*
1. Accept an audibly synthetic narrator and the gap it carries.
2. Kokoro-82M — local, free, no key, materially better than edge-tts. Still TTS.
3. Narrate in the operator's own voice. Free, unbounded quality, but ~20 minutes
   of recording per video against the stated 1–2 hrs/week budget.
4. ElevenLabs. Paid, and the constraint is zero spend until it earns.

*Recorded as a decision the operator has to make*, not one the pipeline can
resolve. `synthesise()` takes an injected runner precisely so the backend is a
one-line swap.

### C-050 · Hit-rate at a fixed view threshold measures repeatability
**Status:** `REFUTED` · 2026-07-30 · n=176 channels

It measures **size**. "40% of videos above 100,000 views" rejected **95 of 176**
channels — more than every other criterion combined — and everything it rejected
was small. A channel at 1,440 subscribers cannot clear it however consistent it
is, so the gate was asking "is this already big" while claiming to ask "is this
repeatable".

Every candidate a new channel could actually learn from was filtered out before
anyone saw it. The niche recommendation was then built on the two survivors, one
of which turned out to be a human (C-048).

**Replaced by views per subscriber**, which measures whether the algorithm serves
a channel beyond its own audience — the only way a new channel grows:

```
The Analyst           599,000 subs   0.1 views/sub
EverythingProfessor   576,000 subs   0.2
Beyond Military       573,000 subs   0.5
Tech Explained         13,200 subs   2.9
True Crime & Forensic   8,340 subs   5.5
Geography Explainer     1,440 subs   7.3
```

The 8,340-subscriber channel converts **55x better per subscriber** than the
599,000-subscriber one.

*Criteria are now `2026-07-30.2`:* skew ≤3, n ≥8, median ≥10,000, views/sub ≥1.0,
subs <150,000, not a personal brand. Re-judging all 176 stored channels cost
**zero quota** — the reason analytics was split from resolution (C-028 era work).

*The general failure:* a threshold chosen for convenience became a proxy for
something it never measured, and it silently determined the project's direction
for a week. Any absolute threshold applied across channels of wildly different
sizes deserves this suspicion.
