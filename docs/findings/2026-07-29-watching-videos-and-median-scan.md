# Findings — 2026-07-29

The day the project first watched a video.

Every claim previously made about what winning videos look like was inferred
from thumbnails and API metadata. Two tools changed that: `claude-video` (yt-dlp
+ ffmpeg frame extraction + captions) for seeing inside a video, and a corrected
scan for ranking channels on statistics that survive skew.

Claim IDs below refer to [claims-ledger.md](claims-ledger.md), which carries the
current status of each. **This document records what was observed on this date;
the ledger records what is still believed.** Where they disagree, the ledger wins.

Raw data: `docs/evidence/2026-07-29/`.

---

## 1. Asset polish is not the lever, and may be negatively correlated

The controlled comparison is two videos from **Bluntly Explained** — same
producer, same visual style, same subscriber base, four days apart in cut rate:

| | Every DIMENSION Explained | The BIGGEST Explosions |
|---|---|---|
| views | **532,684** | 9,343 |
| visuals | crude black doodles on white | polished full-colour space art |
| on-screen errors | "Nineth Dimension" | none observed |
| cut rate | 4.3 s/shot | ~4 s/shot |
| opening panel | high-contrast, reads **"3D · YOU"** | 12 blurry grey cells, illegible |

**The better-looking video lost by 57x** (C-011).

