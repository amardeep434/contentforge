# Multi-niche production structure (feature B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group video production per niche on disk (`data/<niche>/videos/<slug>/{work,meta,final}`) and drive each niche's look/voice/format from a hand-authored `niche.toml`, instead of niche-blind flat dirs and hardcoded constants.

**Architecture:** A new `NicheConfig` (loaded from `data/<niche>/niche.toml`) is resolved once in `cli.py` and passed into `build_video` and the already-injected stage factories in `runtime.py`. The existing module constants stay as fallback defaults. The run-directory sub-roots (`work/`, `meta/`, `final/`) are introduced by prefixing the path-name constants in `pipeline.py`. The current Mr-Finance constants become the first niche, `business-economics/niche.toml`, so behaviour is preserved.

**Tech Stack:** Python 3.13, stdlib `tomllib`, pytest. No new dependencies.

## Global Constraints

- No new runtime dependency — `niche.toml` is parsed with stdlib `tomllib` (open the file in **binary** mode: `path.open("rb")`).
- Every backend stays **injected** through `runtime.py` / passed into `build_video`; stages never import niche values directly. Module constants remain as **fallback defaults only** (a factory called with `niche=None` behaves exactly as today).
- Immutable data: `NicheConfig` is a frozen dataclass; no in-place mutation of module globals.
- Fail loud at the boundary: a named niche with a missing/malformed `niche.toml` raises `MissingDataError` naming the file and the bad field — never a silent default.
- Back-compat: `--niche` defaults to `business-economics`; existing `pipeline make <slug>` keeps working. Legacy `data/videos/*` runs are left untouched (no migration).
- Filename join key stays the zero-padded index: `beat_NNN.wav` ↔ `shot_NNN.png` ↔ `frame_NNN.png`.
- Docs are a deliverable (Task 6), not optional.
- Run the suite after every task: `cd /home/amardeep/Projects/contentforge && PYTHONPATH=src .venv/bin/python -m pytest -q`. It is green at 578 before this plan.
- Work on the branch `feat/niche-structure` (already checked out).

---

## File Structure

- **Create** `src/contentforge/niche.py` — `NicheConfig` + `load_niche`.
- **Create** `data/business-economics/niche.toml` — the first niche, current values.
- **Create** `tests/test_niche.py`.
- **Create** `docs/setup/niches.md`.
- **Modify** `src/contentforge/pipeline.py` — path-name constants → sub-root prefixes; parent `mkdir`s; `run_dir_for`; thread `background`/`accent` into `ensure_frames`/`letter_frame`.
- **Modify** `src/contentforge/runtime.py` — factories accept `niche`.
- **Modify** `src/contentforge/visuals/illustrate.py` — `illustrate` accepts `house_style`.
- **Modify** `src/contentforge/visuals/gguf_backends.py` — `load_pipeline_and_generate` accepts `negative`.
- **Modify** `src/contentforge/visuals/palette.py` — `normalise` accepts `background`.
- **Modify** `src/contentforge/visuals/caption.py` — `chapter_label` accepts `colour`.
- **Modify** `src/contentforge/voice/omnivoice_backend.py` — `_GpuSpeaker` path already in runtime; add `speed` passthrough.
- **Modify** `src/contentforge/publish/metadata.py` — `generate_metadata` accepts `title_format`.
- **Modify** `src/contentforge/script/generate.py` — `generate_script` accepts `system`/`target_words`.
- **Modify** `src/contentforge/cli.py` — `--niche`; niche-scoped `run_dir`; load `NicheConfig`; read from `final/`.
- **Modify** docs (Task 6).

---

## Task 1: NicheConfig loader + first niche.toml

**Files:**
- Create: `src/contentforge/niche.py`
- Create: `data/business-economics/niche.toml`
- Test: `tests/test_niche.py`

**Interfaces:**
- Produces: `NicheConfig` (frozen dataclass) with fields
  `name: str`, `title_format: str`, `house_style: str`, `negative: str`,
  `bg: tuple[int,int,int]`, `accent: tuple[int,int,int]`, `image_model: str`,
  `voice_reference: Path`, `pace: float`, `music: bool`,
  `script_system: str`, `target_words: tuple[int,int]`.
- Produces: `load_niche(niche: str, root: Path) -> NicheConfig` reading `root/niche/niche.toml`.

- [ ] **Step 1: Write the failing test** — create `tests/test_niche.py`:

