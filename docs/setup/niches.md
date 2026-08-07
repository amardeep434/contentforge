# Niches

A **niche** is one video style: a subject domain, a house illustration look, a
voice, a title format and a narration prompt, all bundled so `make` renders
consistently for that channel. The pipeline supports more than one niche at
once — each lives in its own `data/<niche>/` directory with its own
`niche.toml`, and every run directory is scoped under it:
`data/<niche>/videos/<slug>/`. See
[running-the-pipeline.md](running-the-pipeline.md) for the full run-directory
layout.

`--niche` selects one on `make` and `publish`; it defaults to
`business-economics`, the first niche, which carries the original Mr-Finance
constants (unchanged from before niches existed).

```bash
pipeline make my-video --script-file script.txt --niche business-economics
pipeline make my-video --script-file script.txt --niche art-history
```

An explicit `--model` (or `CONTENTFORGE_IMAGE_MODEL`) still overrides the
niche's `image_model` for a quick draft pass — it does not change which niche
you're rendering into.

## Niches are hand-authored

There is no auto-detection. A named niche with a missing or malformed
`niche.toml` fails loudly with `MissingDataError` rather than guessing or
falling back to defaults — the profile is loaded and validated by
`contentforge.niche.load_niche`, field by field, so a typo or missing key is
caught before anything renders.

Auto-profiling a niche from a reference channel (deriving `title_format`,
palette, pace and house style automatically) is a parked idea — see the
niche-structure spec. It is riskier than hand-authoring until the pattern is
clear across two or three niches, so for now every niche is written by hand.

## Adding a niche

```bash
mkdir -p data/<niche>
```

then write `data/<niche>/niche.toml`. There is no scaffolding command; copy an
existing `niche.toml` (e.g. `data/business-economics/niche.toml`) and edit it.

## `niche.toml` schema

Parsed with the Python standard library `tomllib` into a `NicheConfig`
(`src/contentforge/niche.py`). Every field below is required — there are no
defaults, so a section or key left out fails loudly at load time naming
exactly what is missing.

### `[niche]`

| Field | Type | Meaning |
|---|---|---|
| `name` | string | The niche's own name, e.g. `"business-economics"`. |
| `title_format` | string | Video title template with a `{subject}` placeholder, e.g. `"The Economics of Owning a {subject}"`. |

### `[visual]`

| Field | Type | Meaning |
|---|---|---|
| `house_style` | string | Positive image-generation prompt describing the illustration look. |
| `negative` | string | Negative prompt — what the image model must avoid drawing. |
| `bg` | `[r, g, b]` (three ints) | Background colour, e.g. `[240, 232, 216]`. |
| `accent` | `[r, g, b]` (three ints) | Accent colour used in lettering/captions, e.g. `[38, 122, 118]`. |
| `image_model` | string | Default image model for this niche's finals, e.g. `"qwen"`. |

### `[voice]`

| Field | Type | Meaning |
|---|---|---|
| `reference` | path (string, `~` allowed) | Path to the voice reference wav, e.g. `"~/.local/share/contentforge/voices/iapetus-reference.wav"`. |
| `pace` | float | Narration speaking rate, e.g. `0.80`. |
| `music` | bool | Whether this niche's renders include background music. |

### `[script]`

| Field | Type | Meaning |
|---|---|---|
| `target_words` | `[low, high]` (two ints) | Target script length in words, e.g. `[2500, 3200]`. |
| `system` | string (usually a triple-quoted multi-line string) | The full narration system prompt — voice, rules, tone — sent to the LLM when generating the script. |

## Example: `data/business-economics/niche.toml`

```toml
[niche]
name = "business-economics"
title_format = "The Economics of Owning a {subject}"

[visual]
house_style = "simple hand drawn line-art illustration, one single object centered, bold black ink outlines, flat plain cream off-white background, minimal, lots of empty space, muted colours, clean confident linework, no shading, no gradient, no texture, no text, not 3d, not a photograph"
negative = "photo, photorealistic, 3d render, gradient, blurry, watermark, signature, label, text, letters, words, numbers, digits, dial, gauge, clock, cluttered, busy, multiple objects, frame border, grain, noise, realistic hand, hands, fingers, extra fingers, deformed hands, mutated hands, realistic face, detailed anatomy, person"
bg = [240, 232, 216]
accent = [38, 122, 118]
image_model = "qwen"

[voice]
reference = "~/.local/share/contentforge/voices/iapetus-reference.wav"
pace = 0.80
music = false

[script]
target_words = [2500, 3200]
system = """You write long-form business-explainer narration, spoken by one
confident, faintly amused narrator talking directly to the viewer as "you".
...
"""
```

(Truncated here — see the real file for the full narration prompt.)
