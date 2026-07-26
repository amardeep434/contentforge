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
| Family Life English | (none stated) | 11,443,658 | 37,400 | 42 | 2026-06-12 |
| Armory Professor | 319 subs, 1 video | 166,508 | 778 | 2 | 2014-09-21 |
| Cinephile Unfiltered | 1.6M | 2,128,287 | 9,120 | 43 | 2025-07-23 |

Four of five view claims verify within 4%. He is reading real dashboards — plausibly Viewstats or vidIQ, both of which surface exactly these figures, and both of which derive earnings the same way he does.

Two later checks are less clean. Armory Professor supports its claim (319 subs and 1 video at post time, 778 and 2 now — it grew after the screenshot). Cinephile Unfiltered came in at 2,128,287 against a claimed 1.6M, 33% out on a day-old post, which is too far to call a match and is recorded as unverified rather than confirmed.

**But the earnings figures are not measurements.** Every one is `views × $5 ÷ 1000` —
his own arithmetic, formatted to look like data alongside the verified view counts.
Verifying views does not verify money, and the flat $5 RPM is applied to US car content,
Brazilian exam prep and Indian explainers alike.

**One claim fails outright.** "NEW Channel has generated $50k in revenue last 30 days"
over a `$52,143` screenshot, captioned on **BikeGen - Mountain** — a channel with
1,713,546 *lifetime* views. At his own $5 RPM that is ~$8,500 total, ever. The screenshot
and the channel do not reconcile.

## 3. Format beats topic. Volume is not the lever — but nor is scarcity.

The verified channels, by output efficiency:

```
Explained in minutes    2 videos →  2,475,477 views  1,237,739/video   110,000 subs in 5 months
Family Life English    42 videos → 11,443,658 views    272,468/video    37,400 subs in 44 days
ENEM                   28 videos →  4,674,845 views    166,959/video
American Legends      193 videos → 14,350,373 views     74,354/video
Its Just Cars!        142 videos →  6,132,088 views     43,184/video    17,100 subs in 16 months
```

A 28x spread in views-per-video across cars, US history, Brazilian exam prep, ESL instruction
and AI explainers. Topic does not explain it. All five are faceless, AI-assisted, tightly-scoped
explainers — they share format, not subject.

### The correction Family Life English forces

An earlier draft of this document concluded that **volume is the least efficient strategy**,
drawn from four channels where views-per-video fell as video count rose. Family Life English
breaks that: **42 videos in 44 days** — a daily upload cadence, the highest-volume operation in
the sample by rate — while sitting *second* in views-per-video at 272,468.

So cadence and per-video performance are **independent**, not inversely related. The original
reading mistook a small sample for a law. What separates the top and bottom rows is execution
inside a repeatable format, not restraint.

The defensible version: per-video quality is the lever, and high cadence is compatible with it
once the format is repeatable enough to hold quality at rate. Scarcity is not itself a strategy.

### The mislabel worth more than the growth number

The post showcasing this channel captioned it *"New YT update, new niche to get into —
educational kids channel might be the moves."* Both halves are wrong, and the error is
expensive.

**There was no relevant YT update.** The 2026 changes brought stronger parental controls and a
stated emphasis on learning content. Monetization for Made for Kids is unchanged: personalized
ads still disabled, RPM still $1–3, Super Thanks and Memberships still off.

**And it is not a kids channel.** Every title is tagged `(A2 Level)` — CEFR, the Common
European Framework for language learning. That is adult and teen ESL vocabulary, not children's
programming. Animated family stories are the teaching vehicle; the audience is people learning
English.

That distinction decides roughly a 10x revenue difference on identical output. Labelled Made
for Kids: $1–3 RPM, no Tier 1 path. Classified as education: $8–15 RPM, full features. Taking
the caption at face value would have pointed straight into the COPPA trap documented in the
niche table.

**Unresolved, and not guessed at:** actual RPM. ESL audiences skew toward Vietnam, Brazil,
Indonesia and India, where education RPM runs well below the US figures in `data/niches.csv`.
11.4M views could be $90,000 or $9,000; nothing public separates them. Whether the channel is
actually classified as education is visible only to its owner.

### A withdrawn claim

An earlier draft stated that the "$50k in revenue last 30 days" post over **BikeGen - Mountain**
was arithmetically impossible, on the basis that the channel had 1.7M lifetime views. That was
a **search** match, and searching by display name returns the wrong channel readily. The
screenshot shows 42.1K subscribers and 12 videos; `@BikeGenMountain` resolves to 83.8K
subscribers and 8 videos; and that same channel reported 1,713,546 views in one query and
538,382 in another hours later. None of it reconciles, and the claim is **unresolved rather
than disproven**. Handle lookup, not search, wherever a handle is available.

## 4. Decisions

1. **Stop building niche research.** Public data lacks the time dimension required. Pick
   topic on RPM and on what can be sustained weekly.
2. **Plan 2 optimises per-video quality, not throughput — but does not mandate scarcity.**
   Family Life English sustains a daily cadence at 272,468 views/video, so volume and quality
   are not in tension once the format is repeatable. Start at low volume because it is the only
   way to *learn* what works from retention data, not because fewer videos is inherently
   better.
3. **Keep the verification workflow.** Mining a social feed for named channels and checking
   each against the API cost ~3 quota units per channel and turned marketing into evidence.
   That is the one part of today worth automating.
4. **Audience labelling is a first-class revenue decision.** Made for Kids versus education
   is a ~10x RPM difference on identical output, set by who the content addresses. Any
   instructional format must be built for a stated audience, and that choice made deliberately
   rather than inherited from the visual style.
5. **Retention is the untested variable.** Every conclusion here is about reach, not
   watch-time, because the API exposes retention only for channels you own. That gap closes
   by publishing, not by more research.

## Method note

Both failed revisions shared a pattern worth naming: a metric that looked discriminating at
small sample sizes and flattened at large ones. In both cases the small-sample result was
the encouraging one. Check spread at full sample before believing a ranking.

The same error recurred in the qualitative analysis. "Volume is the least efficient strategy"
was drawn from four channels, held for exactly as long as it took to verify a fifth, and was
stated as a conclusion rather than as a pattern in n=4. Four data points produce a hypothesis.
They do not produce a law, and writing one into a spec makes it expensive to revise later.
