# Findings — 2026-07-26

What a day of real data changed. Written up because the conclusions cost ~10,000 API
units and two full implementations to reach, and would be expensive to rediscover.

## 1. Niche research via public YouTube data does not work

Two implementations, both run against live data, both failed the same gate: *if the
top-ranked niche is one you could have guessed without building this, the engine told
you nothing.*

**Revision 1 — state metrics.** Ranked niches by competitor count, view velocity and
"entrability" (fraction of channels under 18 months old). Result: finance first, which
is the obvious guess.

Root cause: `competitor_count` was bounded by our own sample size. Search returns the
incumbents for every query, so the metric measured our sampling, not the market. Across
three niches it read 39 / 38 / 30, and entrability 0.19 / 0.21 / 0.23 — no spread, no
signal. The score collapsed to an RPM lookup.

**Revision 2 — trajectory metrics.** Replaced states with transitions: reconstruct each
channel's climb from per-video view velocity, find the inflection where it broke out,
diff its pre- and post-inflection videos.

At small samples (7–24 channels/niche) this looked like it worked — business ranked
first, finance fell to sixth, breakout rate spanned 0.22–0.88. At proper samples
(34–71 channels/niche) it collapsed: breakout rate 0.38–0.71 and median lift 4.8–9.9
across **all fifteen** niches, and the ranking reverted to RPM order.

**Root cause, and it is fatal.** `views ÷ days_since_publish` is not comparable across
video ages. YouTube views are front-loaded — a video earns most of its lifetime views in
its first weeks — so a recent video always scores higher velocity than an old one of
identical real performance.

Verified directly against MrBeast, a mature channel with no recent breakout:

```
50 videos, ages 163d..1d
median views/day   older half:   944,134   newer half: 2,851,300   lift: 3.0x
median RAW views   older half: 119,902,788  newer half:  85,684,175
```

A 3.0× "breakout" on a channel whose raw view counts are *declining*. `MIN_LIFT` was
3.0, so MrBeast registered as a breakout. The uniform 0.38–0.71 rates across every niche
are largely this artifact.

**Why it is not fixable here.** Separating "this channel improved" from "this video is
newer" requires knowing what a video had earned *at a given age*. The API returns only
current totals. This was flagged as a constraint on day one; revision 2 did not solve
it, it hid it behind a ratio.

## 2. Threads is useless for ranking niches, useful for discovering them

`@_automationexpert` (10K followers, sells a course, bio: "DM 'YT' to start") posts
niche lists with channel names and numbers. Every checkable claim, verified via the API:

| Channel | Claimed views | Actual views | Subs | Videos | Created |
|---|---|---|---|---|---|
| Explained in minutes | 2.5M | 2,475,477 | 110,000 | 2 | 2026-02-26 |
| Its Just Cars! | 6M | 6,132,088 | 17,100 | 142 | 2024-03-30 |
| American Legends | 14.1M | 14,350,373 | 38,700 | 193 | 2024-01-07 |
| ENEM | 4.5M | 4,674,845 | 50,900 | 28 | 2023-06-25 |
| American Secrets | 176k in 6d | 327,518 | 1,740 | 6 | 2026-06-04 |

Four of five verify within 4%. He is reading real dashboards.

**But the earnings figures are not measurements.** Every one is `views × $5 ÷ 1000` —
his own arithmetic, formatted to look like data alongside the verified view counts.
Verifying views does not verify money, and the flat $5 RPM is applied to US car content,
Brazilian exam prep and Indian explainers alike.

**One claim fails outright.** "NEW Channel has generated $50k in revenue last 30 days"
over a `$52,143` screenshot, captioned on **BikeGen - Mountain** — a channel with
1,713,546 *lifetime* views. At his own $5 RPM that is ~$8,500 total, ever. The screenshot
and the channel do not reconcile.

## 3. Format beats topic, and volume is not the lever

The verified channels, by output efficiency:

```
Explained in minutes    2 videos →  2,475,477 views   1,237,739 views/video
ENEM                   28 videos →  4,674,845 views     166,959 views/video
American Legends      193 videos → 14,350,373 views      74,354 views/video
Its Just Cars!        142 videos →  6,132,088 views      43,184 views/video
```

A 28× spread in views-per-video across cars, US history, Brazilian exam prep and AI
explainers. Topic does not explain it. All four are faceless, AI-assisted, tightly-scoped
explainers — they share format, not subject.

Explained in minutes cleared the 1,000-subscriber gate with **two videos in five months**.
Its Just Cars needed **142 videos over 16 months** to reach 17,100 subscribers.

Note also Its Just Cars: 17,100 subs against 6.1M views — a 0.28% subscriber rate. Faceless
content converts viewers to subscribers poorly, so the 1,000-sub gate costs far more views
than it would for a face-led channel.

## 4. Decisions

1. **Stop building niche research.** Public data lacks the time dimension required. Pick
   topic on RPM and on what can be sustained weekly.
2. **Revise Plan 2 toward fewer, better videos.** The volume assumption baked into the
   original plan is contradicted by the two highest-efficiency channels in the sample.
3. **Keep the verification workflow.** Mining a social feed for named channels and checking
   each against the API cost ~3 quota units per channel and turned marketing into evidence.
   That is the one part of today worth automating.
4. **Retention is the untested variable.** Every conclusion here is about reach, not
   watch-time, because the API exposes retention only for channels you own. That gap closes
   by publishing, not by more research.

## Method note

Both failed revisions shared a pattern worth naming: a metric that looked discriminating at
small sample sizes and flattened at large ones. In both cases the small-sample result was
the encouraging one. Check spread at full sample before believing a ranking.
