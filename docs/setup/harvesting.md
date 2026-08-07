# Harvesting a competitor channel

Instead of hand-writing a topic and sources, `harvest` takes a channel you've
already validated through research, pulls its recent upload titles and
auto-caption transcripts, and stages a batch of videos you render in your own
niche's style. This page assumes [running-the-pipeline.md](running-the-pipeline.md)
already works and covers only what harvesting adds.

---

## 0. What "harvest" means here — the copyright stance

**The competitor's transcript is source material a script transforms, never
material a script relays.** `harvest` never touches their video, audio or
images — Content ID strikes are on *media*, not on a differently-worded
script. What crosses over is the *topic* (their title becomes ours to cover)
and the *transcript* (fed to the scriptwriter as grounding, the same way a
Wikipedia source would be).

This is enforced in code, not left to judgment: `check_verbatim`
(`src/contentforge/script/validate.py`) rejects a generated script that sits
too close to its source, and **there is no flag to disable it** — a script
that fails the check fails the run. The topic is borrowed; the expression is
ours.

That said, `check_verbatim` guards against a copyright strike, not against a
platform's monetization review of derivative content — keep it strict and
don't route around it.

---

## 1. Install

`yt-dlp` (used to pull auto-captions) is the `[harvest]` optional extra —
research and rendering need no scraper, so it's kept out of the base install:

```bash
pip install -e ".[harvest]"
```

Captions come from the `yt-dlp` binary, invoked as a subprocess — not its
Python API.

---

## 2. Pick a channel

Harvesting only makes sense against a channel you already trust — one that
came out of research (`pipeline potentials`, the `research` skill) with a
verified verdict, not a guess. `harvest` itself does no vetting; it assumes
the channel argument is a decision you've already made.

---

## 3. `harvest` — build the plan

```bash
pipeline harvest <channel> --niche <niche> [--limit N] [--root data] [--profile P]
```

`<channel>` is an `@handle` or a `UC…` channel id. `--limit` (default 20)
caps how many recent uploads are considered. `--profile` selects a named
YouTube API credential, same as the rest of the pipeline.

For each recent upload, `harvest`:

1. Resolves the channel and its uploads via the YouTube Data API (quota is
   spent and persisted through the usual ledger).
2. Fetches the auto-caption transcript with `yt-dlp`. **A video with no
   captions is skipped** — logged to the console, not silently dropped from
   view — and does not appear in the plan at all.
3. Stages the kept transcript at
   `data/<niche>/videos/<slug>/meta/sources/reference-transcript.txt`.
4. Writes one line per kept video to
   `data/<niche>/harvest/<channel>/plan.jsonl`.

Slugs are derived from the video title and are unique by construction: a
title that slugifies to nothing (e.g. all-punctuation, or fully non-ASCII)
falls back to the video id, and collisions get a deterministic `-2`, `-3`
suffix.

`harvest` finishes by printing how many videos it kept and where the plan
landed, with a hint to review it before rendering:

```
  14 videos harvested -> data/<niche>/harvest/<channel>/plan.jsonl
  review/prune it, then: pipeline harvest-make <channel> --niche <niche>
```

### Review and prune `plan.jsonl`

**Do this before `harvest-make`.** `plan.jsonl` is one JSON object per line —
`slug`, `topic` (the source title), `video_id`, `url`, `title` — and it is
meant to be hand-edited. Delete lines for videos that don't fit the niche, or
whose transcript looked thin. `harvest-make` only renders what's still in the
file, so pruning here is how you keep a bad video out of the batch without
touching any code.

---

## 4. `harvest-make` — render the batch

```bash
pipeline harvest-make <channel> --niche <niche> [--root data] [--model flux]
```

Renders every video still listed in the (reviewed) `plan.jsonl` as one batch,
in order, through the normal `make` pipeline — same eight stages, same
`niche.toml` profile. `--model flux` swaps in the fast draft model for the
whole batch instead of the niche's default; use it to sanity-check a batch's
pacing and topics before committing to a slow final run.

Each video's script is the transcript run through the scriptwriter with the
video's title as the topic — the same transform-not-relay path described
above, not a fresh `--source` lookup.

### Batch behavior

- **Skip what's already done.** A video whose `final/video.mp4` already
  exists is skipped and marked `done` — re-running `harvest-make` is always
  safe and never re-renders a finished video.
- **One failure doesn't kill the batch.** If a single video's render fails,
  the error is recorded in `batch.json` (`status: "failed"` plus the
  exception) and the batch moves on to the next video.
- **Ctrl-C (or SIGTERM) stops gracefully.** The batch finishes the video
  currently rendering, marks it `"stopped"`, and leaves every video after it
  as `"pending"` — the same "finish the current item, then stop" behavior
  `make` uses within a single video, just at the batch level.
- **Re-running resumes.** Because finished videos are skipped, stopped or
  failed videos are simply picked up again on the next `harvest-make` call.

All of this is tracked in three files under
`data/<niche>/harvest/<channel>/`:

```
plan.jsonl          the reviewed list of videos to render
batch.json          per-video status: pending / running / done / failed / stopped
harvest-make.log    a timestamped, append-only line per video event
```

`batch.json` is written atomically (write to a `.tmp` file, then rename)
after every state change, so it's never read half-written.

---

## 5. GPU caveat — render headless or on hermes

A batch render needs a GPU that fits the image model, for every video in the
batch, one after another. On a 6 GB card that's also driving a desktop
session, both `flux` and Qwen can OOM at the `draw` stage purely from desktop
VRAM contention — this is not specific to harvesting, but a multi-video batch
makes it much more likely to hit than a single `make` run.

Render **headless** (no desktop compositor or browser holding VRAM), or on
**hermes** — launch `harvest-make` detached (`setsid pipeline harvest-make
… &`) the same way a long `make` render is launched, and poll `batch.json`
instead of a single `status.json`. See
[running-the-pipeline.md](running-the-pipeline.md) §6 for the hermes
deployment checklist; the same GPU-passthrough and memory settings apply.

---

## 6. One video, not a batch

To reword a single already-harvested (or otherwise obtained) transcript
without going through `harvest`/`harvest-make`, use `make` directly with
`--transcript-file` — see
[running-the-pipeline.md](running-the-pipeline.md) for how `make` picks a
transcript over `--source` URLs, including the auto-detect that finds a
staged `reference-transcript.txt` without any flag at all.