```python
from pathlib import Path

import pytest

from contentforge.niche import NicheConfig, load_niche
from contentforge.errors import MissingDataError

GOOD = """
[niche]
name = "demo"
title_format = "The Economics of Owning a {subject}"
[visual]
house_style = "line art"
negative = "photo"
bg = [240, 232, 216]
accent = [38, 122, 118]
image_model = "qwen"
[voice]
reference = "~/ref.wav"
pace = 0.80
music = false
[script]
system = "You write narration."
target_words = [2500, 3200]
"""

def _write(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True)
    (d / "niche.toml").write_text(text)
    return tmp_path

def test_loads_a_full_profile(tmp_path):
    cfg = load_niche("demo", _write(tmp_path, "demo", GOOD))
    assert cfg.name == "demo"
    assert cfg.title_format == "The Economics of Owning a {subject}"
    assert cfg.bg == (240, 232, 216)
    assert cfg.accent == (38, 122, 118)
    assert cfg.image_model == "qwen"
    assert cfg.pace == 0.80
    assert cfg.music is False
    assert cfg.target_words == (2500, 3200)
    assert cfg.voice_reference == Path("~/ref.wav").expanduser()
    assert cfg.script_system == "You write narration."

def test_missing_file_raises_with_path(tmp_path):
    with pytest.raises(MissingDataError, match="niche.toml"):
        load_niche("nope", tmp_path)

def test_malformed_missing_key_raises_naming_the_field(tmp_path):
    bad = GOOD.replace('image_model = "qwen"', "")
    with pytest.raises(MissingDataError, match="image_model"):
        load_niche("demo", _write(tmp_path, "demo", bad))

def test_bad_colour_raises(tmp_path):
    bad = GOOD.replace("bg = [240, 232, 216]", "bg = [240, 232]")
    with pytest.raises(MissingDataError, match="bg"):
        load_niche("demo", _write(tmp_path, "demo", bad))
```

- [ ] **Step 2: Run, verify fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_niche.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.niche'`.

- [ ] **Step 3: Write `src/contentforge/niche.py`** (exact content):

```python
"""Per-niche production profile, loaded from data/<niche>/niche.toml.

One niche = one look, voice and title format. The profile is hand-authored for
now (auto-deriving it from a reference channel is parked - see the niche-structure
spec). Values are validated at load so a wrong-looking niche fails loudly rather
than rendering off-brand.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from contentforge.errors import MissingDataError

NICHE_FILE = "niche.toml"


@dataclass(frozen=True)
class NicheConfig:
    name: str
    title_format: str
    house_style: str
    negative: str
    bg: tuple[int, int, int]
    accent: tuple[int, int, int]
    image_model: str
    voice_reference: Path
    pace: float
    music: bool
    script_system: str
    target_words: tuple[int, int]


def _require(table: dict, section: str, key: str, path: Path):
    if section not in table or key not in table[section]:
        raise MissingDataError(
            f"{path}: missing [{section}].{key} - a niche profile must set it"
        )
    return table[section][key]


def _colour(value, label: str, path: Path) -> tuple[int, int, int]:
    if not (isinstance(value, list) and len(value) == 3
            and all(isinstance(c, int) for c in value)):
        raise MissingDataError(f"{path}: {label} must be three integers [r, g, b]")
    return (value[0], value[1], value[2])


def load_niche(niche: str, root: Path) -> NicheConfig:
    path = Path(root) / niche / NICHE_FILE
    if not path.exists():
        raise MissingDataError(
            f"no niche.toml at {path}; create it (see docs/setup/niches.md)"
        )
    with path.open("rb") as handle:
        table = tomllib.load(handle)

    words = _require(table, "script", "target_words", path)
    if not (isinstance(words, list) and len(words) == 2):
        raise MissingDataError(f"{path}: [script].target_words must be [low, high]")

    return NicheConfig(
        name=_require(table, "niche", "name", path),
        title_format=_require(table, "niche", "title_format", path),
        house_style=_require(table, "visual", "house_style", path),
        negative=_require(table, "visual", "negative", path),
        bg=_colour(_require(table, "visual", "bg", path), "[visual].bg", path),
        accent=_colour(_require(table, "visual", "accent", path), "[visual].accent", path),
        image_model=_require(table, "visual", "image_model", path),
        voice_reference=Path(_require(table, "voice", "reference", path)).expanduser(),
        pace=float(_require(table, "voice", "pace", path)),
        music=bool(_require(table, "voice", "music", path)),
        script_system=_require(table, "script", "system", path),
        target_words=(int(words[0]), int(words[1])),
    )
```

