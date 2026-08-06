# Multi-niche production structure (feature B) — design

**Date:** 2026-08-06
**Status:** approved, ready for implementation plan
**Scope:** turn the niche-blind, flat production layout into a per-niche structure with
per-niche configuration, so the pipeline can run more than one niche. **This is feature B
of three** (see "Roadmap" at the end for the parked C and A).

## Problem

Today video production is niche-blind:

- Runs land flat in `data/videos/<slug>/` (`run_dir_for = root / slug`), assets mixed with the
  final files (`audio/ raw/ frames/ work/` + `script.txt spec.json video.mp4 …`).
- The **style is hardcoded** as module constants tuned for one niche (Mr. Finance /
  "business-economics"): `HOUSE_STYLE` + `NEGATIVE` (`visuals/illustrate.py`), palette
  cream/teal (`visuals/palette.py`), voice reference + pace `0.80` (`runtime.py` /
  `voice/omnivoice_backend.py`), title format (`publish/metadata.py`), script voice
  (`script/generate.py`), no-music (`render/`).

So a second niche cannot exist without editing code, and there is no on-disk grouping by niche
or a single collected place for the publish-ready files.

## Goal

1. A **per-niche directory layout** grouping every video and its assets under its niche, with a
   dedicated `final/` holding only the publish-ready set.
2. A **`niche.toml`** per niche holding the full style/voice/format profile, loaded into a
   `NicheConfig` and threaded through the stages, so `make`/`publish` render in the *niche's*
   style instead of hardcoded constants.
3. **Behaviour preserved** for the existing niche: the current Mr-Finance constants become the
   first hand-authored `niche.toml` (`business-economics`), carrying the exact same style values
   so the pipeline renders in the same look (a characterisation test guards the values).

Non-goals (parked, see Roadmap): auto-deriving `niche.toml` from a channel (**C**), and
harvesting topics/transcripts into videos (**A**).

## Directory layout

```
data/
  <niche>/                        e.g. business-economics
    niche.toml                    the niche's full profile (hand-authored for now)
    videos/
      <slug>/                     e.g. laundromat
        work/                     audio/  raw/  frames/   (intermediates)
        meta/                     script.txt spec.json manifest.json status.json run.log sources/
        final/                    video.mp4 subtitles.srt subtitles.vtt metadata.json
                                  thumbnail.png published.json
```

- `run_dir_for(root, niche, slug) -> root / niche / "videos" / slug`.
- Within a run: three sub-roots — `work/` (regenerable intermediates), `meta/` (the plan +
  provenance + run state), `final/` (only the publish-ready files).
- **Filename join key is the index**, unchanged: `beat_NNN.wav` ↔ `shot_NNN.png` ↔
  `frame_NNN.png` map together by `NNN`. The per-video directory already scopes the slug, so no
  slug prefix is added to asset names.
- `published/` (a niche-level collection) is **dropped** for now — `final/` per video already
  collects the publish set; add a niche-wide index later only if needed.
- **Legacy** `data/videos/*` runs are left untouched (disposable test runs); no migration.

## `niche.toml` schema + `NicheConfig`

```toml
[niche]
name         = "business-economics"
title_format = "The Economics of Owning a {subject}"

[visual]
house_style  = "simple hand drawn line-art illustration, one single object centered, ..."
negative     = "photo, photorealistic, 3d render, ... realistic hands, ... person"
bg           = [240, 232, 216]   # cream
accent       = [38, 122, 118]    # teal
image_model  = "qwen"

[voice]
reference    = "~/.local/share/contentforge/voices/iapetus-reference.wav"
pace         = 0.80
music        = false

[script]
voice_guidance = "second-person demolition, reveal structure, our own words"
target_words   = [2500, 3200]
```

- New module `src/contentforge/niche.py`: a frozen `NicheConfig` dataclass + `load_niche(niche,
  root) -> NicheConfig`, reading `data/<niche>/niche.toml` via stdlib `tomllib`. Validates at the
  boundary (required keys present, colours are 3-int lists, pace in a sane range) and fails loud
  with a clear message on a malformed file — no silent defaults for a niche that exists.
- `~` in paths is expanded. Unknown keys are ignored (forward-compat) but logged once.

## Wiring (the real work)

The stage backends are already **injected** through `runtime.py`, which is where the hardcoded
choices live — so the change is contained: `runtime` loads the `NicheConfig` once and passes the
relevant fields into each factory, instead of the factories importing module constants.

