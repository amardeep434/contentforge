---
name: verify-creator-claims
description: Turn creator-marketing claims into evidence. Use when a social feed, video, newsletter or forum post names YouTube channels with view or earnings figures, or when the user asks whether a niche/channel/income claim is real. Extracts named channels, checks each against the YouTube Data API, and reports what verifies and what does not.
---

# Verifying creator claims

Social feeds are full of "this faceless channel did 6M views and earns $30,000/month".
Some of it is real. Most of the *money* part is not. This skill separates them.

## The core asymmetry

**View counts are checkable. Earnings are not.**

`channels.list` returns real subscriber, view and video counts for any public channel.
YouTube exposes revenue only to the channel owner. So when a post shows both, the views
can be confirmed and the money cannot — and posts routinely present the two in the same
list format, which reads as though both were measured.

In practice the earnings line is almost always `views × assumed_RPM ÷ 1000` — the
poster's own arithmetic. Confirming the view count does **not** confirm the revenue.
Say so explicitly every time.

## Workflow

**1. Extract every named channel.** Prefer @handles from screenshots — handle lookup
costs 1 quota unit; searching by name costs 100 and returns a guess. If you only have a
display name, search, then confirm you matched the right channel by checking whether its
view count is near the claimed figure before treating it as the same channel.

**2. Verify.** From the contentforge repo:

```bash
pipeline verify @handle1 @handle2 --claimed-views 6000000 --rpm 5
```

Handles resolve exactly; `--claimed-views` compares against the assertion;
`--rpm` produces an *implied* figure that the output labels as not a measurement.

**3. Check the arithmetic, not just the views.** Does the claimed revenue reconcile with
the channel's lifetime views at any plausible RPM? A "$50k in the last 30 days" caption
over a channel with 1.7M lifetime views does not reconcile at any RPM under $30, and
that gap is the finding.

**4. Report in a table.** Claimed vs actual vs error, per channel. State the tolerance
you used — a screenshot taken days ago against a channel that kept growing shows a real
discrepancy that is not a false claim. Distinguish OVERSTATED from UNDERSTATED.

## What to extract beyond the numbers

Verified view counts and channel ages support conclusions the poster usually isn't making:

- **Views per video** — divides output efficiency. Spreads of 20×+ are common between
  channels in the same format, and that spread is more informative than the topic.
- **Channel age vs video count** — distinguishes a grind from a lucky hit. Two videos in
  five months to 110k subscribers is a different phenomenon from 142 videos in 16 months
  to 17k, and only one is a repeatable plan.
- **Subscriber-to-view ratio** — faceless content converts poorly (~0.3% is normal), which
  determines how many views the 1,000-subscriber monetization gate actually costs.

## Cautions

- **Treat the poster's incentive as context, not as a verdict.** Someone selling a course
  can still be reading real dashboards. Check the numbers; do not dismiss on the bio.
- **Selection bias is total.** These are showcased winners. The sample says nothing about
  how many channels did the same thing and failed, and no amount of verification fixes that.
- **Never generalise RPM across niches.** A flat RPM applied to US car content, Brazilian
  exam prep and Indian explainers is wrong by a factor of 5-10.
- **Automating collection across a social feed at scale violates platform ToS.** Reading
  pages you are logged into is ordinary use; building a scraper on it is not.

## Related

`docs/findings/2026-07-26-research-engine-negative-result.md` records the run that produced
this workflow, including why ranking niches from public metrics does not work.