- [ ] **Step 4: Write `data/business-economics/niche.toml`** with the exact current values. Create the dir first (`mkdir -p data/business-economics`). Use this literal content — the multi-line strings are copied verbatim from `visuals/illustrate.py` (HOUSE_STYLE, NEGATIVE) and `script/generate.py` (the SYSTEM prompt):

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

Voice, all mandatory:
- Second person. Talk to the viewer. "You walk in, you see the rows of machines,
  and you assume..." Never "I", never "we", never "in this video".
- Open on a reframe: state what the subject REALLY is, against what it looks
  like, in the first two sentences. Earn the rest of the video from that.
- One idea per sentence, plain spoken English, the rhythm of someone explaining
  something they find quietly funny. Short sentences. Concrete numbers.
- Use a running metaphor where it clarifies, never as decoration.
- Reveal, do not list. Each section turns over one more rock.

Rules, all mandatory:
- Every factual claim must trace to a provided source and carry an inline marker
  like [1] naming it. Markers are stripped before narration; write them anyway.
- Never reproduce source wording. Rewrite everything.
- No fabricated authority. Never "I have studied", "in my experience", "experts
  agree". The narrator explains; it never credentials itself.
- Write only the spoken words. No headings, no stage directions, no timestamps,
  no "welcome back", no "don't forget to subscribe".
