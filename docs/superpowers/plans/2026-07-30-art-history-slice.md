# Plan 3 — Art History Vertical Slice

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax.
>
> **Read [`docs/findings/claims-ledger.md`](../../findings/claims-ledger.md) first.**
> Every design decision below cites the claim that justifies it. Where this plan
> and the ledger disagree, the ledger wins.

**Supersedes** Plan 2 tasks 5–8. Plan 2 tasks 1–4 (LLM client, sourcing, script
generation, the validator) are implemented and unchanged.

**Goal:** publish three artist-biography videos, then read retention and CTR.

That last clause is the point. C-028 established that no externally-visible
variable explains why one video beats its sibling, and that the deciding one —
click-through against impressions — is visible only to the channel owner. Three
videos exist to produce that data. They are an instrument, not a launch.

---

## What we are building, and why each choice is what it is

| Decision | Justified by |
|---|---|
| Long-form artist biography, 17–22 min | C-034; runtime carries multiple mid-rolls |
| Public-domain artworks only | C-033 — *Bridgeman v. Corel*, EU DSM Art. 14 |
| Crude-but-clear visuals; no polish budget | **C-011** — a crude video beat its polished sibling 57x |
| One fixed opening style, chosen once | C-027 — opening style is a channel-level constant |
| Narration backend is a decision, not a default | C-049 — no free TTS matches a human reading their own prose |
| Per-video authored substance | C-032 — the inauthentic-content monetisation gate |
| Rank nothing on mean views | C-003 |

**Expected outcome, stated so we cannot quietly move the goalposts:** roughly
**26,000 median views** and **~$100–200 per video**, anchored on Narrative Art
History (C-035), *not* on Art History Explained's 112,000 median.

⚠️ **Revised 2026-07-30.** Art History Explained turns out to be Christopher P
Jones, an art-history writer narrating his own work with a 6,000-subscriber
Substack behind him (C-048). It is not a faceless channel and its numbers are not
a target an AI pipeline should expect to reach. Anchoring on Narrative Art
History was already the plan; that now looks conservative in the right direction,
and even it is a channel whose production model is unverified.

The niche still stands, but on the copyright position, the absence of aviation's
advertiser-suitability exposure, and the architecture fit — not on demand
evidence.

### Explicit non-goals

- **No whiteboard animation.** C-013 — the winners show static line art; no such
  tool is involved.
- **No labelled-grid thumbnails.** C-011 — that is the *failing* copycat's
  opening frame. `src/contentforge/visuals/thumbnail.py` is to be deleted, not
  extended.
- **No asset-fidelity optimisation.** Refuted. Spend the effort on script.
- **No opening-line A/B testing.** C-015 was refuted under a preregistered blind
  test; opening style does not vary within a channel.

---

## Task 1: Public-domain artwork sourcing

**Files:** `src/contentforge/sourcing/artworks.py`, `tests/test_artworks.py`

**Interfaces:**
- `search_artworks(query, transport) -> list[Artwork]`
- `Artwork` — frozen: `title`, `artist`, `year`, `image_url`, `source`,
  `license`, `credit_line`, `retrieved_at`
- `assert_public_domain(artist_death_year, now) -> None` — raises below life+70

**Implemented 2026-07-30** across two sources, both free and keyless:

- `sourcing/artworks.py` — the Met's open-access collection
- `sourcing/commons.py` — Wikimedia Commons

Two sources because one is not enough (C-045): the Met holds **no** open-access
Monet, Renoir or Klimt, while Commons returns 22, 28 and 15 respectively. The
Art Institute of Chicago was tried first and dropped — its image host answers
with a Cloudflare challenge instead of a JPEG.

Each source has its own trap, and each is covered by a test built from a real
result: the Met's `artistOrCulture` search flag returns 0 for every artist, and
on Commons the `Artist` field names the *photographer* rather than the painter
(C-046).

