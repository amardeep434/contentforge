---
name: research
description: Run whenever the user says "research", asks to look into a niche, channel, format or earnings claim, or asks what is working on YouTube. Runs the full loop end to end - gather Threads posts and their reply screenshots, read the images for channel names, verify every named channel against the YouTube Data API, record findings in the claims ledger, and file verified channels in the potentials list. Do not do ad-hoc searching instead of this.
---

# research

One word, one loop. Every stage runs; none is optional. The loop exists because
doing this by hand produced eight refuted hypotheses, four wrong channel
lookups, and a conclusion that was exactly backwards.

**Run all five stages before reporting.** Stages 2 and 4 need judgement, so this
cannot be a single command — but it is a single request, and stopping halfway
means reporting claims as if they were facts.

---

## 1. Gather — free, no quota

```bash
pipeline leads "<query>" --expand
pipeline leads "<topic>" --tags --expand      # community / tag feed
```

**`--expand` is mandatory.** A Threads post is a teaser ending in "here's how I
did it:" — every actual step is a *reply*, posted as an image. Without it you
collect headlines and discard the article (roughly half the evidence).

Good queries: `faceless youtube`, `youtube automation`, `channel spotted`,
`<niche> youtube`. `CHANNEL SPOTTED` posts are the richest vein — they name a
small channel with its niche and format.

Writes `data/leads/<date>-<query>/` (gitignored; regenerable).

## 2. Read the screenshots — needs eyes

Read **every** file in `<run>/images/`. Files ending `_replyN` are walkthrough
steps. What to pull out:

- **`@handle`** — the point. Usually in a channel-page header.
- **subs / video count** — to compare against the caption's claim.
- **revenue over the same window as views** — gives a *computed RPM*, the only
  RPM evidence not sourced from a marketing blog (C-040).
- **thumbnail and visual style** — crude line art keeps winning (C-011, C-041).

> **Never complete a truncated handle.** Tooltips crop headers to `@ultrasfct…`.
> Guessing the rest is C-008, now wrong 4 times out of 4 — most recently while
> building this skill, producing an unrelated 217-subscriber channel. If it is
> not fully legible, leave it unread.

Record what you found, keyed by permalink:

```python
from pathlib import Path
from contentforge.research.leads import add_image_handles
add_image_handles(Path("data/leads/<run>"), {
    "https://www.threads.net/@poster/post/ABC": ["someunfilteredguy"],
    "https://www.threads.net/@other/post/DEF": [],   # read, found nothing
})
```

Empty means *not yet read*; that is deliberately different from *read, found
nothing*, so record both.

## 3. Verify — ~2 quota units per channel

```bash
pipeline leads-verify data/leads/<run>
```

Resolves each handle with `channels.list` (1 unit, exact) — **never** search
(100 units, returns a guess). Profiles on **median, skew and hit-rate**; mean
overstates the median by >2x on 58% of channels (C-001).

Then it files every verified channel into `docs/evidence/potentials.csv`
automatically and prints the summary.

> **Sanity-check each profile against its screenshot.** If the screenshot showed
> a 1.3M-view video and the API reports a 342-view median, the handle is wrong,
> not the channel. Discard the row.

## 4. Record in the ledger — the part that makes it durable

Add or update claims in `docs/findings/claims-ledger.md`. Every claim carries a
**status** and a **sample size**:

| Status | Meaning |
|---|---|
| `CONFIRMED` | survived a test that could have refuted it |
| `HYPOTHESIS` | fits the data, never tested on held-out data |
| `REFUTED` / `WITHDRAWN` | contradicted, or retracted for method error |

Anything under n≈10 is a `HYPOTHESIS` however clean it looks — three rules here
died from being read off n=4 (C-004, C-007, C-014).

**When evidence flips a claim, edit the existing row and say what refuted it.**
Do not add a second row. The correction history is the point.

A claim that could not be checked is also a finding — the run report counts
uncheckable claims for exactly this reason.

## 5. Report

State what was verified, what was not, and the quota spent. Never present a
claim as a measurement. If a number came from a screenshot rather than the
API, say so.

---

## The potentials list

`docs/evidence/potentials.csv` — committed, cumulative, keyed on **channel id**
(handles get renamed). A channel checked once never needs checking again.

```bash
pipeline potentials            # summary
pipeline potentials --all      # every row
```

Statuses: `candidate` (measured, unjudged) → `watching` / `exemplar` /
`rejected`. Set `status` and `notes` by hand; **a refresh preserves them** while
updating the measurements, so judgement is never overwritten.

`repeatable` = skew ≤3, hit-rate ≥40%, n ≥8. Only ~5% qualify (C-020).
`reachable` = under 80k subs, i.e. small enough that its numbers say something
about a channel starting from zero.

## What this loop cannot answer

Why one video beats its sibling. Click-through rate against impressions is
owner-only, and eight externally-visible hypotheses have already been tested and
refuted (C-028). Use this to find and check channels — not to explain them.

## Cost

Stages 1–2 free. Stage 3 ~2 units per named channel, against 10,000/day
resetting at **Pacific** midnight. A 20-post run naming 5 channels ≈ 10 units.