"""
```

**Verify the pasted values match source** before continuing (they must be byte-identical so behaviour is preserved):

```bash
grep -n "simple hand drawn line-art" src/contentforge/visuals/illustrate.py
grep -n "photo, photorealistic, 3d render" src/contentforge/visuals/illustrate.py
grep -n "You write long-form business-explainer" src/contentforge/script/generate.py
```

- [ ] **Step 5: Run tests, verify pass**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_niche.py -q` → PASS (4).

- [ ] **Step 6: Commit**

```bash
git add src/contentforge/niche.py tests/test_niche.py data/business-economics/niche.toml
git commit -m "feat: NicheConfig loader + first niche.toml (business-economics)"
```

---

## Task 2: Per-niche run directory (work / meta / final)

**Approach (do it the lazy-correct way):** the run-dir sub-roots are introduced by **prefixing the existing path-name constants** in `pipeline.py`, so every `run_dir / NAME` expression resolves under the right sub-root with no per-call-site surgery. `Path("run") / "meta/spec.json"` yields `run/meta/spec.json`. The only extra work is creating the sub-dir before each **direct file write** (`write_text`/`write_bytes`/`compose`), because those do not create parents.

**Files:**
- Modify: `src/contentforge/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `run_dir_for(root: Path, niche: str, slug: str) -> Path` = `root / niche / "videos" / slug`.
- Produces: artefacts under `meta/` (script, spec, manifest, status, run.log, sources.json), `final/` (video, subtitles, metadata, thumbnail, published.json), `work/` (audio, raw, frames, ffmpeg scratch).

- [ ] **Step 1: Write the failing test** — append to `tests/test_pipeline.py`:

```python
def test_run_dir_is_grouped_by_niche(tmp_path):
    from contentforge.pipeline import run_dir_for
    assert run_dir_for(tmp_path, "biz", "laundromat") == tmp_path / "biz" / "videos" / "laundromat"

def test_build_writes_into_work_meta_final(tmp_path):
    fakes = Fakes()
    run = tmp_path / "run"
    build(run, fakes)                      # existing `build(run_dir, fakes)` helper
    assert (run / "meta" / "spec.json").exists()
    assert (run / "meta" / "status.json").exists()
    assert (run / "meta" / "manifest.json").exists()
    assert (run / "work" / "audio").is_dir()
    assert (run / "work" / "raw").is_dir()
    assert (run / "final" / "video.mp4").exists()
    assert (run / "final" / "subtitles.srt").exists()
```

- [ ] **Step 2: Run, verify fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py -k "niche or work_meta_final" -q` → FAIL.

- [ ] **Step 3: Edit `pipeline.py` — constants.** Replace the constant block (lines 39-51) with:

```python
# Artefact paths, each already prefixed with its run-dir sub-root, so
# `run_dir / NAME` lands in work/ meta/ or final/ with no per-site path surgery.
SCRIPT_NAME = "meta/script.txt"
SPEC_NAME = "meta/spec.json"
MANIFEST_NAME = "meta/manifest.json"
STATUS_NAME = "meta/status.json"
RUNLOG_NAME = "meta/run.log"
METADATA_NAME = "final/metadata.json"
THUMBNAIL_NAME = "final/thumbnail.png"
VIDEO_NAME = "final/video.mp4"

AUDIO_DIR = "work/audio"
RAW_DIR = "work/raw"
FRAME_DIR = "work/frames"
WORK_DIR = "work/ffmpeg"
```

And update `SOURCES_NAME` (line 151) and the subtitles constants (lines 408-409):

```python
SOURCES_NAME = "meta/sources.json"
```
```python
SUBS_SRT = "final/subtitles.srt"
SUBS_VTT = "final/subtitles.vtt"
```

- [ ] **Step 4: Edit `pipeline.py` — `run_dir_for`** (line 145):

```python
def run_dir_for(root: Path, niche: str, slug: str) -> Path:
    return root / niche / "videos" / slug
```

- [ ] **Step 5: Edit `pipeline.py` — add parent `mkdir` at every direct write site.** `mkdir(parents=True, exist_ok=True)` on the file's parent before writing. Make these exact changes:

  - `load_or_write_script` (line 158): replace `run_dir.mkdir(parents=True, exist_ok=True)` with `path.parent.mkdir(parents=True, exist_ok=True)`.
  - `ensure_script` generated branch (line 196): replace `run_dir.mkdir(parents=True, exist_ok=True)` with `path.parent.mkdir(parents=True, exist_ok=True)`.
  - `ensure_spec` (line 261): replace `run_dir.mkdir(parents=True, exist_ok=True)` with `path.parent.mkdir(parents=True, exist_ok=True)`.
  - `RunLog.__init__` (after line 84, before `self._flush()`): add
    `self._status_path.parent.mkdir(parents=True, exist_ok=True)`.
  - `write_subtitles` (line 422, before the two writes): add
    `(run_dir / "final").mkdir(parents=True, exist_ok=True)`.
  - `ensure_metadata` (before `path.write_text` at line 484): add
    `path.parent.mkdir(parents=True, exist_ok=True)`.
  - `ensure_thumbnail` (before `thumbnail.compose` at line 498): add
    `path.parent.mkdir(parents=True, exist_ok=True)`.
  - `ensure_video` (before `renderer(...)` at line 434): add
    `out_path.parent.mkdir(parents=True, exist_ok=True)`.
  - `write_manifest` (before `path.write_text` at line 612): add
    `path.parent.mkdir(parents=True, exist_ok=True)`.
  - `clean_run` (line 642, before the final `write_text`): add
    `(run_dir / SCRIPT_NAME).parent.mkdir(parents=True, exist_ok=True)`.

  (`ensure_audio`/`ensure_illustrations`/`ensure_frames` already call `out_dir.mkdir(parents=True, exist_ok=True)`, and `parents=True` creates `work/audio` etc. — no change needed there. The ffmpeg `WORK_DIR` scratch is created by the renderer.)

- [ ] **Step 6: Update existing pipeline-test path assertions.** In `tests/test_pipeline.py`, change any assertion referencing old flat paths to the new sub-roots (`run/spec.json` → `run/meta/spec.json`, `run/status.json` → `run/meta/status.json`, `run/audio` → `run/work/audio`, `run/video.mp4` → `run/final/video.mp4`, `run/subtitles.srt` → `run/final/subtitles.srt`, `run/metadata.json` → `run/final/metadata.json`, `run/run.log` → `run/meta/run.log`, `run/manifest.json` → `run/meta/manifest.json`). Search first: `grep -nE "run.*/(spec|status|audio|video|subtitles|metadata|manifest|run\.log|script\.txt|thumbnail)" tests/test_pipeline.py`.

- [ ] **Step 7: Run the full suite, verify green**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q` → PASS.

- [ ] **Step 8: Commit**

```bash
git add src/contentforge/pipeline.py tests/test_pipeline.py
git commit -m "feat: per-niche run dir with work/meta/final sub-roots"
```

---

## Task 3: Thread NicheConfig through the stage factories

**Files:**
- Modify: `runtime.py`, `visuals/illustrate.py`, `visuals/gguf_backends.py`, `voice/omnivoice_backend.py`, `publish/metadata.py`, `script/generate.py`
- Test: `tests/test_runtime.py` (create), existing tests stay green.

**Wiring (verified file:line → what carries it):**

| niche field | flows via | current source |
|---|---|---|
| `house_style` | `runtime.illustrator` → `illustrate(house_style=…)` → `build_prompt(style=…)` | `illustrate.py:74 HOUSE_STYLE`, used at `illustrate.py:201` |
| `negative` | `runtime.illustrator` → `gguf_backends.load_pipeline_and_generate(negative=…)` | `gguf_backends.py:164 NEGATIVE`; also `illustrate.py:186` default path |
| `image_model` | `runtime.illustrator(niche)` → `name = niche.image_model` | `runtime.py:228` `DEFAULT_IMAGE_MODEL` |
| `voice_reference`, `pace` | `runtime.speaker(niche)` → `_GpuSpeaker(ov, reference, speed=pace)` → `ov.synthesise(speed=…)` | `runtime.py:183-184`; `omnivoice_backend.py:85 DEFAULT_SPEED=0.80` |
| `title_format` | `runtime.metadata_writer(niche)` → `generate_metadata(title_format=…)` | `publish/metadata.py:36 SYSTEM` |
| `script_system`, `target_words` | `runtime.scriptwriter(…, niche=…)` → `generate_script(system=…, target_words=…)` | `script/generate.py:SYSTEM`, `TARGET_WORDS_LOW/HIGH` |
| `bg`, `accent` | Task 3b (pipeline-internal, not a factory) | `palette.py:REFERENCE_BACKGROUND`, `caption.py:35 ACCENT` |

- [ ] **Step 1: Write the failing test** — `tests/test_runtime.py`:

```python
from pathlib import Path
from contentforge.niche import NicheConfig

def _cfg(**over):
    base = dict(name="n", title_format="T {subject}", house_style="HS", negative="NEG",
                bg=(1, 2, 3), accent=(4, 5, 6), image_model="flux",
                voice_reference=Path("/ref.wav"), pace=0.7, music=False,
                script_system="SYS", target_words=(100, 200))
    base.update(over)
    return NicheConfig(**base)

def test_illustrator_accepts_a_niche(monkeypatch):
    from contentforge import runtime
    captured = {}
    def fake_load(name, w=768, h=432, negative=None):
        captured["name"] = name
        captured["negative"] = negative
        return object(), (lambda p, path, seed: path), (lambda: None)
    monkeypatch.setattr("contentforge.visuals.gguf_backends.load_pipeline_and_generate", fake_load)
    monkeypatch.setattr("contentforge.visuals.illustrate.illustrate", lambda subjects, out_dir, **k: [])
    draw = runtime.illustrator(niche=_cfg(image_model="flux", negative="NEG"))
    draw(["a fan"], Path("/tmp"))          # triggers _prepare
    assert captured["name"] == "flux"      # image_model from the niche
    assert captured["negative"] == "NEG"   # negative from the niche

def test_speaker_uses_niche_reference_and_pace(monkeypatch):
    from contentforge import runtime
    cfg = _cfg(voice_reference=Path("/my/ref.wav"), pace=0.9)
    spk = runtime.speaker(niche=cfg)
    assert spk._reference == Path("/my/ref.wav")
    assert spk._speed == 0.9
```

- [ ] **Step 2: Run, verify fail** — `illustrator()`/`speaker()` have no `niche` param.

- [ ] **Step 3: Implement the threads.**

`visuals/illustrate.py` — give `illustrate` a `house_style` param and pass it to `build_prompt`:
- signature (line 157-165): add `house_style: str = HOUSE_STYLE,` (e.g. after `model: str = DEFAULT_MODEL,`).
- line 201: change `prompt = build_prompt(subject)` → `prompt = build_prompt(subject, style=house_style)`.

`visuals/gguf_backends.py` — give the loader a `negative` param used by the generate closure:
- signature `def load_pipeline_and_generate(name, width=768, height=432):` → add `negative: str = NEGATIVE,` (import `NEGATIVE` is already at module top from `illustrate`).
- line 164: change `kwargs["negative_prompt"] = NEGATIVE` → `kwargs["negative_prompt"] = negative`.

`voice/omnivoice_backend.py` — nothing to change here; `_GpuSpeaker` lives in `runtime.py` and already calls `ov.synthesise(...)` which takes `speed=DEFAULT_SPEED`. We add the `speed` passthrough in `runtime.py` (below).

`publish/metadata.py` — make the title format a parameter:
- `generate_metadata(client, script, sources=None)` → `generate_metadata(client, script, sources=None, title_format=None)`.
- Inside, if `title_format` is given, replace the hardcoded pattern in the `SYSTEM` prompt before use. The pattern lives in `SYSTEM` (line 36: `Titles follow "The Economics of Owning a [X]"...`). Simplest exact change: build the prompt as `system = SYSTEM if title_format is None else SYSTEM.replace('The Economics of Owning a [X]', title_format.replace('{subject}', '[X]'))` and pass `system` to `client.complete(...)` at line 168 instead of `SYSTEM`.

`script/generate.py` — make the system prompt and word target parameters:
- `generate_script(client, topic, sources, shape, ...)` (line 77) → add `system: str = SYSTEM, target_words: tuple[int, int] = (TARGET_WORDS_LOW, TARGET_WORDS_HIGH),`.
- Inside, use `system` wherever `SYSTEM` was passed to the client, and use `target_words[0]`/`target_words[1]` in the f-string at line 91 (currently `{TARGET_WORDS_LOW}-{TARGET_WORDS_HIGH}`).

`runtime.py` — factories accept `niche` and fill from it:
- `illustrator(model=None, width=None, height=None)` → `illustrator(niche=None, model=None, width=None, height=None)`. At line 228 set `name = model or (niche.image_model if niche else None) or os.environ.get(ENV_IMAGE_MODEL, DEFAULT_IMAGE_MODEL)`. In `_prepare` (line 240), pass `negative` to the gguf loader: `gguf_backends.load_pipeline_and_generate(name, w, h, negative=niche.negative if niche else NEGATIVE)` — import `NEGATIVE` at the top of the function alongside the existing `from contentforge.visuals.illustrate import illustrate, load_pipeline` → add `NEGATIVE`. In `draw` (line 250), pass `house_style=niche.house_style if niche else HOUSE_STYLE` into `illustrate(...)` (also import `HOUSE_STYLE`).
- `_GpuSpeaker.__init__(self, backend, reference)` → add `speed: float = None`; store `self._speed = speed`; in `__call__` (line 144) pass `speed=self._speed if self._speed is not None else self._backend.DEFAULT_SPEED` to `self._backend.synthesise(...)`.
- `speaker(backend=None, voice=None)` → `speaker(niche=None, backend=None, voice=None)`. In the omnivoice branch (line 183): `reference = niche.voice_reference if niche else Path(os.environ.get(ENV_VOICE_REFERENCE, str(ov.DEFAULT_REFERENCE)))`; `return _GpuSpeaker(ov, reference, speed=niche.pace if niche else None)`.
- `metadata_writer(client=None)` → `metadata_writer(niche=None, client=None)`; return `lambda script, sources=None: generate_metadata(resolved, script, sources, title_format=niche.title_format if niche else None)`.
- `scriptwriter(topic, source_urls, client=None)` → `scriptwriter(topic, source_urls, niche=None, client=None)`; inside `write`, call `generate_script(resolved, topic, sources, choose_shape(topic), system=niche.script_system if niche else generate.SYSTEM, target_words=niche.target_words if niche else (generate.TARGET_WORDS_LOW, generate.TARGET_WORDS_HIGH))` — the `from contentforge.script.generate import ...` line already imports `choose_shape, generate_script`; add `SYSTEM as _SYSTEM, TARGET_WORDS_LOW, TARGET_WORDS_HIGH` or reference them via the module.

- [ ] **Step 4: Run the full suite, verify green.**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q` → PASS (578 + new).

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/runtime.py src/contentforge/visuals/illustrate.py \
        src/contentforge/visuals/gguf_backends.py src/contentforge/publish/metadata.py \
        src/contentforge/script/generate.py tests/test_runtime.py
git commit -m "feat: thread NicheConfig through the stage factories"
```

---

## Task 3b: Thread bg + accent through the letter stage

`bg` (background) and `accent` are used inside `pipeline.py`'s letter stage, not in an injected factory, so they thread through `build_video` → `ensure_frames` → `palette.normalise` / `letter_frame` → `caption.chapter_label`.

**Files:** `pipeline.py`, `visuals/palette.py`, `visuals/caption.py`; test in `tests/test_pipeline.py`.

- [ ] **Step 1: Write the failing test** (extend `tests/test_pipeline.py`): assert `palette.normalise` and `caption.chapter_label` accept the new params.

```python
def test_normalise_accepts_a_background(tmp_path):
    from PIL import Image
    from contentforge.visuals import palette
    p = tmp_path / "x.png"; Image.new("RGB", (8, 8), (10, 10, 10)).save(p)
    palette.normalise(p, background=(1, 2, 3))   # must not raise; uses given bg

def test_chapter_label_accepts_a_colour():
    from contentforge.visuals import caption
    block = caption.chapter_label((1920, 1080), 2, colour=(4, 5, 6))
    assert block is not None
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement.**
- `palette.py` `normalise(source, destination=None)` → add `background: tuple[int, int, int] = REFERENCE_BACKGROUND`; at line 37 use `fill=background` instead of `fill=REFERENCE_BACKGROUND`.
- `caption.py` `chapter_label(frame_size, number, ...)` (line 70) → add `colour: tuple[int, int, int] = ACCENT`; at line 79 use `colour=colour` instead of `colour=ACCENT`.
- `pipeline.py`:
  - `ensure_frames(run_dir, specs, raws, upscaler, force=False)` → add `background=None, accent=None`. At line 354 change `palette.normalise(target)` → `palette.normalise(target, background=background or palette.REFERENCE_BACKGROUND)`. Change `letter_frame(target, spec)` (line 357) → `letter_frame(target, spec, accent=accent)`.
  - `letter_frame(frame_path, spec)` → add `accent=None`. At line 381 change `caption.chapter_label(frame_size, spec.chapter)` → `caption.chapter_label(frame_size, spec.chapter, colour=accent or caption.ACCENT)`.
  - `build_video(...)` → add `niche=None` param. In the `letter` stage lambda (line 574) pass `background=niche.bg if niche else None, accent=niche.accent if niche else None` into `ensure_frames`.

- [ ] **Step 4: Run full suite, verify green.**

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/pipeline.py src/contentforge/visuals/palette.py src/contentforge/visuals/caption.py tests/test_pipeline.py
git commit -m "feat: thread niche bg/accent through the letter stage"
```

---

## Task 4: CLI --niche wiring

**Files:** `src/contentforge/cli.py`; test `tests/test_cli.py`.

- [ ] **Step 1: Write the failing test** — real, runnable, against `make --dry-run` (no models load):

```python
def test_make_uses_niche_run_dir_and_loads_config(tmp_path):
    from contentforge.cli import main
    # a minimal niche.toml under the tmp data root
    niche_dir = tmp_path / "biz"
    niche_dir.mkdir(parents=True)
    (niche_dir / "niche.toml").write_text(
        '[niche]\nname="biz"\ntitle_format="T {subject}"\n'
        '[visual]\nhouse_style="hs"\nnegative="neg"\nbg=[1,2,3]\naccent=[4,5,6]\nimage_model="qwen"\n'
        '[voice]\nreference="~/r.wav"\npace=0.8\nmusic=false\n'
        '[script]\nsystem="sys"\ntarget_words=[10,20]\n'
    )
    script = tmp_path / "s.txt"
    script.write_text("One sentence here. Two sentence here. Three here.\n")
    rc = main(["make", "smoke", "--niche", "biz", "--root", str(tmp_path),
               "--script-file", str(script), "--dry-run"])
    assert rc == 0
    # dry-run wrote the script into the niche-scoped run dir
    assert (tmp_path / "biz" / "videos" / "smoke" / "meta" / "script.txt").exists()
```

- [ ] **Step 2: Run, verify fail** (`--niche` unknown).

- [ ] **Step 3: Implement in `cli.py`.**
- On the `make` subparser: `make.add_argument("--niche", default="business-economics")`. Change `make.add_argument("--root", type=Path, default=Path("data/videos"))` → `default=Path("data")`.
- On the `publish` subparser: add the identical `--niche` and change its `--root` default the same way.
- `make` handler: change `run_dir = args.root / args.slug` → `run_dir = args.root / args.niche / "videos" / args.slug` (or import and use `run_dir_for(args.root, args.niche, args.slug)`). After it, load the niche: `from contentforge.niche import load_niche; cfg = load_niche(args.niche, args.root)`. Pass it through: `writer = runtime.scriptwriter(args.topic, args.source, niche=cfg) if args.topic else None`; `speak=runtime.speaker(niche=cfg)`; `illustrator=runtime.illustrator(niche=cfg, model=args.model)` (explicit `--model` still overrides for a draft); `metadata_writer=runtime.metadata_writer(niche=cfg)`; and `build_video(..., niche=cfg, ...)`. Update the two closing `print`s to include `--niche {args.niche}` in the resume/publish hints. **Note:** the `--dry-run` branch calls `ensure_script(run_dir, script, writer)` — it must use the niche-scoped `run_dir`, and it does not need `cfg` beyond building `writer`; keep `load_niche` before the dry-run branch only if `--topic` is used, else guard it so a dry-run with `--script-file` still works without a niche.toml. Simplest: load `cfg` lazily only when not dry-run, and build `writer` with `niche=None` in dry-run (dry-run does not generate). Match the test above (dry-run with `--script-file` needs no cfg).
- `publish` handler: change `run_dir = args.root / args.slug` → niche-scoped; the artefact reads (`run_dir / VIDEO_NAME`, `run_dir / METADATA_NAME`, `run_dir / THUMBNAIL_NAME`, `load_metadata(run_dir)`) already resolve under `final/` because the constants now carry the prefix — no further change.

- [ ] **Step 4: Run full suite, verify green.**

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/cli.py tests/test_cli.py
git commit -m "feat: --niche on make/publish, niche-scoped run dirs"
```

---

## Task 5: End-to-end smoke on the host

**Files:** none (verification).

- [ ] **Step 1:** Build one short video in the new layout (fast draft model, needs the GPU + services up):

```bash
cd /home/amardeep/Projects/contentforge
set -a && . ./.env 2>/dev/null; set +a
printf 'One short sentence here. Two short sentence here. Three here.\n' > /tmp/smoke.txt
.venv/bin/python -c "import sys; from contentforge.cli import main; sys.exit(main())" \
  make smoke --niche business-economics --model flux --root data --script-file /tmp/smoke.txt
```

- [ ] **Step 2:** Assert the tree: `data/business-economics/videos/smoke/{work,meta,final}` populated; `final/video.mp4`, `final/thumbnail.png` exist; `meta/status.json` shows every stage `ok`/`skipped`.
- [ ] **Step 3:** Delete the smoke run: `rm -rf data/business-economics/videos/smoke`. No commit.

---

## Task 6: Documentation

**Files:** modify `docs/setup/running-the-pipeline.md`, `README.md`; create `docs/setup/niches.md`; modify `~/.hermes/skills/contentforge-video/SKILL.md`, `~/.hermes/skills/contentforge-render-status/SKILL.md`; modify the session handoff.

- [ ] **Step 1:** `running-the-pipeline.md` — replace the "What it leaves behind" run-dir listing with the `work/meta/final` layout under `data/<niche>/videos/<slug>/`; add `--niche` to the `make`/`publish` examples and note the default `business-economics`; state `final/` is the reviewable/publish set.
- [ ] **Step 2:** Create `docs/setup/niches.md` — what a niche is; the `niche.toml` field-by-field schema (mirror `NicheConfig` from Task 1: `[niche] name,title_format` / `[visual] house_style,negative,bg,accent,image_model` / `[voice] reference,pace,music` / `[script] system,target_words`); how to add one (`mkdir data/<niche>` + write `niche.toml`); that it is hand-authored for now (auto-profiling parked).
- [ ] **Step 3:** `README.md` — the run-dir / one-command blurb reflects the niche layout (`data/<niche>/videos/<slug>/…`).
- [ ] **Step 4:** hermes skills — the run paths and `status.json` location referenced in both SKILL.md files move under `/root/videos/<niche>/videos/<slug>/…`; update the `make` example to pass `--niche` and the poll paths to `…/meta/status.json`. (These files live under `~/.hermes/skills/`, not in the repo — edit in place, do not `git add`.)
- [ ] **Step 5:** Handoff (`docs/handoff/2026-08-06-session-handoff.md`) — a short note that feature B landed, where the layout/config live, and that A (harvest) is next.
- [ ] **Step 6: Commit**

```bash
git add docs/ README.md
git commit -m "docs: multi-niche layout, niche.toml, updated skills"
```

---

## Self-Review

- **Spec coverage:** layout (Task 2), niche.toml + NicheConfig (Task 1), factory wiring (Task 3), pipeline-internal bg/accent (Task 3b), CLI + back-compat (Task 4), business-economics carries current values (Task 1 Step 4 + the verify greps + the green suite as the characterisation guard), error handling (Task 1), docs (Task 6). Roadmap C/A parked in the spec. Covered.
- **Placeholder scan:** none — every code step has real code; every edit step names the exact file, line, old text and new text. The one judgement call (metadata `title_format` via `SYSTEM.replace`) is spelled out with the exact strings.
- **Type consistency:** `NicheConfig` fields used in Tasks 3/3b/4 match Task 1 exactly (`image_model`, `voice_reference`, `pace`, `script_system`, `target_words`, `bg`, `accent`, `title_format`, `house_style`, `negative`, `music`). `run_dir_for(root, niche, slug)` used consistently. `_GpuSpeaker._speed` set in Task 3 and asserted in its test. `load_pipeline_and_generate(..., negative=...)` matches the fake in the Task 3 test.
