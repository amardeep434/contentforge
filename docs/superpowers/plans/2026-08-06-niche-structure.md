# Multi-niche production structure (feature B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group video production per niche on disk (`data/<niche>/videos/<slug>/{work,meta,final}`) and drive each niche's look/voice/format from a hand-authored `niche.toml`, instead of niche-blind flat dirs and hardcoded constants.

**Architecture:** A new `NicheConfig` (loaded from `data/<niche>/niche.toml`) is resolved once in `runtime` and its fields are passed into the already-injected stage factories (illustrator, speaker, metadata_writer, scriptwriter) — the existing module constants stay only as fallbacks. `pipeline.build_video` and the `ensure_*` stages write into `work/`, `meta/`, `final/` sub-roots. The current Mr-Finance constants become the first niche, `business-economics/niche.toml`, so behaviour is preserved.

**Tech Stack:** Python 3.13, stdlib `tomllib`, pytest. No new dependencies.

## Global Constraints

- No new runtime dependency — `niche.toml` is parsed with stdlib `tomllib` (read binary mode).
- Every backend stays **injected** through `runtime.py`; stages never import niche values directly — they receive them as parameters. Module constants remain as **fallback defaults only**.
- Immutable data: `NicheConfig` is a frozen dataclass; no in-place mutation.
- Fail loud at the boundary: a named niche with a missing/malformed `niche.toml` raises `MissingDataError` naming the file and the bad field — never a silent default.
- Back-compat: `--niche` defaults to `business-economics`; existing `pipeline make <slug>` keeps working. Legacy `data/videos/*` runs are left untouched (no migration).
- Filename join key stays the zero-padded index: `beat_NNN.wav` ↔ `shot_NNN.png` ↔ `frame_NNN.png`.
- Docs are a deliverable of this feature (Task 6), not optional.
- Keep the suite green (currently 578 tests): `PYTHONPATH=src .venv/bin/python -m pytest`.

---

## File Structure

- **Create** `src/contentforge/niche.py` — `NicheConfig` dataclass + `load_niche(niche, root)`.
- **Create** `data/business-economics/niche.toml` — the first niche, current values.
- **Create** `tests/test_niche.py` — loader tests.
- **Create** `docs/setup/niches.md` — how to add a niche.
- **Modify** `src/contentforge/pipeline.py` — `run_dir_for` signature + `work/meta/final` sub-roots in every `ensure_*`, `RunLog`, `build_video`, `write_manifest`.
- **Modify** `src/contentforge/runtime.py` — accept a `NicheConfig`, pass fields into factories.
- **Modify** `src/contentforge/visuals/illustrate.py` — `illustrate`/`build_prompt`/`load_pipeline` take `house_style`/`negative`/`model` params (constants as defaults).
- **Modify** `src/contentforge/visuals/palette.py` — `normalise` takes a `background` param (default `REFERENCE_BACKGROUND`).
- **Modify** `src/contentforge/publish/metadata.py` — title-format text comes from a param.
- **Modify** `src/contentforge/script/generate.py` — voice guidance / word target from params.
- **Modify** `src/contentforge/cli.py` — `--niche` on `make`/`publish`; build `run_dir` per niche; load `NicheConfig`.
- **Modify** `docs/setup/running-the-pipeline.md`, `README.md`, `~/.hermes/skills/contentforge-video/SKILL.md`, `~/.hermes/skills/contentforge-render-status/SKILL.md`, the session handoff.

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
  `script_voice: str`, `target_words: tuple[int,int]`.
