---
name: threads-channel-research
description: Use when researching YouTube niches, channels, or earnings claims from social media - gathers Threads posts and their screenshots, reads channel names out of the images, then verifies every named channel against the YouTube Data API and writes a report separating checked facts from uncheckable claims.
---

# Threads → verified channel research

Social posts about YouTube earnings are claims. This loop turns the checkable
ones into measurements and counts the rest as uncheckable rather than quietly
believing them.

**The whole reason this exists:** the channel being discussed is almost always
named *inside an attached screenshot*, never in the caption. A first pass that
read captions only concluded 0 of 9 monetary claims were verifiable. Reading the
images, the first two attempted checks both verified. See C-039 in
`docs/findings/claims-ledger.md`.

## Step 1 — gather (free, no quota)

```bash
pipeline leads "faceless youtube" --expand
pipeline leads "youtubecreators" --tags --expand   # tag feed / community
```

**Always pass `--expand`.** On Threads the top-level post is a teaser — it ends
on "here's how I did it:" and every actual step is a *reply*, posted as an image.
Without expansion you collect headlines and throw away the article. On the first
real run, expansion recovered 17 step screenshots against 18 top-level ones:
roughly half the evidence.

Expansion is slow — one JavaScript-rendered fetch per post via Jina's
`x-timeout` header — so it is bounded to the posts carrying the most monetary
claims. Replies by anyone other than the original author are ignored.

Writes `data/leads/<date>-<query>/` containing `leads.json` and `images/`.
Reports how many handles appeared in captions (usually zero) and how many
screenshots came down.

Good queries: `faceless youtube`, `youtube automation`, `channel spotted`,
`youtube niche`. The `--tags` feed reaches community posts; `CHANNEL SPOTTED`
posts are the richest vein — they name a small channel with its niche and format.

## Step 2 — read the screenshots (this is the step that needs eyes)

Read every file in `<run>/images/`. Files ending `_replyN` are the walkthrough
steps and are usually where the method — and sometimes the channel — is shown. They are typically YouTube Studio panels or
channel pages. Extract:

- **`@handle`** — the whole point. Usually in the channel-page header.
- **subscriber count and video count** — to compare against the caption's claim.
- **revenue and views over the same window** — these give a *computed RPM*, the
  only RPM evidence in this project not sourced from a marketing blog (C-040).
- **thumbnail style** — the recurring finding is that crude line art wins
  (C-011, C-041).

Then record what you found, keyed by permalink:

```python
from pathlib import Path
from contentforge.research.leads import add_image_handles
add_image_handles(Path("data/leads/<run>"), {
    "https://www.threads.net/@poster/post/ABC": ["someunfilteredguy"],
})
```

An empty `handles_from_images` means *not yet read* — deliberately distinct from
*read, found nothing*. Do not skip this step and go straight to verify; you will
reproduce the original error.

**Never complete a truncated handle.** Screenshots crop and tooltips overlap, so
a header often reads `@ultrasfct…`. Guessing the rest reproduces C-008, which has
now been wrong 4 times out of 4 — most recently while building this very skill,
where `@ultrasfctv` was invented from a covered header and resolved to an
unrelated 217-subscriber channel. If the handle is not fully legible, record it
as unread and move on.

**Sanity-check every profile against its screenshot.** The verify step is what
catches a bad handle: if the screenshot showed a 1.3M-view video and the API
reports a 342-view median, the handle is wrong, not the channel. Treat any
contradiction as a failed lookup and discard the row.

## Step 3 — verify and profile (~2 quota units per channel)

```bash
pipeline leads-verify data/leads/<run>
```

Resolves each handle with `channels.list` (1 unit, exact) — **never** by search,
which costs 100 and returns a guess. Handle-guessing is now 4-for-4 wrong (C-008).
Then profiles every channel on **median, skew and hit-rate**. Never rank on mean:
it overstates the median by more than 2x on 58% of channels (C-001).

`repeatable` means skew ≤3, hit-rate ≥40%, and n ≥8. Only ~5% of channels
qualify; the rest are lottery-shaped (C-020).

## Step 4 — record what was learned

Add findings to `docs/findings/claims-ledger.md` with a status and a sample size.
Anything under n≈10 is a `HYPOTHESIS` regardless of how clean it looks — three
rules in this project died from being read off n=4.

If a claim verified, say so with the numbers. If it could not be checked, that is
also a finding: the report counts uncheckable claims for exactly this reason.

## What this loop cannot tell you

Within-channel variance — why one video beats its sibling — is not visible from
outside. Click-through rate against impressions is owner-only. Eight
externally-observable hypotheses have already been tested and refuted (C-028).
Use this loop to find and check channels, not to explain their performance.

## Cost

Step 1 and 2 are free. Step 3 costs ~2 units per named channel against a
10,000/unit daily quota that resets at **Pacific** midnight. A 20-post run
naming 5 channels costs about 10 units.
