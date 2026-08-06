# Harvest: channel → reworded videos (feature A) — design

**Date:** 2026-08-06
**Status:** approved, ready for implementation plan
**Depends on:** feature B (per-niche structure + `NicheConfig`) must land first — harvested videos
land under `data/<niche>/videos/<slug>/`.
**Scope:** turn a validated channel into a batch of original videos on the same topics, by
harvesting each video's topic (title) and transcript (captions), rewording the transcript in the
niche's voice, and driving the existing `make` pipeline in a resumable loop.

## Problem

Today each video is one manual `pipeline make <slug> --topic … --source URL`. To produce a
channel's worth of videos you would invoke it by hand N times, hand-gathering a topic and sources
each time. The research phase already validates *which channels are worth copying the approach of*
(`research/potentials.py`), and `youtube_api.py` can already list a channel's videos — but nothing
connects "this channel is good" to "make videos on its topics."

## Goal

1. **`harvest`** — a channel → a reviewable **plan** of (slug, topic, transcript) per video, with
   transcripts staged where `make` will find them. Prepare-only: no generation, so the operator
   prunes the plan before spending GPU time.
2. **`make --transcript-file`** — feed a local transcript as the source material; the existing
   `generate_script` **rewords** it in the niche voice and `script/validate.py::check_verbatim`
   **enforces** it is not a copy (the strike guardrail).
3. **`harvest-make`** — a **properly wired batch loop** that drives `make` over the plan: one
   normal render per entry, **skips finished videos**, **continues past a failed one** (records it),
   and is **interruptible and resumable at both levels** — between videos, and within a video
   between items (reusing `interrupt.py` + `status.json` from the pipeline hardening).

Non-goal: auto-deriving the niche profile (feature C, parked).

## Copyright stance (why this is strike-safe)

Copyright **strikes** are Content ID / manual claims on copied *audio or video* — a reworded script
in our own voice with our own art does not trigger them. The transcript is used only as **source
material to transform**, exactly what principle #5 ("Transform, never relay") and `check_verbatim`
already enforce: a generated script too close to its source is **rejected**. The video's *topic*
(title) is borrowed; the *expression* is ours. Honest residual caveat (not a strike): heavily
reused content can affect monetization review — the more the rewrite and visuals diverge, the
safer; keep `check_verbatim` strict.

## Components

### 1. Transcript fetch — `harvest/transcripts.py`
`fetch_transcript(video_id_or_url: str, runner=subprocess.run) -> str`. Shells the installed
`yt-dlp` to pull auto/uploaded captions (`--write-auto-subs --sub-lang en --skip-download
--sub-format vtt -o -` style, or download to a temp file and read), strips VTT cue timing to plain
text. `runner` is injected so it is unit-testable without network. Raises `MissingDataError` with
the video id if no captions exist (that video is skipped in the plan, not fatal to the batch).

### 2. Slug + planner — `harvest/plan.py`
- `slugify(title: str) -> str` — lowercased, alphanumerics + hyphens, deduped.
- `HarvestEntry` (frozen): `slug, topic, video_id, url, title`.
- `build_plan(client: YouTubeClient, channel: str, ledger, limit) -> list[HarvestEntry]` — resolve
  channel (handle or id) → `get_uploads_playlists` → `get_playlist_video_ids(max=limit)` →
  `get_videos` for titles. `topic = title`; `slug = slugify(title)`.
- `write_plan(entries, niche_root)` / `read_plan(niche_root, channel)` — JSONL at
  `data/<niche>/harvest/<channel>/plan.jsonl` (one entry per line; human-prunable).