**The licence gate is not optional.** C-033 holds only for artworks that are
themselves public domain. Cézanne (d. 1906), Degas (1917), Klimt (1918), Monet
(1926), Klee (1940) and Kandinsky (1944) all clear life+70; Picasso (d. 1973)
does not until 2043. A run that cannot establish an artist's death year must
fail, not guess.

- [x] **Step 1: Failing tests**
- [x] **Step 2: Implement** — the Met
- [x] **Step 3: Wikimedia Commons as a second source**
- [x] **Step 4: Run tests** — 45 tests across both sources, 291 total
- [x] **Step 5: Commit**

Verified live: Picasso returns 0 from both sources (in copyright until 2044),
Cezanne and Degas return only their own works, Commons covers the artists the
Met does not, and images download as valid JPEGs.

Use `survey_artists()` before committing to a subject — availability does not
follow fame or death date.

## Task 2: Voice

**Files:** `src/contentforge/voice/speak.py`, `tests/test_speak.py`

Carried over unchanged from Plan 2 Task 5 — it was never contentious.

**Interfaces:** `strip_citations(script) -> str`; `synthesise(text, out_path, voice) -> Path`

Citation markers are for the validator and the description. `[1]` must never be
spoken. Add `edge-tts` to `pyproject.toml`.

- [x] **Step 1: Failing tests** — 19 of them
- [x] **Step 2: Implement**
- [x] **Step 3: Run tests** — 310 total
- [x] **Step 4: Commit**

**Done 2026-07-30.** Verified live: 12.94s of speech from a sample paragraph,
35 word timings, no citation marker spoken, valid MP3.

Two things worth carrying into Task 3:

- `Narration` returns **word-level timings**, not just a duration. edge-tts >=7
  defaults to `SentenceBoundary` and then emits no word events at all, so
  `boundary="WordBoundary"` is requested explicitly. Task 3's requirement that
  shot durations sum to the narration duration is now measurable rather than
  estimated.
- Output is 24 kHz mono at 48 kbps. That is edge-tts's fixed format and is fine
  for narration — YouTube re-encodes regardless — but it is not a knob that
  exists if the audio is ever judged thin. (The exemplar publishes 48 kHz
  stereo, though YouTube's own re-encode makes the comparison less meaningful
  than it looks.)
- **Pace is matched to the exemplar by measurement** (C-047): 142 wpm across
  2,592 words of its Cezanne video, against edge-tts's default 162. `-12%` lands
  at 143. Everything else about the voice needs a human ear.

## Task 3: Visual composition

**Files:** `src/contentforge/visuals/compose.py`, `tests/test_compose.py`

**Interfaces:**
- `plan_shots(script, artworks) -> list[Shot]`
- `Shot` — frozen: `image_path`, `start_s`, `duration_s`, `pan`, `chapter_title`

One artwork per narration beat, slow pan, chapter title held at the top. That is
what the exemplar does, and C-011 says do not spend beyond it.

**A shot without an artwork is an error.** Filling a gap with a stock image is
how the failing copycat worked (C-031) — found imagery pasted in, including a
diagram it did not own.

- [ ] **Step 1: Failing tests**
  - every narration beat maps to exactly one shot
  - shot durations sum to the narration duration (within a tolerance)
  - a beat with no artwork raises rather than reusing the previous image
  - chapter titles propagate to every shot in that chapter
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit** — `feat: plan shots from script beats and artworks`

## Task 4: Render

**Files:** `src/contentforge/render/video.py`, `tests/test_video.py`

**Interfaces:** `build_command(shots, audio, out_path) -> list[str]`;
`render(shots, audio, out_path, runner) -> Path`

Split so the ffmpeg invocation is testable without running ffmpeg. `build_command`
is pure and asserted against; `render` shells out through an injected runner.

1080p, `zoompan` for the slow pan, `-c:v libx264 -preset medium -crf 20`.