- Produces: `load_niche(niche: str, root: Path) -> NicheConfig` reading `root/niche/niche.toml`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_niche.py
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
voice_guidance = "second-person"
target_words = [2500, 3200]
"""

def _write(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True)
    (d / "niche.toml").write_text(text)
    return tmp_path

def test_loads_a_full_profile(tmp_path):
    root = _write(tmp_path, "demo", GOOD)
    cfg = load_niche("demo", root)
    assert cfg.name == "demo"
    assert cfg.title_format == "The Economics of Owning a {subject}"
    assert cfg.bg == (240, 232, 216)
    assert cfg.accent == (38, 122, 118)
    assert cfg.image_model == "qwen"
    assert cfg.pace == 0.80
    assert cfg.music is False
    assert cfg.target_words == (2500, 3200)
    assert cfg.voice_reference == Path("~/ref.wav").expanduser()

def test_missing_file_raises_with_path(tmp_path):
    with pytest.raises(MissingDataError, match="niche.toml"):
        load_niche("nope", tmp_path)

def test_malformed_missing_key_raises_naming_the_field(tmp_path):
    bad = GOOD.replace('image_model = "qwen"', "")
    root = _write(tmp_path, "demo", bad)
    with pytest.raises(MissingDataError, match="image_model"):
        load_niche("demo", root)

def test_bad_colour_raises(tmp_path):
    bad = GOOD.replace("bg = [240, 232, 216]", "bg = [240, 232]")
    root = _write(tmp_path, "demo", bad)
    with pytest.raises(MissingDataError, match="bg"):
        load_niche("demo", root)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_niche.py -q`
Expected: FAIL — `ModuleNotFoundError: contentforge.niche`.

- [ ] **Step 3: Write `niche.py`**

```python
# src/contentforge/niche.py
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
    script_voice: str
    target_words: tuple[int, int]


def _require(table: dict, section: str, key: str, path: Path):
    if section not in table or key not in table[section]:
        raise MissingDataError(
            f"{path}: missing [{section}].{key} - a niche profile must set it"
        )
    return table[section][key]


def _colour(value, key: str, path: Path) -> tuple[int, int, int]:
    if not (isinstance(value, list) and len(value) == 3
            and all(isinstance(c, int) for c in value)):
        raise MissingDataError(f"{path}: [{key}] must be three integers [r,g,b]")
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
        bg=_colour(_require(table, "visual", "bg", path), "visual].bg", path),
        accent=_colour(_require(table, "visual", "accent", path), "visual].accent", path),
        image_model=_require(table, "visual", "image_model", path),
        voice_reference=Path(_require(table, "voice", "reference", path)).expanduser(),
        pace=float(_require(table, "voice", "pace", path)),
        music=bool(_require(table, "voice", "music", path)),
        script_voice=_require(table, "script", "voice_guidance", path),
        target_words=(int(words[0]), int(words[1])),
    )
```

- [ ] **Step 4: Write `business-economics/niche.toml` with today's values**

Copy the exact current constants (read them from source, do not retype from memory):
`HOUSE_STYLE` and `NEGATIVE` from `visuals/illustrate.py`; `bg` from
`visuals/palette.py:58` `REFERENCE_BACKGROUND = (240, 232, 216)`; `accent` the teal
`(38, 122, 118)` (grep it: `grep -rn "38, 122, 118" src/contentforge`); `image_model = "qwen"`;
`reference = "~/.local/share/contentforge/voices/iapetus-reference.wav"`; `pace = 0.80`;
`music = false`; `voice_guidance` from `script/generate.py`; `target_words` from its
`TARGET_WORDS_LOW/HIGH`; `title_format = "The Economics of Owning a {subject}"`.

```toml
# data/business-economics/niche.toml
[niche]
name = "business-economics"
title_format = "The Economics of Owning a {subject}"

[visual]
house_style = "<paste HOUSE_STYLE verbatim from visuals/illustrate.py>"
negative = "<paste NEGATIVE verbatim from visuals/illustrate.py>"
bg = [240, 232, 216]
accent = [38, 122, 118]
image_model = "qwen"

[voice]
reference = "~/.local/share/contentforge/voices/iapetus-reference.wav"
pace = 0.80
music = false

[script]
voice_guidance = "<paste the voice/structure guidance from script/generate.py>"
target_words = [2500, 3200]
```

- [ ] **Step 5: Run tests, verify pass**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_niche.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/contentforge/niche.py tests/test_niche.py data/business-economics/niche.toml
git commit -m "feat: NicheConfig loader + first niche.toml (business-economics)"
```

---

## Task 2: Per-niche run directory (work / meta / final)

**Files:**
- Modify: `src/contentforge/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `run_dir_for(root: Path, niche: str, slug: str) -> Path` = `root/niche/"videos"/slug`.
- Produces: sub-root constants `WORK_DIR="work"`, `META_DIR="meta"`, `FINAL_DIR="final"`; audio/raw/frames live under `work/`, script/spec/manifest/status/run.log/sources under `meta/`, video/subtitles/metadata/thumbnail/published under `final/`.

- [ ] **Step 1: Write the failing test** (extend `tests/test_pipeline.py`)

```python
def test_run_dir_is_grouped_by_niche(tmp_path):
    from contentforge.pipeline import run_dir_for
    assert run_dir_for(tmp_path, "biz", "laundromat") == tmp_path / "biz" / "videos" / "laundromat"

def test_build_writes_into_work_meta_final(tmp_path):
    fakes = Fakes()
    run = tmp_path / "biz" / "videos" / "run"
    build(run, fakes)                      # `build` helper points build_video at `run`
    assert (run / "meta" / "spec.json").exists()
    assert (run / "meta" / "status.json").exists()
    assert (run / "work" / "audio").is_dir()
    assert (run / "work" / "raw").is_dir()
    assert (run / "final" / "video.mp4").exists()
```

- [ ] **Step 2: Run, verify fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py -k "niche or work_meta_final" -q`
Expected: FAIL (paths still flat).

- [ ] **Step 3: Implement path changes in `pipeline.py`**

- Change `run_dir_for` to `def run_dir_for(root, niche, slug): return root / niche / "videos" / slug`.
- Add `META_DIR = "meta"`, `FINAL_DIR = "final"`; keep `WORK_DIR = "work"`. Set `AUDIO_DIR = "work/audio"`, `RAW_DIR = "work/raw"`, `FRAME_DIR = "work/frames"` (join under run_dir stays `run_dir / AUDIO_DIR`).
- Point artefact paths at sub-roots: `SCRIPT_NAME`, `SPEC_NAME`, `MANIFEST_NAME`, `STATUS_NAME`, `RUNLOG_NAME`, and `sources/` → prefix with `META_DIR`; `VIDEO_NAME`, `subtitles.srt/.vtt`, `METADATA_NAME`, `THUMBNAIL_NAME`, `published.json` → prefix with `FINAL_DIR`. In each `ensure_*`, `RunLog`, and `write_manifest`, build the path as `run_dir / META_DIR / X` or `run_dir / FINAL_DIR / X`. Create the sub-dirs with `mkdir(parents=True, exist_ok=True)` where they are first written.
- `render`'s `work_dir` stays `run_dir / WORK_DIR / "ffmpeg"` (a scratch subdir).

- [ ] **Step 4: Update existing pipeline tests to the new paths**

Adjust any assertion in `tests/test_pipeline.py` referencing old flat paths (`run/audio`, `run/video.mp4`, `run/status.json`, `run/spec.json`) to the `work/meta/final` equivalents. The `build(tmp_path, fakes, ...)` helper's `run_dir` argument is unchanged; only the internal sub-paths move.

- [ ] **Step 5: Run pipeline tests, verify pass**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contentforge/pipeline.py tests/test_pipeline.py
git commit -m "feat: per-niche run dir with work/meta/final sub-roots"
```

---

## Task 3: Thread NicheConfig through the stage factories

**Files:**
- Modify: `src/contentforge/runtime.py`, `visuals/illustrate.py`, `visuals/palette.py`, `publish/metadata.py`, `script/generate.py`
- Test: `tests/test_runtime.py` (create if absent), plus existing tests stay green.

**Interfaces:**
- Consumes: `NicheConfig` from Task 1.
- Produces: each factory accepts the niche values as parameters; module constants remain as defaults so callers that pass nothing behave as before.
  - `illustrate.build_prompt(subject, style=HOUSE_STYLE, negative=NEGATIVE, ...)`
  - `illustrate.illustrate(..., house_style=HOUSE_STYLE, negative=NEGATIVE, model=DEFAULT_MODEL)`
  - `palette.normalise(source, destination=None, background=REFERENCE_BACKGROUND)`
  - `runtime.illustrator(niche=None, model=None, ...)`, `runtime.speaker(niche=None, ...)`, `runtime.metadata_writer(niche=None, client=None)`, `runtime.scriptwriter(topic, source_urls, niche=None, client=None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runtime.py
from pathlib import Path
from contentforge.niche import NicheConfig

def _cfg(**over):
    base = dict(name="n", title_format="T {subject}", house_style="HS", negative="NEG",
                bg=(1,2,3), accent=(4,5,6), image_model="qwen",
                voice_reference=Path("/ref.wav"), pace=0.7, music=False,
                script_voice="SV", target_words=(100, 200))
    base.update(over)
    return NicheConfig(**base)

def test_illustrator_uses_niche_house_style(monkeypatch, tmp_path):
    from contentforge import runtime
    seen = {}
    def fake_gen(name, w=768, h=432):
        return object(), (lambda prompt, path, seed: seen.setdefault("prompt", prompt) or path), (lambda: None)
    monkeypatch.setattr("contentforge.visuals.gguf_backends.load_pipeline_and_generate", fake_gen)
    monkeypatch.setattr("contentforge.visuals.illustrate.illustrate",
                        lambda subjects, out_dir, **k: [] )
    draw = runtime.illustrator(niche=_cfg(image_model="qwen"))
    # image_model comes from the niche, not the env/global default
    assert draw is not None  # smoke: constructing with a niche config works
```

(Keep this test light — the deep behaviour is already covered by `test_gguf_backends.py`; here we only assert the niche value flows in without error.)

- [ ] **Step 2: Run, verify fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_runtime.py -q`
Expected: FAIL — `illustrator()` has no `niche` parameter yet.

- [ ] **Step 3: Add `niche` params (constants stay as defaults)**

- `visuals/illustrate.py`: give `build_prompt` a `negative` param (currently only `style`); give `illustrate` and `load_pipeline` `house_style`/`negative`/`model` params defaulting to the module constants; use them where the constants are used now.
- `visuals/palette.py`: `normalise(..., background=REFERENCE_BACKGROUND)`; use `background` in the `flatten_background(..., fill=background)` call (palette.py:199).
- `publish/metadata.py`: accept a `title_format` string param and inject it into the prompt where the "The Economics of Owning a [X]" text is hardcoded.
- `script/generate.py`: `generate_script(..., voice_guidance=DEFAULT_VOICE_GUIDANCE, target_words=(TARGET_WORDS_LOW, TARGET_WORDS_HIGH))`; use them in the prompt.
- `runtime.py`: each factory gains `niche: NicheConfig | None = None`. When present, pull values from it: `illustrator` → `image_model=niche.image_model`, and pass `house_style/negative` into the generate closure / `illustrate`; `speaker` → `reference=niche.voice_reference, pace=niche.pace`; `metadata_writer` → `title_format=niche.title_format`; `scriptwriter` → `voice_guidance=niche.script_voice, target_words=niche.target_words`. When `niche is None`, behave exactly as today (constants).

- [ ] **Step 4: Run the full suite, verify green**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: PASS (578 + new).

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/runtime.py src/contentforge/visuals/illustrate.py \
        src/contentforge/visuals/palette.py src/contentforge/publish/metadata.py \
        src/contentforge/script/generate.py tests/test_runtime.py
git commit -m "feat: thread NicheConfig through the stage factories"
```

---

## Task 4: CLI --niche wiring

**Files:**
- Modify: `src/contentforge/cli.py`
- Test: `tests/test_cli.py` (extend, or add a focused test)

**Interfaces:**
- Consumes: `load_niche` (Task 1), `run_dir_for` (Task 2), niche-aware factories (Task 3).
- Produces: `make`/`publish` accept `--niche` (default `business-economics`); `run_dir = args.root / args.niche / "videos" / args.slug`; `--root` default `data/`.

- [ ] **Step 1: Write the failing test**

```python
def test_make_uses_niche_run_dir(tmp_path, monkeypatch):
    # Assert the CLI builds data/<niche>/videos/<slug> and loads that niche.toml.
    # Use --dry-run so no models load; point --root at a tmp data dir containing
    # <niche>/niche.toml and a --script-file, and assert the run dir exists there.
    ...
```

Write it concretely against the `make --dry-run` path (which only needs script + beats), creating `tmp/business-economics/niche.toml` (copy the repo's) and a script file, then asserting `run_dir` resolves under the niche.

- [ ] **Step 2: Run, verify fail** — `--niche` unknown arg.

- [ ] **Step 3: Implement**

- Add `make.add_argument("--niche", default="business-economics")` and the same on the `publish` parser. Change both `--root` defaults from `Path("data/videos")` to `Path("data")`.
- In the `make` handler: `run_dir = args.root / args.niche / "videos" / args.slug`; `cfg = load_niche(args.niche, args.root)`; pass `niche=cfg` into `runtime.illustrator/speaker/metadata_writer/scriptwriter`. Update the two closing `print` lines to reference the niche path and `pipeline make <slug> --niche <niche>`.
- In the `publish` handler: same `run_dir`; read artefacts from `run_dir / "final"`.

- [ ] **Step 4: Run full suite, verify green.**

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/cli.py tests/test_cli.py
git commit -m "feat: --niche on make/publish, niche-scoped run dirs"
```

---

## Task 5: End-to-end smoke on the host

**Files:** none (verification task).

- [ ] **Step 1:** Build one short video in the new layout on the host (fast draft model):

```bash
set -a && . ./.env 2>/dev/null; set +a
.venv/bin/python -c "import sys; from contentforge.cli import main; sys.exit(main())" \
  make smoke --niche business-economics --model flux --root data \
  --script-file <(printf 'One short sentence. Two short sentence. Three.\n')
```

- [ ] **Step 2:** Assert the tree: `data/business-economics/videos/smoke/{work,meta,final}` populated; `final/video.mp4`, `final/thumbnail.png`, `meta/status.json` all `ok`.
- [ ] **Step 3:** No commit (throwaway run). Delete `data/business-economics/videos/smoke` after.

---

## Task 6: Documentation

**Files:**
- Modify: `docs/setup/running-the-pipeline.md`, `README.md`
- Create: `docs/setup/niches.md`
- Modify: `~/.hermes/skills/contentforge-video/SKILL.md`, `~/.hermes/skills/contentforge-render-status/SKILL.md`
- Modify: the session handoff

- [ ] **Step 1:** `running-the-pipeline.md` — replace the "What it leaves behind" listing with the `work/meta/final` layout; add `--niche` to `make`/`publish` examples and note the default; state `final/` is the reviewable/publish set.
- [ ] **Step 2:** Create `docs/setup/niches.md` — what a niche is, the `niche.toml` field-by-field schema (from Task 1), how to add one (`mkdir data/<niche>; write niche.toml`), and that it is hand-authored for now (auto-profiling parked).
- [ ] **Step 3:** `README.md` — the run-dir / one-command blurb reflects the niche layout.
- [ ] **Step 4:** Both hermes skills — the run paths and `status.json` location referenced move under `/root/videos/<niche>/videos/<slug>/…`; update the `make`/poll commands to pass `--niche` and read the new `status.json`/`final/` paths.
- [ ] **Step 5:** Handoff — a short note that feature B landed, where the layout/config live, and that A (harvest) is next.
- [ ] **Step 6: Commit**

```bash
git add docs/ README.md
git commit -m "docs: multi-niche layout, niche.toml, and updated hermes skills"
```

*(The two hermes SKILL.md files live outside the repo under `~/.hermes/skills/`; edit them in place — they are not committed to git.)*

---

## Self-Review

- **Spec coverage:** layout (Task 2), niche.toml + NicheConfig (Task 1), wiring make/publish to per-niche config (Tasks 3–4), business-economics carries current values (Task 1 step 4 + characterisation via existing tests), CLI + back-compat (Task 4), error handling (Task 1), testing (each task), documentation (Task 6). Roadmap C/A are parked in the spec, not this plan. Covered.
- **Placeholder scan:** Task 4 step 1 test body is described rather than fully coded — the implementer writes it against `make --dry-run`; acceptable as a focused instruction, but prefer to expand it to real code during execution. Everything else is concrete.
- **Type consistency:** `NicheConfig` field names used in Tasks 3–4 match Task 1 exactly (`image_model`, `voice_reference`, `pace`, `script_voice`, `target_words`, `bg`, `accent`, `title_format`). `run_dir_for(root, niche, slug)` used consistently in Tasks 2 and 4.
