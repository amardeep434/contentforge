# Session Handoff — contentforge (2026-08-07)

**Continues:** `docs/handoff/2026-08-06-session-handoff.md` (read that first for the pre-history:
voice=OmniVoice, the copy-the-approach copyright stance, OmniRoute LLM on :20128, the earlier
image-model eval that ended on an open A/B/C decision).

**Branch state:** `master` at `bbdc769` (PR #2 + PR #3 merged). Active work branch
**`feat/niche-structure`** (off `bbdc769`, **local-only, not pushed**) — holds the multi-niche
specs/plans + the first two implemented tasks.

**Tests:** 584 passing (`PYTHONPATH=src .venv/bin/python -m pytest`). Python 3.13 in `.venv`.

> This session was huge. It (1) finished the image-model decision, (2) hardened the pipeline,
> (3) fully provisioned hermes incl. a hard nvidia-Vulkan fix, (4) designed + specced + planned
> two features (multi-niche structure "B" and harvest "A"), and (5) began executing B via
> subagent-driven development. **We stopped mid-execution when the session usage limit hit
> (resets 2am Asia/Kolkata). Task 2's code is committed and green; it only needs review.**

---

## 0. THE ONE-LINE STATE + WHERE TO RESUME

Executing plan B (`docs/superpowers/plans/2026-08-06-niche-structure.md`) via **subagent-driven
development** (Sonnet-5 implementers, Opus reviewers, ledger-tracked). **Task 1 done+reviewed.
Task 2 implemented + committed (`b0bcb46`) + 584 tests pass, but its Opus review never ran
(implementer died at the usage limit on "write report").**

**RESUME AT: the Task-2 review.** See §9 for the exact commands. Do NOT re-implement Task 2 — the
code is committed and green. Generate its review package (`BASE=f119f9c`, `HEAD=b0bcb46`), dispatch
the Opus reviewer, then continue the loop: Task 3 → 3b → 4 → 5 → 6, then feature A (plan
`2026-08-06-harvest.md`, 7 tasks).

**UPDATE (later this session): feature B landed.** All six tasks of
`docs/superpowers/plans/2026-08-06-niche-structure.md` are implemented and committed on
`feat/niche-structure`. The multi-niche layout is `data/<niche>/videos/<slug>/{work,meta,final}/`
(`run_dir_for` in `src/contentforge/pipeline.py`); the per-niche profile is `NicheConfig`
(`src/contentforge/niche.py`), loaded from `data/<niche>/niche.toml` and validated field-by-field
(fails loud with `MissingDataError` on anything missing or malformed — no auto-profiling, hand-authored
only). `pipeline make`/`publish` both take `--niche` (default `business-economics`, which carries the
original Mr-Finance constants unchanged). Docs: `docs/setup/niches.md` (new — the `niche.toml` schema
and how to add a niche), `docs/setup/running-the-pipeline.md` and `README.md` (updated for the new run
layout and `--niche`), plus the two hermes skills at `~/.hermes/skills/contentforge-video/SKILL.md`
and `~/.hermes/skills/contentforge-render-status/SKILL.md`. **Feature A (harvest,
`docs/superpowers/plans/2026-08-06-harvest.md`) is next** — it depends on B's `run_dir_for` and
`niche=` factory kwargs.

---

## 1. Image model — RESOLVED: Qwen-Image, default, fail-loud

The 2026-08-06 open decision (FLUX vs Qwen GGUF, options A/B/C) is settled.

- **Option C (newer diffusers) is impossible:** `diffusers 0.39.0` is the LATEST on PyPI. The
  `KeyError: None` was really diffusers' GGUF params being unable to ride accelerate's
  `enable_sequential_cpu_offload` (meta-device reconstruction drops `quant_type`). 6 GB *needs*
  sequential offload → diffusers-direct GGUF is a dead end.
- **Option B's tool (Wan2GP) is a 5 GB video suite; its engine is `mmgp`.** `pip install mmgp
  optimum-quanto` into the working venv is all that's needed. mmgp can't eat raw `.gguf` and chokes
  on diffusers `GGUFParameter`, BUT its happy path (on-the-fly quanto qint8 + layer streaming) works.
- **THE WORKING METHOD** (`src/contentforge/visuals/gguf_backends.py`, `scripts/build_prequant.py`):
  1. diffusers loads the GGUF transformer **if you pass `config=<transformer config dir>`** (the
     original `KeyError`/SD1.5-config errors were just a missing config).
  2. Dequantise every `GGUFParameter` to plain bf16 in-memory (`dequantize_gguf_tensor`).
  3. **Pre-quantise once** with `offload.save_model(..., do_quantize=True, qint8,
     config_file_path=...)` → a qint8 `.safetensors`. Reload with
     `offload.fast_load_transformers_model(..., modelClass=...)` (meta-device, ~1 GB at load), build
     the pipe, `offload.profile(pipe, VerylowRAM_LowVRAM, quantizeTransformer=False)` to stream.
     **Pixels are bit-identical** to the on-the-fly path (verified: identical PNG byte sizes).
  4. **Env-skew patch (KEEP IT):** transformers 5.14 calls `safetensors.safe_open(..., backend=...)`
     but safetensors 0.8.0 rejects `backend`. Drop the kwarg by patching
     `transformers.modeling_utils.safe_open` **AFTER** importing diffusers *and* mmgp (mmgp
     re-touches transformers on import and would undo an earlier patch). sdxl-turbo never hit this
     because it has no T5.
- **Decision (operator, by eye): Qwen-Image is the model for every final render** — bolder ink and
  the ONLY model that draws a real **stick figure** instead of a detailed person (FLUX and sdxl
  over-draw people). **No silent fallback**: if Qwen can't load, the render **fails loudly**;
  FLUX/sdxl stay selectable via `CONTENTFORGE_IMAGE_MODEL`/`--model` only as an explicit **draft**
  pass. `runtime.illustrator` implements this; `DEFAULT_IMAGE_MODEL = "qwen"`.
- **Measured (RTX 3060, 6 GB), pre-quant reload path:** Qwen qint8 20 GB file, **~36 GB peak RAM**,
  ~2 GB VRAM, ~4 min/image (20 steps) → **~10 h for a ~150-image video**. FLUX qint8 12 GB, ~18 GB
  RAM, ~2 GB VRAM, ~19 s/image (4 steps) → ~48 min. Operator **accepted the ~10 h Qwen render** as an
  overnight batch (resumable). Beats = sentences (short merged) → a 2500–3200-word script ≈ ~150 images.
- **Assets (host):** `~/.local/share/contentforge/models/{qwen-image-qint8.safetensors (20 GB),
  flux-schnell-qint8.safetensors (12 GB), flux-schnell-cfg/config.json}`. Rebuild with
  `python scripts/build_prequant.py` (~42 GB RAM transient, host only; needs the GGUF sources
  `city96/Qwen-Image-gguf` + `city96/FLUX.1-schnell-gguf` and components `Qwen/Qwen-Image` +
  `Freepik/flux.1-lite-8B` in the HF cache).
- **Comparison images:** `docs/evidence/image-model-compare/{flux,qwen}_{fan,figure}.png`.

## 2. Pipeline hardening (all committed, verified live)

- **Real VRAM OOM in the voice→image handoff (FIXED).** After the voice model closed, ~1.6 GB VRAM
  lingered and Qwen fragmented across images (~800 MB reserved-but-unallocated) until 130 MB short.
  Fixes: `runtime.py` sets `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` at import (main lever);
  `_GpuSpeaker.close()` adds `torch.cuda.synchronize()` + `empty_cache()` + `ipc_collect()`;
  `gguf_backends` calls `empty_cache()` before building the pipe.
- **Durable incremental log (`RunLog` in `pipeline.py`):** writes `status.json` (per-stage
  pending/running/ok/skipped/failed/stopped + error + remaining) and `run.log` (timestamped) after
  **every** stage, so a crash/stop leaves a full record.
- **Safe stop + partial resume (`interrupt.py`):** Ctrl-C/SIGTERM finishes the current item then
  stops → clean `"stopped"` status, resumable; a second signal hard-kills. Per-item skip in
  audio/draw/letter keeps finished items across a rerun.
- **Cross-stage memory freeing:** `illustrator.close()` frees the image model after draw (mmgp
  `offload_obj.release()`); verified VRAM 1922 → 792 MB. On process exit the OS frees everything
  regardless.

## 3. Docs updated + merged

README, `docs/setup/running-the-pipeline.md` (rewritten), `local-image-generation.md` (rewritten),
`local-voice.md` (new), `.env.example`, `pyproject.toml` (`[gpu]` gains mmgp+optimum-quanto),
`cli.py` (`--voice-backend` choices now include `omnivoice`). All merged to master (PR #2 = the
evidence-ledger feature branch; PR #3 = the hermes/nvidia-Vulkan docs).

## 4. Hermes — task 3 DONE, verified (one activation step left)

A **full video rendered end to end inside the sandbox** (Qwen images, OmniVoice narration,
nvidia-Vulkan upscale, ffmpeg → `video.mp4` + thumbnail on the host at
`/home/amardeep/hermes-videos/verify-test/`).

**Config (`~/.hermes/config.yaml` → `terminal`):** `docker_image: contentforge-sandbox:latest`,
`container_memory: 40960`, `container_disk: 102400`, `lifetime_seconds: 43200`,
`daemon_term_grace_seconds: 300`, `docker_extra_args` += `-v /home/amardeep/hermes-videos:/root/videos`,
`docker_env`: `CONTENTFORGE_VOICE_BACKEND=omnivoice`, `CONTENTFORGE_VOICE_REFERENCE=/root/.local/share/contentforge/voices/iapetus-reference.wav`,
`CONTENTFORGE_IMAGE_MODEL=qwen` (dead Gemini AQ key removed). Gateway is a systemd --user service
`hermes-gateway.service`.

**Provisioning (host scripts):** `~/hermes-provision.sh` (STAGE 0 build image, 1 copy ~60 GB
weights/voice/upscaler/fonts into the root-owned sandbox home via a root container, 2 refresh
contentforge source from the **main checkout**, 3 pip the EXACT host stack `torch==2.6.0
torchaudio==2.6.0` cu124 + `diffusers==0.39.0 transformers==5.14.1 accelerate safetensors mmgp
optimum-quanto omnivoice soundfile WeTextProcessing` + a static ffmpeg into `/root/.local/bin`, 4
verify with doctor through the proxy). `~/hermes-sandbox.Dockerfile`. Sandbox is **python3.11**
(host 3.13); torch cu124 runs fine there; qint8 files are python-agnostic.

**Render model in hermes:** a Qwen video is ~10 h but hermes commands time out in minutes, so the
render is **launched detached** (`setsid pipeline make … --root /root/videos &`) and **polled** via
`status.json`. Two skills written: `~/.hermes/skills/contentforge-video` (start a render, detached +
poll) and `contentforge-render-status` (check/resume/stop across sessions).

### 4.1 THE nvidia-Vulkan root cause + fix (marquee finding)
The upscaler `realesrgan-ncnn-vulkan` failed in-container: `vkCreateInstance failed -9` / "Could not
get vkCreateInstance via vk_icdGetInstanceProcAddr for ICD libGLX_nvidia.so.0". **Not a broken
driver** — the host works, and the container had the same valid `libGLX_nvidia.so.610.43.03` (exports
the symbol), the ICD json, `/dev/nvidia*`, `/dev/nvidia-caps`, `NVIDIA_DRIVER_CAPABILITIES=all`.
`strace` found the real cause: **`libEGL.so.1` ENOENT everywhere**. The nvidia-container-toolkit
injects nvidia's *vendor* libs (`libGLX_nvidia`, `libEGL_nvidia`) but **not the GLVND *dispatch*
layer** (`libEGL.so.1`, `libGLX.so.0`) that nvidia's combined lib dlopens at init → the ICD returns
NULL for vkCreateInstance. **Fix: `libglvnd0` (+ `libgl1 libegl1 libglx0`) in the custom sandbox
image.** Then the passed-through nvidia GPU does the upscale at **~2.8 s/image, byte-identical to the
host** (6119983 bytes). The custom image also adds the Vulkan loader (`libvulkan1`), a static
`ffmpeg`, and `mesa-vulkan-drivers` as a CPU (llvmpipe) fallback. `NVIDIA_DRIVER_CAPABILITIES=all` is
necessary but NOT sufficient — the GLVND dispatch libs were the real gap. (Recorded in
`running-the-pipeline.md` §6 and `~/hermes-sandbox.Dockerfile`.)

### 4.2 ⚠️ LAST ACTIVATION STEP (not done)
The live agent container (`hermes-<id>`) still runs the OLD `nikolaik` image. To switch it to
`contentforge-sandbox:latest`:
```
docker rm -f $(docker ps -q -f name=hermes-)
systemctl --user restart hermes-gateway.service
```
Then one agent command recreates it. Verify:
`docker inspect $(docker ps -q -f name=hermes-) --format '{{.Config.Image}} {{.HostConfig.Memory}}'`
→ want `contentforge-sandbox:latest 42949672960`.

## 5. Task 5 (sync main checkout) — DONE
Local `master` fast-forwarded to the merge commits (`ed7640e`, then `bbdc769`). The provisioning
script's `SRC` now points at the **main checkout** (not the evidence-ledger worktree).

## 6. Preferences saved to memory (apply every session)
- **`no-commit-attribution`**: NEVER add `Co-Authored-By`, `Claude-Session:` links, or "Generated
  with Claude Code" to commits/PRs/messages. (User asked mid-session; the two already-merged
  commits `7b873ae`/`0f21ffa` still carry the trailer in history — left as-is, rewriting merged
  history is worse.)
- **`docs-in-specs-and-plans`**: every spec AND plan must include documentation updates as explicit
  deliverables.

## 7. THE MULTI-NICHE + HARVEST DESIGN (current work)

**Operator's goal:** research → pick a channel worth copying the approach of → harvest its video
**topics** + **transcripts** → **reword creatively** (avoid a copyright strike) → make our own
videos in that niche's style. Multiple niches.

**Key clarification (important):** the operator meant reword the competitor's **transcript**, not
independent sources. That is **strike-safe and fits the pipeline by design:** copyright strikes are
Content ID on *media*, not reworded scripts; and principle #5 "Transform, never relay" +
`script/validate.py::check_verbatim` already **reject** a script too close to its source. So the
transcript is used as **source material to transform**; the *topic* is borrowed, the *expression* is
ours. Honest residual caveat (not a strike): reused content can affect monetization review — keep
`check_verbatim` strict.

**Decomposed into three, and the operator's decision:**
- **B — multi-niche structure** (BUILD NOW): `data/<niche>/videos/<slug>/{work,meta,final}` +
  `niche.toml` full profile + `NicheConfig` + rewire make/publish to per-niche config. First niche
  `business-economics` = today's Mr-Finance constants (hand-authored, behaviour preserved).
- **A — harvest** (BUILD NOW, after B): channel → reviewable `plan.jsonl` + staged transcripts →
  `make --transcript-file` rewords → `harvest-make` batch loop (skip done, continue-on-fail,
  interrupt-resumable, `batch.json` ledger). yt-dlp `[harvest]` extra.
- **C — niche auto-profiling** (PARKED, documented): derive `niche.toml` from a reference channel
  (title format, pace, palette, house style, script voice). **Parked** because auto-deriving a good
  profile is riskier/worse than hand-authoring until the pattern is clear over 2–3 niches.
- **Honest upload-first critique (recorded, operator overrode to still build B+A):** 0 videos
  published; the project's own research says "the next evidence has to come from our own uploads";
  the highest-value move is to publish a handful and **measure** before more generality. Operator
  chose to build B+A now and document C — so this critique lives in the spec's Roadmap, not as a
  blocker.

**Specs + plans (all committed on `feat/niche-structure`):**
- `docs/superpowers/specs/2026-08-06-niche-structure-design.md` (B) + `plans/2026-08-06-niche-structure.md` (B, 6 tasks + Task 3b).
- `docs/superpowers/specs/2026-08-06-harvest-design.md` (A) + `plans/2026-08-06-harvest.md` (A, 7 tasks).
- **Both plans were hardened by two Opus forks to literal, zero-assumption detail and opus-reviewed.**
  The hardening fixed real assumption-traps a cheaper agent would hit: **accent is `caption.py:35
  ACCENT=(38,122,118)`** (not palette); **`bg`/`accent` thread through `pipeline.py`**
  (`normalise` at :354, `letter_frame`→`chapter_label` at :381), NOT through runtime factories;
  **script "voice" is the full multi-line `SYSTEM` prompt** in `generate.py` (field renamed
  `script_system`); **Qwen's negative prompt is `gguf_backends.py:164`**; **`house_style` is dropped
  at `illustrate.py:201`** (`build_prompt(subject)` uses the default); **`get_videos` returns
  `VideoRecord` with NO description** and silently drops no-duration videos; **`build_plan` must
  return the quota ledger**; **`scriptwriter(topic, source_urls, client=None)`** gets an added
  optional `sources` kwarg. Task 3b (threading bg+accent through 3 pipeline layers) was flagged as
  the highest-cost/lowest-value piece — kept because operator chose the full profile; first thing to
  cut if B feels heavy.

## 8. Git / branch / PR state
- `master` = `bbdc769` (PRs #2, #3 merged).
- **`feat/niche-structure`** (local-only, NOT pushed) off `bbdc769`, contains, newest first:
  `b0bcb46` Task 2 (per-niche run dir) · `f119f9c` Task 1 (NicheConfig + niche.toml) ·
  `2034007` harden plans · `cd9cea4` plan A · `acda0cb` spec A · `bc2adf3` plan B · `92687cb` spec B.
- When B's tasks + final review are done → `superpowers:finishing-a-development-branch` → PR for
  `feat/niche-structure`. Then A (same branch or a new one).

## 9. HOW TO RESUME THE SDD EXECUTION (do this next session)

**Flow decided:** subagent-driven development (`superpowers:subagent-driven-development`).
Implementers = **Sonnet 5** (`model: sonnet`). Task reviewers = **Opus** (`model: opus`). Each task:
Sonnet implements+commits → Opus reviews the diff → fix loop if needed → ledger → next task.
**Execute continuously; do not pause between tasks** (only stop on a blocker or all-done).

**SDD workspace + ledger (resume map):**
`/home/amardeep/Projects/contentforge/.superpowers/sdd/2026-08-06-niche-structure/`
- `progress.md` (ledger): `Task 1: complete (commits 2034007..f119f9c, review clean)` + a deferred-minor line.
- `BASE-task2` = `f119f9c…` (Task 2's BASE). `task-1-brief.md`, `task-2-brief.md`, `task-1-report.md`
  exist; **`task-2-report.md` is MISSING** (implementer died before writing it — not needed, review from the diff).
- SDD scripts: `~/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development/scripts/{sdd-workspace,task-brief,review-package}` — **run them with cwd = the main checkout** `/home/amardeep/Projects/contentforge`.

**STEP 1 — finish Task 2 (review only; code is `b0bcb46`, 584 tests pass, tree clean):**
```
cd /home/amardeep/Projects/contentforge
SDD=~/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development/scripts
bash "$SDD/review-package" docs/superpowers/plans/2026-08-06-niche-structure.md f119f9c b0bcb46
```
Dispatch an **Opus** task-reviewer with: the Task-2 brief (`.../task-2-brief.md`), the printed review
package path, and the Global Constraints from the plan. (There is no Task-2 report file — tell the
reviewer the code is committed at `b0bcb46` and green; review from the diff.) If clean → append
`Task 2: complete (commits f119f9c..b0bcb46, review clean)` to the ledger and go to Task 3. If
Critical/Important findings → run the fix loop (resume a Sonnet implementer with the findings).

**STEP 2 — Task 3 onward (normal SDD loop):** for each of B's remaining tasks (3, 3b, 4, 5, 6):
record BASE=`git rev-parse HEAD`, `task-brief PLAN N`, dispatch Sonnet implementer with the brief
path + interfaces from earlier tasks (esp. `NicheConfig` field names from Task 1 and
`run_dir_for(root, niche, slug)` from Task 2) + a report-file path, then review-package →
Opus review → ledger. Task 6 is the docs task (includes editing the two hermes SKILL.md files under
`~/.hermes/skills/`, which are NOT in git).

**STEP 3 — feature A:** repeat the whole SDD flow for `plans/2026-08-06-harvest.md` (7 tasks). It
depends on B (uses `run_dir_for(root, niche, slug)` + the `niche=` factory kwargs B adds). Fresh
workspace: `sdd-workspace docs/superpowers/plans/2026-08-06-harvest.md`.

**STEP 4 — finish:** after each plan's final whole-branch review (most-capable model), delete that
plan's SDD workspace, then `superpowers:finishing-a-development-branch` → PR.

## 10. Outstanding (priority order)
1. **Resume SDD** (§9): Task-2 review → Tasks 3–6 (B) → A's 7 tasks.
2. **Hermes activation** (§4.2): swap the live container to `contentforge-sandbox:latest`.
3. **Merge** `feat/niche-structure` when B (and A) land.
4. **YouTube OAuth** for `publish` (one-time, host, personal Gmail; `docs/setup/publishing.md`).
5. **Rotate the 3 leaked secrets** if any transcript is shared: tinyproxy `scraper` password, the
   (dead, removed) Gemini AQ key, the OmniRoute token (`sk-…`). They surfaced in this session's logs too.
6. **§10 cleanup from the prior handoff** (reclaim disk: drop the GGUF eval scratch, PixArt, LoRAs,
   `peft`/`tiktoken`/`gguf`; KEEP mmgp + optimum-quanto + the two qint8 files).
7. **Then the real payoff:** publish a few videos and MEASURE (the upload-first critique).

## 11. Do NOT re-litigate (decided/measured this session)
Qwen = image model for finals, fail-loud, FLUX/sdxl draft-only. Pre-quant qint8 + mmgp streaming is
the load path; `expandable_segments` stays; the safetensors `backend=` patch stays (after
diffusers+mmgp import). Hermes container = `contentforge-sandbox:latest` (libglvnd0 is the Vulkan
fix), 40 GB RAM, host-mounted `/root/videos`, detached-render + poll. Multi-niche = B+A now, C
parked. Plans are hardened + opus-reviewed — implement them literally; if plan text and a review
finding conflict, ask which governs. No commit attribution ever.