| niche.toml field | consumed by | today's source (constant) |
|---|---|---|
| `visual.house_style`, `visual.negative` | `illustrator` → `visuals/illustrate.py` | `HOUSE_STYLE`, `NEGATIVE` |
| `visual.bg`, `visual.accent` | palette normalise + lettering | `palette.py` constants |
| `visual.image_model` | `illustrator` | `CONTENTFORGE_IMAGE_MODEL` / `DEFAULT_IMAGE_MODEL` |
| `voice.reference`, `voice.pace` | `speaker` → OmniVoice | `CONTENTFORGE_VOICE_REFERENCE`, `DEFAULT_SPEED` |
| `voice.music` | `renderer` | (implicit "no music") |
| `title_format` | `metadata_writer` → `publish/metadata.py` | title-format prompt |
| `script.voice_guidance`, `script.target_words` | `scriptwriter` → `script/generate.py` | prompt constants |

Approach: keep the module constants **as the fallback defaults** (so nothing breaks if a field is
absent), but have each factory accept the value as a parameter that `runtime` fills from
`NicheConfig`. The constants stop being the source of truth; `business-economics/niche.toml`
becomes it, carrying today's exact values so output is unchanged.

`build_video` / `run_dir_for` / the `ensure_*` stages and `RunLog` are updated to write into
`work/ meta/ final/`. `publish` reads from `final/`.

## CLI

- `make` / `publish` gain `--niche <name>`, **default `business-economics`**, so today's
  `pipeline make <slug>` keeps working unchanged. `--root` default becomes `data/`.
- `run_dir = args.root / args.niche / "videos" / args.slug`.
- `pipeline niches` (small addition): list the niches under `data/` and whether each has a valid
  `niche.toml`. (Optional, cheap; include if trivial.)

## Error handling

- Missing/malformed `niche.toml` for a named niche → loud `MissingDataError` naming the file and
  the missing key (never a silent default — a wrong-looking niche must fail, not render off-brand).
- Existing per-stage loud-failure behaviour is preserved; only the paths change.

## Testing

- `test_niche.py`: `load_niche` parses a good file; rejects a malformed one; expands `~`.
- Update `test_pipeline.py` fakes/paths to the `work/meta/final` layout; assert stages write to the
  right sub-root and `publish` reads `final/`.
- A characterisation test: `business-economics/niche.toml` reproduces the current
  `HOUSE_STYLE`/`NEGATIVE`/palette/pace/title-format values (guards the migration).
- Full suite stays green (currently 578).

## Documentation (part of this feature, not an afterthought)

Every change that a user or the hermes agent can see must land in the docs in the same plan:

- **`docs/setup/running-the-pipeline.md`** — update the run-directory listing to the
  `work/ meta/ final/` layout; add `--niche` to the `make`/`publish` examples and explain the
  default; note that `final/` is the reviewable/publish set.
- **`docs/setup/niches.md`** (new, short) — how to add a niche: create `data/<niche>/niche.toml`,
  the field-by-field schema, and that it is hand-authored for now (auto-profiling is parked, C).
- **`README.md`** — the one-paragraph run-dir / "one command" blurb reflects the niche layout.
- **hermes skills** (`~/.hermes/skills/contentforge-video`, `contentforge-render-status`) — the
  `--root`/paths and `status.json` location referenced there move under `…/<niche>/videos/<slug>/`;
  update the skills so the agent reads the right paths.
- **Session handoff** — a short note that B landed and where the layout/config now live.

The implementation plan must include these doc edits as explicit steps, and the plan for **A**
(harvest) will carry its own documentation deliverable the same way.

## Roadmap — parked, documented so it can be resumed

Decided this session (operator): build **B (this) + A (harvest)**; **skip C (auto-profiling)** for
now; document the rest. Honest sequencing critique also recorded so the trade-off isn't relitigated.

- **C — niche auto-profiling (parked).** Instead of hand-authoring `niche.toml`, derive it from a
  chosen reference channel: title format ← its titles; `pace` ← words ÷ duration of a video;
  palette ← sampled frames; `house_style`/`voice_guidance` ← LLM description of frames/transcripts.
  This automates what was done **by hand** for Mr. Finance. **Risk (why parked):** an auto-derived
  profile will likely be *worse* than a human's hand-tune until the pattern is clear over 2-3
  niches; hand-authoring `niche.toml` (copy + tweak) is cheaper and better until then.
- **A — harvest (next spec).** Validated channel → list its videos (`youtube_api` already can) →
  per video: topic (from title) + transcript (captions) → `generate_script` **rewords** it in the
  niche's voice, with `script/validate.py::check_verbatim` enforcing it is not a copy → land as a
  video under the niche's `videos/`. New build = transcript fetch + the harvest/batch loop.
- **Strategic note (the honest critique).** The project's own research concluded *"the next
  evidence has to come from our own uploads."* Zero videos are published yet. The highest-value
  path is: make a handful of real videos in the existing niche, **publish, and measure**, before
  investing further in multi-niche generality. B is cheap foundation; C especially should wait
  until the content loop is proven.