- [ ] **Step 1: Failing tests**
  - the command references every shot's image
  - the audio track is attached
  - a non-zero ffmpeg exit raises with stderr attached, never a silent partial file
  - output path is created only on success
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit** — `feat: render shots and narration to mp4`

## Task 5: Thumbnail

**Files:** `src/contentforge/visuals/thumbnail.py` **(delete and rewrite)**,
`tests/test_thumbnail.py`

Delete the existing file first. It generates a labelled grid of stock imagery,
which is verifiably the opening frame of a channel with a 239-view median
(C-009, C-011).

**Interfaces:** `build_thumbnail(artwork_path, artist_name, out_path) -> Path`

What the evidence supports and nothing more: the artwork itself, large and
legible at small size, with the artist's name. High contrast; readable as a
thumbnail-sized rectangle. The one property the winning grid and the losing grid
differed on was **legibility at small size** (C-011), so that is the only thing
to optimise.

- [ ] **Step 1: Delete the old file and its assumptions**
- [ ] **Step 2: Failing tests** — output is 1280x720; text present; raises when
      the source artwork is missing rather than emitting a blank
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit** — `feat: replace the grid thumbnail with an artwork crop`

## Task 6: Publish

**Files:** `src/contentforge/publish/youtube.py`, `tests/test_youtube_publish.py`

**Interfaces:** `upload(video_path, metadata, credentials, transport) -> str`

`videos.insert` costs **1,600 quota units** — 16% of a day. Pre-flight against
the ledger and refuse rather than fail mid-upload.

**Blocked on you:** an OAuth client (`client_secret*.json`, already gitignored).

Metadata rules, both from the ledger:
- `madeForKids=False` — C-022 territory; the COPPA classification costs ~10x RPM
- description carries every source URL — the provenance rule, and it is also
  what distinguishes authored work under C-032

- [ ] **Step 1: Failing tests** — a run without headroom raises before uploading;
      metadata includes sources; `madeForKids` is explicitly set, never defaulted
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit** — `feat: upload to YouTube with a quota pre-flight`

## Task 7: Instrumentation — the actual experiment

**Files:** `src/contentforge/research/ours.py`, `tests/test_ours.py`

**Interfaces:** `record_performance(video_id, stats, path) -> Path`;
`compare_ours(rows) -> str`

This is why the other six tasks exist. YouTube Analytics exposes to the channel
owner what no third party can see: impressions, click-through rate, and the
retention curve (C-028).

Store per video, per pull, so a curve accumulates: `views`, `impressions`,
`ctr`, `average_view_duration`, `average_percentage_viewed`.

Compare **only against our own videos**, age-matched — C-005 and C-006, the two
rules that made within-channel comparison work in the first place.

- [ ] **Step 1: Failing tests**
  - a pull that returns no impressions is recorded as unknown, never zero
    (the `quota_monitor` invariant: unknown must never read as zero)
  - two videos of different ages are not compared directly
  - repeated pulls append rather than overwrite
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run tests**
- [ ] **Step 4: Commit** — `feat: record our own retention and CTR`

---

## Running order

Tasks 1–5 are independent of credentials and can proceed now. Task 6 waits on the
OAuth client. Task 7 waits on the first upload.

## Definition of done

1. Three artist-biography videos published, each 17–22 minutes.
2. Every factual claim in every script resolves to a fetched source.
3. Every artwork verified public domain, with its credit line recorded.
4. Retention and CTR captured for all three.
5. **A ledger entry comparing outcome to the ~26,000 median forecast** — whether
   it confirms or refutes.

Point 5 is the deliverable. Three videos that produce no recorded finding would
repeat the mistake this project spent a week correcting.

## What could make this wrong

- **RPM at ~$4 rather than $8** (C-040) would halve the revenue case. Real RPM
  is knowable only from our own Studio data — Task 7 answers it.
- **C-023 rests on n=8** and Art History Explained is an outlier within its own
  niche (C-035). The niche does not confer its numbers.
- **C-032** is judged by human review at YPP application, not by a rule we can
  test in advance.
