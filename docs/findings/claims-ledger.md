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
**Status:** `CONFIRMED` · 2026-07-29 · 3 failures out of 3 attempts

Every attempt to guess a handle hit the wrong channel:

| Guessed | Reality |
|---|---|
| `@BikeGenMountain` | irreconcilable numbers; a revenue claim was withdrawn on bad data |
| `@Brainosophy` | a 1,674-view channel; the real one is `@brainosophic` |
| `@PaintProfessor` | 154 subs, 1,579 lifetime views — not the channel cited |

`channels.list` with `forHandle` costs 1 unit and returns the exact channel;
`search.list` costs 100 and returns a guess.

*Consequence:* the `paintprof_*.jpg` reference thumbnails in `data/samples/refs/`
are of unverified provenance and must not be cited.

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
**Status:** `HYPOTHESIS` · 2026-07-29 · fits n=16, tested on nothing

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
**Status:** `HYPOTHESIS` · 2026-07-29 · n=8 videos

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

The policy (renamed 2026-07-15) bans mass-produced templates and verbatim
readings. A rigid per-video template is exactly what these channels run. Whether
the authored-visuals distinction (C-017) is what keeps them compliant is
untested and consequential — it gates monetisation.
