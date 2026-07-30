# Preregistration — held-out test of C-015

Written **before** any channel was selected or any caption read. Committed before
execution so the protocol cannot be adjusted to fit the result.

C-015 was generated from the same sixteen videos that refuted C-014. That makes
it a hypothesis fitted to its own evidence. This is its first real test.

## Hypothesis

**A video's opening 50 seconds attaches to something the viewer already
possesses** — a belief they hold, a person they can picture, an experience they
have lived, or a concrete scene — **rather than to an abstraction the viewer must
already care about.** Videos that attach outperform videos that abstract, within
their own channel.

## Selection rule, fixed in advance

Channels are drawn from `docs/evidence/2026-07-29/scan-rev2-channel-profiles.csv`
and must satisfy, in this order:

1. **Not previously examined.** Excludes Art History Explained, Bluntly Explained,
   Explainer Chris, Paint Professor, Brainosophy, Pilot Debrief, Air Crash
   Investigation, Joe Bart Philosophy, How Money Works Uncut, Imagine the Physics.
2. `n_long >= 12` — enough videos for extremes to be meaningful.
3. `spread >= 5` — hits and flops must actually differ, or the test has no signal.
4. **Age-matched** (C-006): within each channel, hits and flops are drawn only
   from videos whose publication ages overlap, and the median age of the hit group
   and the flop group must differ by **less than 60 days**. Channels that cannot
   meet this are dropped, not adjusted.
5. Top 3 and bottom 3 by view count within the age-matched pool.

No channel is inspected before these rules are applied. Channels are taken in the
order the rules yield them.

## Blinding

The captions are split into two files by script:

- `blind-openings.txt` — the first ~50 seconds of each video, labelled with
  opaque IDs ordered by a hash of the video ID, so ordering carries no
  information about views or channel.
- `blind-key.csv` — the ID → channel/views/hit-or-flop mapping.

**The key is not read until every classification is recorded.** Classifications
are written to `blind-calls.csv` and committed before unblinding.

## Classification criterion, fixed in advance

Each opening is labelled exactly one of:

- **ATTACHES** — within the first 50 seconds the viewer is given a belief they
  already hold, a specific named person, a lived experience, or a concrete
  physical scene they can picture without prior knowledge.
- **ABSTRACTS** — the opening requires the viewer to already care about a concept,
  category, or field. Includes topic announcements ("that's the topic of today's
  video") and definitions offered before any concrete anchor.

Ambiguous cases are labelled **ATTACHES**, deliberately biasing against the
hypothesis: if the rule only works when marginal cases are read charitably, it is
not a usable rule.

## Success criterion, fixed in advance

Let *A* = share of hit videos labelled ATTACHES, *B* = share of flop videos
labelled ATTACHES.

- **SUPPORTED** if `A - B >= 0.40` and `A >= 0.70`.
- **REFUTED** if `A - B <= 0.15`.
- **INCONCLUSIVE** otherwise — recorded as such, and C-015 stays a hypothesis.

A per-channel breakdown is also reported. If the rule holds in aggregate but
fails in more than one channel, that is reported as a scope limit rather than
smoothed over — this is exactly how C-014 died.

## Committed in advance

Whatever the outcome, it is written into the ledger. A refutation here is a
successful test, not a failure: it costs one afternoon instead of a build.