The winner's visual grammar: a stick-figure smiley on black for the zeroth
dimension, a doodled steam train for the first, a hand-drawn JOB OFFER letter
stamped REJECTED for the fifth, hand-lettered word cards ("DIFFERENT STARTING
POINTS", "THERE."), and a chapter title at the top of every shot. A recurring
dark AI-rendered panel grid serves as a navigational spine between chapters —
which is where the thumbnail is cropped from.

Structure is a ladder with a payoff: 0D → 11D, each rung reframing the last,
closing on a callback to the empty point from the opening.

### The copycat

`@PaintProfessor` — 154 subscribers, median **239** views (C-009) — runs the
identical title template, "Every X Explained in N Minutes", on all six videos.

It opens on a **6-cell circular grid: flat silhouettes in coloured circles with
labels underneath**. That is very nearly the template
`src/contentforge/visuals/thumbnail.py` was built to generate.

Its interior is scraped reference charts: a five-panel taekwondo kick diagram
with body-copy captions, a Kung Fu stance chart still labelled **in French**.
Found images, pasted whole.

So the format is worth nothing on its own (C-010), pacing is not the
differentiator (C-012), and polish is not either (C-011). What is left is that
the winner's drawings each serve one narrated idea and the copycat's do not
(C-017 — hypothesis, not established).

### What this kills in the codebase

`src/contentforge/visuals/thumbnail.py` generates a labelled grid of stock
imagery. That is, verifiably, the opening frame of the failing channel. It
optimises the wrong variable and should not be extended.

Also settled: no whiteboard-animation software is involved (C-013). Frames show
complete line-art images held statically, one per narration beat, with no
progressive draw-on. The open-source options (scriptimate, SVGVideoMaker) are
not worth adopting because the technique they implement is not the one in use.

---

## 2. Mean views-per-video is broken, and every prior ranking used it

Across 146 channels in 24 niches:

```
mean overstates median by >2x     84 / 146   (58%)
median skew                            2.3x
worst skew                            98.3x
repeatable channels                 7 / 146   (5%)
```

"Repeatable" = skew ≤3, hit-rate ≥40% at a 100,000-view threshold, n ≥8 videos.
**95% of channels depend on occasional viral hits** (C-020).

The headline casualty is Explainer Chris, cited at "201,427 views/video" in the
2026-07-26 findings. Its median is **34,518** — nine hits carrying fifteen flops,
floor 1,177, ceiling 1,736,716 (C-002).

### The seven repeatable channels

```
niche          channel                        subs      n     median  skew  hit%  v/sub   age
kids_learning  Kalam Kids (Islam & Arabic) 316,000     38  1,330,195   1.4   92%   4.2   1200d
aviation       Pilot Debrief             1,030,000     43    788,580   1.4  100%   0.8    325d
philosophy     Joe Bart Philosophy         878,000     50    554,352   1.3  100%   0.6    349d
aviation       Air Crash Investigation     237,000     43    478,896   1.6   84%   2.0    905d
economics      How Money Works Uncut       113,000     48    168,484   1.5   69%   1.5    697d
history        Art History Explained        16,700      8    112,326   1.0   62%   6.7    280d
physics        Imagine the Physics          69,200     15     57,374   2.6   47%   0.8    206d
```

**Art History Explained is the only reachable profile** (C-023): 6.7 views per
subscriber against 4.2 for the next best and under 2.0 for most, at skew 1.0.
The rest sit at 69K–1.03M subscribers, where a new channel can infer nothing
about its own prospects.

Aviation is the strongest niche measured — 14 channels, 2 repeatable (C-021).

Graveyards, all with zero repeatable channels (C-022):

```
psychology   10 channels   median-of-medians   475   skew 8.1x
math          5 channels                       367
space         4 channels                       420
language     21 channels                     5,150   most channels of any niche
```

### The scan was run twice, because rev 1 was biased by its own prefilter

Rev 1 selected the top 12 channels per niche by `total_views / video_count` —
the mean, the statistic the same run then proved broken (C-016). Rev 2 removed
all ranked prefiltering and deep-scanned every channel passing basic gates.

```
              n    median skew   repeatable   median-of-medians
rev 1 (mean)  76      2.9x        3 (4%)          3,136
rev 2 (none) 146      2.3x        7 (5%)          2,104
```

Rev 1's channels were 26% more skewed and its median-of-medians 49% inflated.
Direction as predicted; the headline conclusion survived.

Rev 2 also persists **every candidate found, gated or not** — 1,189 rows in
`scan-rev2-all-candidates.csv` — so any future re-filter costs zero quota
instead of another 2,400 units. Rev 1's failure to do this is why it had to be
re-searched rather than re-analysed.

Total cost: 2,217 units (rev 1) + 2,791 (rev 2) + 26 ad-hoc = ~5,034 of 10,000.

---

## 3. A script rule that held at n=8 and broke at n=16

### Within Art History Explained, it holds cleanly

Eight videos, production held constant — same paintings-with-slow-pans, same
photographic b-roll, same narrator, same "The Life and Art of X" title:

```
video       views    born-date  "story of an artist who…"  reversal <60s  question
Cézanne   216,697       yes              yes                    yes       "How did he do it?"
Kandinsky 198,311       yes              yes                    yes       "How did he get there?"
Klee      136,680       yes              yes                    yes       forward promise
Degas     113,806       yes              yes                    yes       "How should we read…"
Monet     110,845        no               no                    yes       —
Klimt      94,570       yes              yes                    yes       —
────────────────────────────────────────────────────────────────────────────────────
Caravaggio  5,210        no               no                     no       —
Bruegel     3,699        no               no                     no       —
```

Every hit opens on a specific sourced obstacle plus a turn. Caravaggio opens on
praise — "powerful images of passion, pain and devotion come to mind" — and lost
20–40x to its own siblings.

Two sub-rules died here. **Narration start time doesn't matter** (C-018): Klee
begins at 00:38 and got 136,680, against 00:03 for Degas and Monet. **The "This
is the story of" opener isn't required** (C-019): Monet skips it, opening with
the same assumed-familiarity move Caravaggio flopped with, then pivots — "aged
just 27, he stood on the edge of the Seine and considered ending his life."

### Across channels, it fails

Tested on four age-matched repeatable channels, with the criterion committed to
in writing before any caption was read.

| Channel | Verdict |
|---|---|
| Joe Bart Philosophy | holds — hits carry dates, altitudes, names; flops open "it's midnight and I want to rant" |
| How Money Works Uncut | holds — hits carry absurd specifics; flops open on abstractions |
| Pilot Debrief | partial — *all four* have turns; hits differ by naming a single identifiable person |
| **Imagine the Physics** | **fails** — hits and flops run the identical setup-then-subvert structure |

```
HIT   502K  "You think you understand gravity? … Simple. … The so-called force"
FLOP   33K  "Picture an electron scattering off a photon. Simple enough, right? … But"
FLOP   21K  "How hot can things get? There's no limit, right? … So what about cold?"
```

Imagine the Physics had the tightest age match in the set — hits 149–203 days,
flops 147–182 days — so **the refutation comes from the best-controlled
comparison available** (C-014).

Air Crash Investigation was excluded before testing: its hits are 639–881 days
old and its flops 49–110, which is the view front-loading confound that killed
research engine v2 (C-006).

### The replacement hypothesis, and why it is not yet a finding

Every hit opens on something the viewer already possesses — a belief they hold
(gravity, time dilation), a person they can picture (Jenny; Sarah; McCandless
317 miles up), a grievance they have lived (a $15/hr ad demanding 10 years on a
20-month-old program). Every flop opens on an abstraction the viewer must
already care about: specialised labour, business ethics, antimatter, corporate
social responsibility, electron-photon scattering.

**This rule was generated from the same sixteen videos that refuted the previous
one** (C-015). Fitting a new rule to the data that killed the old one is not
evidence, and this project has now made that error three times (C-004, C-007,
C-014). It requires a held-out set: channels not yet examined, hits and flops
selected by view rank *before* any caption is read.

Note also that "flop" is not comparable across channels. Joe Bart's worst videos
sit at 160K–271K; Imagine the Physics' at 19K–33K.

---

## 4. Method notes

**Handles must be resolved, never guessed** (C-008). Three guesses, three wrong
channels. `channels.list` with `forHandle` costs 1 unit and is exact;
`search.list` costs 100 and returns a best guess by display name. The
`paintprof_*.jpg` files in `data/samples/refs/` are of unverified provenance and
must not be cited.

**Captions are free and off-quota.** `yt-dlp --write-auto-sub --skip-download`
retrieves timestamped narration without touching the Data API. The entire
cross-channel script test cost 10 units — all of it spent listing videos, none
on the text that produced the finding.

**Commit the test criterion before looking at the data.** Doing so on the
cross-channel test is the only reason the refutation was recognised rather than
explained away; the temptation to reclassify Imagine the Physics as "partial"
was immediate and would have been dishonest.

**The open web is unusable for this topic.** Every search result was an
AI-video-tool marketing blog citing other marketing blogs. Nothing in this
document is sourced from that tier.

---

## 5. What this changes

1. **Stop extending `visuals/thumbnail.py`.** It reproduces the failing
   channel's opening frame.
2. **Re-rank everything on median and hit-rate** (C-003). Any prior ranking
   using mean views-per-video is void.
3. **Plan 2 should not be rewritten around the "Every X Explained" format**
   (C-010) — the format is free to copy and the copycat proves it carries no
   value alone.
4. **Do not build on C-015 until it survives a held-out test.** It is the most
   promising thing here and the most likely to be wrong.

Open and unresolved: what changed to make this format work in the last five
months when identical titles earned 239 views two years ago (C-024), and whether
a rigid per-video template survives the "inauthentic content" policy that gates
monetisation (C-025).

---

## 6. Addendum — C-015 refuted, and observational analysis closed out

C-015 was tested under a [preregistered blind
protocol](2026-07-29-C015-preregistration.md) and **refuted**: hits attached at
0.62, flops at 0.73, difference **-0.11** against a refutation threshold of
+0.15. Every one of the six scorable channels scored exactly +0.00 — opening
style is a channel-level constant (C-027), so it cannot explain within-channel
variance, and C-014's apparent success was detecting one channel's inconsistency
with its own format.

That closes the observational programme. Eight externally-visible variables have
now been tested and refuted:

```
mean-based ranking      C-001      narration start time   C-018
format                  C-010      opener formula         C-019
asset polish            C-011      opening style          C-015 / C-027
cut rate                C-012      production tooling     C-013
```

The one remaining candidate is topic selection, and the variable that would
decide it — click-through rate against impressions — is visible only to the
channel owner (C-028). No quota buys it.

**So the next evidence has to be our own.** Further public-data analysis
generates hypotheses faster than it can test them, which is exactly how eight
died. Plan 2 already proposed publishing a few videos and reading retention; what
has changed is that we now know which variables not to spend effort on.

### What is settled enough to build on

- Rank on median and hit-rate, never mean (C-003).
- Compare only within a channel, only between age-matched videos (C-005, C-006).
- Resolve handles, never guess them (C-008).
- Do not invest in asset fidelity, template design, or opening-line engineering —
  all refuted.
- Instrument from the first upload: retention curve, CTR and impressions per
  video, so our own data is usable as the controlled experiment public data
  cannot provide.

### What still blocks a build

1. **Niche and channel identity** — a decision, not a finding. The scan offers
   aviation (C-021, strongest measured) and the Art History Explained profile
   (C-023, only reachable one). Both are hypotheses at thin `n`.
2. **`YOUTUBE_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS`** — without them
   quota accounting stays a local forecast rather than an authoritative read.
3. **YouTube OAuth client** for `videos.insert` (1,600 units per upload).
4. **Instagram Business conversion and a Meta app** — `instagram_business_basic`,
   `instagram_business_content_publish`, `threads_basic`,
   `threads_keyword_search`. 2–4 week App Review, so worth starting before it is
   needed.
5. **`src/contentforge/visuals/thumbnail.py` should be deleted or rewritten** —
   it reproduces the failing copycat's opening frame.