### 3. `harvest` command (cli)
`pipeline harvest <channel> --niche <niche> [--limit N] [--root data]`:
- `build_plan` → `write_plan`.
- Per entry: `fetch_transcript` → stage at `data/<niche>/videos/<slug>/meta/sources/reference-transcript.txt`
  (create the run dir's `meta/sources/`). A video with no captions is logged and dropped from the
  written plan.
- Prints the plan (slug + topic) for review. **No generation.**

### 4. `make --transcript-file` (extends feature B's make)
- New arg `--transcript-file <path>` (mutually informative with `--topic`). Reads the local text
  into a `Source(url="transcript:<slug>", title=topic, text=<transcript>, retrieved_at=now)` and
  passes `[source]` to the scriptwriter, bypassing URL fetch. `generate_script(topic, [source])`
  rewords it; `check_verbatim` runs as today.
- If `--transcript-file` is omitted, `make` also auto-detects a staged
  `meta/sources/reference-transcript.txt` in the run dir (so `harvest-make` needn't pass the path
  explicitly). Explicit `--script-file` still wins and skips generation entirely.

### 5. `harvest-make` — the wired batch loop (cli)
`pipeline harvest-make <channel> --niche <niche> [--root data] [--model …]`:
- `read_plan` → for each entry **in order**:
  - If `data/<niche>/videos/<slug>/final/video.mp4` exists → **skip** (already done).
  - Else call `build_video` with the niche config + `topic=entry.topic` + the staged transcript as
    the source (via the auto-detect in §4).
  - On `interrupt.StopRequested` (Ctrl-C) → stop the whole batch cleanly (the current video already
    recorded `stopped` in its own `status.json`); re-running resumes at that video's first unfinished
    item.
  - On any other exception → record it in the batch ledger and **continue** to the next entry (one
    bad transcript must not kill the batch). The failed video's own `status.json` holds its error.
- Writes a **batch ledger** `data/<niche>/harvest/<channel>/batch.json`:
  `{slug: "done"|"failed"|"stopped"|"pending", error?}` updated after each video, plus a
  `harvest-make.log` line per video — the same durable-record pattern as `RunLog`, at the batch
  level. So a partially-run batch is legible and resuming re-runs only the not-done ones.
- `interrupt.arm()` is called once at the start so a single Ctrl-C is graceful across the batch.

## Data flow

```
research/potentials  ── operator picks a channel ──►  pipeline harvest <ch> --niche N
                                                          │  youtube_api: channel→videos→titles
                                                          │  yt-dlp: captions→transcript
                                                          ▼
                         data/N/harvest/<ch>/plan.jsonl   +   data/N/videos/<slug>/meta/sources/reference-transcript.txt
                                                          │  (operator prunes plan.jsonl)
                                                          ▼
                         pipeline harvest-make <ch> --niche N
                            for slug in plan (skip done, continue on fail, interruptible):
                               build_video(niche=N, topic, transcript-source)  →  data/N/videos/<slug>/final/video.mp4
                            batch.json + harvest-make.log record every outcome
```

## Error handling

- No captions for a video → `MissingDataError` from `fetch_transcript`; harvest logs + drops it,
  batch never sees it.
- One video failing in `harvest-make` → recorded in `batch.json`, loop continues.
- Ctrl-C → graceful stop, both levels resumable (existing `interrupt`/per-item skip + the batch
  ledger).
- Malformed plan / missing niche → loud `MissingDataError`.

## Testing

- `test_transcripts.py`: VTT → plain text stripping; injected `runner`; no-captions raises.
- `test_harvest_plan.py`: `slugify` rules; `build_plan` with a fake `YouTubeClient` yields entries;
  `write_plan`/`read_plan` round-trip.
- `test_cli.py`: `harvest` writes plan + stages transcripts (fakes for youtube + yt-dlp);
  `make --transcript-file` loads a local transcript as the source (fake scriptwriter asserts the
  Source text is the transcript); `harvest-make` loop over a 3-entry plan skips a done slug,
  continues past a failing one, and records `batch.json` (all with injected fakes — no network/GPU).
- Full suite green.

## Documentation (deliverable, per the standing rule)

- **`docs/setup/harvesting.md`** (new) — the whole workflow: pick a channel from research →
  `harvest` → review/prune `plan.jsonl` → `harvest-make`; the copyright stance; the resume/stop
  behaviour of the batch.
- **`docs/setup/running-the-pipeline.md`** — add `--transcript-file` to the `make` options and a
  pointer to harvesting.md.
- **`README.md`** — one line under "Making a video" that a channel can be harvested into a batch.
- **hermes skills** — `contentforge-video` gains a short "make a batch from a channel" note
  (`harvest` then `harvest-make`, detached + poll `batch.json`); `contentforge-render-status` learns
  to read `batch.json` for batch progress.
- **Session handoff** — note A landed and where the batch ledger lives.
- **`pyproject.toml`** — optional `[harvest]` extra declaring `yt-dlp` (the subprocess binary), and
  a note that captions come from it.

## Roadmap note

Feature **C (auto-profiling)** remains parked (see the niche-structure spec). The honest
upload-first critique still stands: the first real payoff is publishing a handful of these and
**measuring** whether reworded videos get watched — build no further generality until that signal
exists.
