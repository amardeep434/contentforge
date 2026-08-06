# Session Handoff — contentforge video pipeline

**Date:** 2026-08-06
**Branch:** `evidence-ledger` (worktree at `~/Projects/contentforge/.claude/worktrees/evidence-ledger`)
**PR:** #2 (OPEN), 59 commits ahead of `master`, **not merged**
**Tests:** 566 passing (`PYTHONPATH=src .venv/bin/python -m pytest`)
**Goal of the project:** an evidence-grounded, mostly-offline faceless-YouTube pipeline that
**copies the approach of Mr. Finance** (`UC6AwWrRKNrwt83CMJqeTUzw`, "The Economics of Owning a
[X]") without being a copy, and can eventually be run/triggered from hermes (the user's Telegram
agent).

> This document captures every decision, discussion, issue, and fix from this session in detail.
> Read it fully before continuing. Nothing here is speculative — it reflects what is committed and
> what was measured.

---

## 0. The one-line state

The **full pipeline works end to end** and produced a real 20.6s video on the GPU
(`script → spec → audio → images → letter → render → subtitles → metadata → thumbnail`). The
**voice is solved** (OmniVoice, local, cloning the chosen Iapetus voice). The **image quality was
the last real blocker** — fixed enough to be coherent with sdxl-turbo, and a **FLUX vs Qwen-Image
(Q8 GGUF) evaluation is running in the background** to decide whether to upgrade the image model.
Remaining after that: **merge the PR**, then **finish the hermes sandbox copy** so the Telegram
agent can run it.

---

## 1. The pipeline, as built (the `make` command)

One resumable command builds everything; each stage writes a named artefact and is skipped if
present (rerun resumes; `--force <stage>` redoes one). Every backend is **injected**, so the whole
loop is unit-tested without a GPU/TTS/ffmpeg.

```
pipeline make <slug> --topic "..." --source URL --source URL   # generate script from sources
pipeline make <slug> --script-file script.txt                  # or hand-write the script
pipeline publish <slug>                                        # upload, private, asks first
pipeline doctor                                                # check GPU/ffmpeg/fonts/upscaler/LLM
```

**Stages** (all resumable/forceable): `script → spec → audio → draw → letter → render → metadata
→ thumbnail`. `render` also writes `subtitles.srt`/`.vtt`.

**Run directory** (`data/videos/<slug>/`) contains, all reviewable **before** publish:
`script.txt, sources.json, spec.json, manifest.json, audio/, raw/, frames/, video.mp4,
subtitles.srt/.vtt, metadata.json, thumbnail.png, published.json`.

**Key modules** (under `src/contentforge/`):
- `pipeline.py` — the orchestrator (`build_video`), the resumable stages, manifest, subtitles wiring.
- `runtime.py` — resolves env → injected callables (LLM client, spec planner, **speaker**,
  metadata writer, illustrator, upscaler, renderer). One place all backend choices live.
- `script/generate.py` — narration generation (voice + shapes), `script/validate.py` — the policy
  gate (verbatim/citation/credential checks), `script/spec.py` — per-beat visual spec.
- `voice/omnivoice_backend.py` (**new**), `voice/backends.py` (Gemini/edge), `voice/speak.py` (edge).
- `visuals/illustrate.py` (diffusion), `visuals/caption.py` (lettering), `visuals/sheet.py`
  (drawn document), `visuals/palette.py` (chroma correction), `visuals/thumbnail.py`, `visuals/compose.py`.
- `render/video.py` (ffmpeg), `render/subtitles.py`.
- `publish/metadata.py` (title/desc/tags/thumb_headline), `publish/youtube.py` (OAuth upload).

---

## 2. Decisions made this session (with rationale)

### 2.1 Voice: Gemini → **OmniVoice** (local, no key)
- Started with Gemini TTS, voice **Iapetus** chosen by the operator from 6 candidates read at
  matched pace (timbre-only comparison).
- **Gemini is dead-ended by Google, not by us.** The operator's Google account (a **personal**
  Gmail) is restricted to new **`AQ.`-prefix** API keys, which the `generativelanguage` API rejects
  with `401 ACCESS_TOKEN_TYPE_UNSUPPORTED` — on **every** endpoint/version and via the **official
  `google-genai` SDK** (all tested live). Confirmed a **known Google-side regression** (Aug 2026):
  Google staff stated *"AI Studio will now only generate Authentication Key (AQ) keys"*; the
  account has **no "Generative Language API"** to enable; **no workaround exists** (not billing, not
  a fresh project, not the SDK). Forum threads + Google's own reply confirm it.
- **Replaced with OmniVoice** (`k2-fsa/OmniVoice`, Apache-2.0): local on the GPU, **no key**, and
  **voice-clones** the Iapetus reference from a short clip. Operator confirmed the clone matches.
  This also fits the **offline-first** goal Gemini never did.
- **Default backend is now `omnivoice`**; `edge` and `gemini` remain selectable.
- **Speed calibrated by measurement** to hit the reference's **142 wpm** (C-047):
  `speed 1.0 → ~172 wpm, 0.89 → ~153, 0.82 → ~144, 0.80 → ~141`. **`DEFAULT_SPEED = 0.80`.**
- **Voice reference asset:** `~/.local/share/contentforge/voices/iapetus-reference.wav` (copied
  from the Gemini Iapetus sample) + `DEFAULT_REFERENCE_TEXT` (the ceiling-fan line it speaks).
  Overridable via `CONTENTFORGE_VOICE_REFERENCE`.
- **WeTextProcessing** installed (optional OmniVoice dep) for number normalization ("$150" →
  spoken). Used when present, skipped otherwise (never crashes a render).

### 2.2 Copy the approach, keep our own identity (copyright)
Operator's explicit steer: copy the **idea/technique/script-style/visual-approach** but be
different enough to not be a complete copy / avoid a strike. Concretely:
- **Palette: keep cream** `(240,232,216)` as *deliberate differentiation* — Mr. Finance's signature
  is **pale blue**; ours is cream. (Earlier I had tuned toward cream against a *mismatched*
  reference still; watching a real video showed the channel is pale-blue + single-word + simple
  icons. We keep cream on purpose.)
- **Accent colour: muted teal** `(38,122,118)`, deliberately **not** their red. Used on the chapter
  number — the one non-ink colour, our mark where theirs uses red on the focal figure.
- **Titles/descriptions: mirror the proven pattern** — operator's steer: "keep the same kind of
  titles/descriptions based on what works for them." Metadata prompt models "The Economics of
  Owning a [tangible business]" (42/42 of their titles; winners are businesses viewers have stood
  inside). Low copyright risk (short descriptive format).
- **Script voice/wording: ours.** Second-person demolition style, reveal structure, ~17-22 min
  (2500-3200 words), our own words, shapes rotate so no two videos share a skeleton.
- **No background music** — measured the reference at **-50 dB**: its speech gaps are real silence,
  so there is **no music bed**. We add none.

### 2.3 Everything reviewable before publish
Operator: "everything reviewable before actual publish… should not depend on publish." So `make`
now produces **metadata.json** and **thumbnail.png** as its own resumable stages; `publish` **only
uploads** what `make` already produced and refuses if any artefact is missing. Thumbnail was the
specific gap (it used to be built inside the publish flow, invisible until you committed to upload).

### 2.4 Model routing idea (deferred)
Operator suggested the pipeline could **switch models per-beat by expertise** (e.g. a stronger model
for figures, fast one for simple objects). **Deferred** until the FLUX/Qwen eval tells us which
model is good at what. The image model is already per-run config (`CONTENTFORGE_IMAGE_MODEL`);
per-beat routing is a clean extension.

### 2.5 LLM routing: **OmniRoute** (not Ollama)
- Evaluated local LLMs for the spec/metadata stages. **OmniRoute** (the user's local OpenAI-compat
  router) beat Ollama massively: `auto/fast` **5.4s** vs gemma4 **74s** for 3 beats; qwen builds
  timed out (they emit long chain-of-thought before a JSON array).
- **Default:** `CONTENTFORGE_LLM_BASE_URL=http://127.0.0.1:20128/v1`, `CONTENTFORGE_LLM_MODEL=auto/best-free`.
- **PORT TRAP (important):** OmniRoute's **API and dashboard are BOTH on 20128** (API at `/v1`,
  dashboard at `/`). **37777 is NOT OmniRoute** — it is a **claude-mem** server squatting that port.
  Earlier docs wrongly said 37777 was the dashboard; corrected. If a browser at 37777 says "not
  responding," that's claude-mem, not OmniRoute.
- OmniRoute **binds `0.0.0.0:20128` and currently accepts requests with no API key** — it is
  reachable on the LAN. A `CONTENTFORGE_LLM_KEY` (an OmniRoute access token, `sk-...`) is now set
  and accepted, but OmniRoute is **not enforcing** it (returns 200 without it too). Enforcement is a
  separate OmniRoute setting the user can enable.

---

## 3. Issues faced and how they were fixed (chronological-ish)

1. **Caption text stacked into the block below it** — `textbbox` measures drawn-ink extent, not line
   height. Fixed with `line_height()` using `font.getmetrics()` (ascent+descent).
2. **Pipeline was never wired** — every end-to-end render lived in a throwaway tmp script. Built the
   real `pipeline make` orchestrator with resumable stages.
3. **Palette 4× too saturated** vs reference (measured median sat 0.315 vs 0.079). Two-point chroma
   fit + flatten paper-grain + snap background to reference cream. (C-061/062.)
4. **Text floated on the background** — the reference letters onto a drawn **sheet**. Built
   `sheet.py`. Later found the reference's *dominant* frame is a single word top area, not a sheet —
   so heading-only beats use empty-space placement; sheet reserved for genuine checklists. (C-063.)
5. **`make` never wired script generation** — added `ensure_script` stage 0 (topic+sources → grounded
   validated narration).
6. **Subtitles missing** — added `.srt/.vtt` from the same shot timing; strip `[1]` citations from
   captions and the Gemini audio path (edge already stripped).
7. **Thumbnail built on refuted premise** — rewrote to compose a real frame + Bangers headline.
8. **OmniRoute wrong port / one bad heading killing a 20-beat chunk** — chunked spec at 20 beats,
   retry a failed chunk once, heading cap 3→4 words, model-agnostic.
9. **hermes sandbox couldn't run the pipeline** — a long saga (see §4). Ultimately made it capable.
10. **Diffusers `HF_HUB_OFFLINE=1` broke model loading** — diffusers 0.39 resolves the `fp16`
    variant via the Hub metadata API even with weights cached, so offline mode hard-fails
    (`OfflineModeIsEnabled`). **Removed `HF_HUB_OFFLINE` everywhere.** Weights still load from cache;
    only the tiny metadata check goes online (through the proxy).
11. **Gemini AQ-key 401** — see §2.1. Not fixable; switched to OmniVoice.
12. **6 GB VRAM: voice + image models can't coexist** — the first full render OOM'd at the draw
    stage because OmniVoice was still resident. Added `_GpuSpeaker.close()` (frees model +
    `torch.cuda.empty_cache()`), called by the pipeline after the audio stage.
13. **Thumbnail crashed a finished render** — used the 7-word SEO title, thumbnail caps at 5. Added
    `thumb_headline` (2-4 word hook, distinct from title) to metadata + truncate-not-raise backstop.
14. **Images were garbage** (the big one, see §5).
15. **omnivoice install broke the image stack** — it pulled `torchaudio 2.11.0` (CUDA 13) against
    torch 2.6+cu124. Fixed by pinning `torchaudio==2.6.0` (cu124). Also bumped transformers 4→5.14.1;
    verified sdxl-turbo + sd-turbo still load+generate under transformers 5.x. Image pipeline intact.

---

## 4. The hermes sandbox saga (making the Telegram agent able to run the pipeline)

The hermes agent runs **on the host** (pid, host venv) but executes shell commands **inside a Docker
sandbox** (`terminal.backend: docker`, image `nikolaik/python-nodejs:python3.11-nodejs20`). The
sandbox is on network **`scrape-internal`** (`internal=true` → **no default route to host**) and all
egress goes through **`scrape-proxy`** (tinyproxy, **default-deny** with a domain whitelist). So by
default the sandbox could reach **nothing** the pipeline needs.

What was done to make it capable (all **verified from inside the running container**, not inferred):
- **GPU passthrough:** installed `nvidia-container-toolkit` on the host (user ran the sudo commands),
  added `--gpus=all` to `terminal.docker_extra_args`. (Toolkit **first**, flag **second** — the flag
  fails every `docker run` without the toolkit.)
- **RAM:** raised `terminal.container_memory` **5120 → 12288** (sdxl-turbo offloads ~8-9 GB to system
  RAM; 5 GB OOMs).
- **Reach OmniRoute:** the sandbox has no host route + default-deny proxy. Fixed with **one narrow
  `ufw` rule** (user ran it): `sudo ufw allow from 172.21.0.0/16 to 172.21.0.1 port 20128 proto tcp`
  (scrape-egress subnet → host gateway → OmniRoute API port only), **plus** whitelisting the host in
  the proxy: added `^172\.21\.0\.1(:20128)?$` and `^generativelanguage\.googleapis\.com$` to
  `~/.local/share/scrape-egress/whitelist` (tinyproxy needs a **restart**, not just SIGHUP). Inside
  the sandbox the LLM base URL is **`http://172.21.0.1:20128/v1`** (the bridge gateway = host).
- **Assets copied into the sandbox home** (`~/.hermes/sandboxes/docker/default/home` = `/root` in the
  container), because the container is root-owned (do the copy **via a root container** mounting both
  the sandbox home and the host assets read-only — a normal `cp` gets permission-denied):
  HF model cache (8.9 GB, sd-turbo + sdxl-turbo), Real-ESRGAN, fonts, and the contentforge source.
- **Installed in the sandbox** (`pip install --user` → persists in `/root/.local`): torch+diffusers+
  contentforge (`torch 2.13.0+cu130` inside the sandbox), and a **static ffmpeg** binary in
  `/root/.local/bin` (host ffmpeg is dynamically linked, can't just be copied).
- **`docker_env` set** (in `~/.hermes/config.yaml` under `terminal.docker_env`): PATH,
  `CONTENTFORGE_LLM_BASE_URL=http://172.21.0.1:20128/v1`, `CONTENTFORGE_LLM_MODEL=auto/best-free`,
  `CONTENTFORGE_VOICE_BACKEND=gemini` (⚠️ **should be updated to `omnivoice`**),
  `CONTENTFORGE_VOICE=Iapetus` (⚠️ stale — omnivoice uses the reference wav, not a voice name),
  `CONTENTFORGE_IMAGE_MODEL=stabilityai/sdxl-turbo`, `GEMINI_API_KEY` (dead AQ key — irrelevant now),
  `CONTENTFORGE_LLM_KEY` (the OmniRoute token). **`HF_HUB_OFFLINE` was removed** (broke diffusers).
- **Verified inside a container mirroring the config:** `pipeline doctor` all green; spec generation
  through OmniRoute over the bridge; a real 768×432 image drawn on the passed-through GPU.
- **`contentforge-video` hermes skill** written at `~/.hermes/skills/contentforge-video/SKILL.md` so
  the agent knows it can run `pipeline make`/`publish` inside its own sandbox (no mailbox needed).

**⚠️ Sandbox work is INCOMPLETE for OmniVoice:** the sandbox was set up when Gemini was the voice. It
does **not** yet have: OmniVoice installed, the `k2-fsa/OmniVoice` model cached, the Iapetus reference
wav, WeTextProcessing, `soundfile`, or the `sdxl-base`/LoRA/FLUX/Qwen weights if we change the image
model. `docker_env` still says `gemini`. **This must be redone for OmniVoice before the agent can
make a video** (copy reference wav + model, pip install omnivoice+soundfile, set
`CONTENTFORGE_VOICE_BACKEND=omnivoice`). Same asset-copy pattern as §4.

**Security notes (do not lose):** During this session, three secrets leaked into the transcript via a
config-file injection / a bad shell expansion: the **tinyproxy `scraper` password**, the **old Gemini
key**, and the **OmniRoute token** appeared in logs. **Rotate all three** if the transcript is ever
shared. OmniRoute also accepts unauthenticated LAN requests (enforcement off).

---

## 5. The image-quality investigation (the current focus)

**The first full render's images were garbage** — sdxl-turbo drew a **garbled kitchen scale** for
"a ceiling fan above a thermometer", with fake numbers and random objects; a **7-fingered mangled
hand** for "a bare human forearm". Root causes and fixes (all committed):

1. **Subjects too complex.** The spec wrote compound scenes; sdxl-turbo collapses them. Now the spec
   writes **ONE simple object, 3-6 words** ("an electric desk fan").
2. **4 steps too few** → **`TURBO_STEPS = 8`** (~10s/image).
3. **Weak negative prompt** → added `numbers, digits, dial, gauge, clock, cluttered, multiple
   objects, deformed hands, extra fingers, realistic face, person`.
4. **Realistic anatomy is fatal.** Mr. Finance uses **stick figures** (C-058), never realistic
   people. Spec now forbids realistic people/body parts and asks for **"a simple black stick
   figure"** when a person is needed; prefers objects.
5. **House style** → "one single object centered, minimal, lots of empty space".
6. **`COMPOSITION` emptied** — it said "subject on the right" for a sheet layout that no longer
   exists, and overran CLIP's 77-token limit.
7. **Heading placement** — a dead-centre heading landed on a centred subject (the fan). Heading-only
   beats now use **measured empty-space placement** (`place_blocks`), so words go where the drawing
   left room (a side/corner), the way the reference does. Chapter-only beats draw just the corner
   marker.

**Result:** a clean, coherent ceiling fan with the heading clear of it, and simplified stick-figure
people (no mangled hands). sdxl-turbo still over-draws sometimes (a crowd instead of one figure) —
a model ceiling.

**Model evaluation (operator wanted to "pick by eye" among better offline models):**
- Compared **sdxl-turbo (baseline+fixes)** vs **sdxl-turbo + ColoringBook LoRA** vs **sdxl-base +
  ColoringBook LoRA** vs **PixArt-Sigma** on a fan (object) and a stick figure (person).
- **Finding: the LoRA prettifies *objects* but wrecks *subject accuracy on people*** — it ignores
  "stick figure" and draws bottles/desk scenes. base+LoRA is slower AND drifts. PixArt didn't run
  (tokenizer download broken). **None clearly beat the fixed baseline.**
- Operator then asked to try **Wan / Hunyuan / Seedance2**. Research verdict: those are **video**
  models — Wan 2.2 runs on 6 GB only via aggressive GGUF at 480p/minutes-per-clip (video gen is an
  architecture change + overkill for a still-line-art style); HunyuanVideo needs 14 GB+; **Seedance
  is API/closed (not offline)**. The real win is **better *image* models via GGUF quantization**:
  **FLUX.1-schnell** and **Qwen-Image**, both of which fit 6 GB quantized (tool: **Wan2GP**, or
  diffusers-GGUF directly).
- **CURRENTLY RUNNING (background, detached with setsid, survives interruptions):** downloading **Q8
  GGUF** (operator: "we don't want quality loss" → Q8 is effectively lossless) of FLUX.1-schnell
  (`city96/FLUX.1-schnell-gguf` + FLUX components from ungated `cocktailpeanut/xulf-schnell`) and
  Qwen-Image (`city96/Qwen-Image-gguf` + open `Qwen/Qwen-Image` components), then auto-generating the
  fan+figure test with each. ~50 GB of downloads on a **slow, flaky** network (the download processes
  kept dying; now wrapped in a 20-retry resume loop). Generation is ~1-3 min/image on 6 GB.
  - **Scripts:** `<scratch>/gen_flux.py`, `<scratch>/gen_qwen.py`; downloader `<scratch>/robust_dl.py`
    (logs `FLUX_READY`/`QWEN_READY`/`ALL_READY`); orchestrator `<scratch>/orch2.sh` (waits then
    generates; logs `<scratch>/genrun2.log`, done marker `ORCH2_DONE`).
  - `<scratch>` = `/tmp/claude-1000/-home-amardeep/35a61c40-e916-459f-b213-f713293bccc6/scratchpad`.
    **NOTE:** scratchpad is session-temp and **was wiped once** at a usage-limit interruption — the
    earlier comparison images were lost and had to be regenerated. If it's wiped again, regenerate
    from the scripts (models are cached in `~/.cache/huggingface`).
  - **diffusers 0.39 supports** `FluxPipeline`+GGUF and `QwenImagePipeline`+GGUF; `gguf`, `peft`,
    `tiktoken` all installed.

**Decision pending:** view the FLUX and Qwen samples vs baseline; pick the image model (possibly
per-beat routing per §2.4); or keep the fixed sdxl-turbo baseline if the quantized models aren't
worth the ~1-3 min/image (a 200-shot video → hours vs ~30 min).

---

## 6. Environment / config reference

**Host `.env`** (for host runs; the agent can't read/write `.env` — permission-denied):
```
CONTENTFORGE_LLM_BASE_URL=http://127.0.0.1:20128/v1
CONTENTFORGE_LLM_MODEL=auto/best-free
CONTENTFORGE_LLM_KEY=<omniroute token>
CONTENTFORGE_VOICE_BACKEND=omnivoice
CONTENTFORGE_IMAGE_MODEL=stabilityai/sdxl-turbo
```
Load with `set -a && . ./.env && set +a`.

**hermes config** `~/.hermes/config.yaml` → `terminal.docker_env` (see §4; **update voice to
omnivoice**). `terminal.docker_extra_args: [--network=scrape-internal, --gpus=all]`,
`container_memory: 12288`.

**Optional extras** in `pyproject.toml`: `[gpu]` (torch/diffusers/…), `[publish]` (google-auth OAuth),
`[voice]` (omnivoice, soundfile).

**Host assets (offline):** models in `~/.cache/huggingface`; Real-ESRGAN in
`~/.local/share/realesrgan`; fonts in `~/.local/share/fonts/contentforge`; voice reference in
`~/.local/share/contentforge/voices/iapetus-reference.wav`.

**Reference material:** Mr. Finance video data in `docs/evidence/2026-07-30-mrfinance-videos.json`;
the ledger `docs/findings/claims-ledger.md` (C-047 pace, C-055 format, C-058 look, C-061/062/063
palette+sheet). The `watch` skill was used to actually view/hear a real Mr. Finance video (the gym
one, id `4nYkN0wTi2Q`).

---

## 7. Outstanding work (priority order)

1. **Finish the image-model eval** (running): view FLUX vs Qwen (Q8) vs baseline; decide model,
   possibly per-beat routing. Wire the choice into `runtime.illustrator`/`CONTENTFORGE_IMAGE_MODEL`.
2. **Merge PR #2** to `master` (operator's stated sequence: fix images → merge → hermes).
3. **Redo the hermes sandbox for OmniVoice** (§4 ⚠️): install omnivoice+soundfile+WeTextProcessing in
   the sandbox, copy the OmniVoice model + Iapetus reference wav, set `docker_env` voice to
   `omnivoice`, whitelist nothing new (omnivoice is offline once cached). Then verify a full
   `pipeline make` inside the actual hermes container.
4. **YouTube OAuth** for `publish` (one-time, host, personal Gmail; `docs/setup/publishing.md`).
5. **Sync the main checkout** after merge (worktree work propagates to `master`).
6. **Rotate the three leaked secrets** if the transcript is shared (tinyproxy password, old Gemini
   key, OmniRoute token).

## 8. Things to NOT re-litigate (already decided/measured)

- Voice = OmniVoice (Gemini is Google-broken). Pace = 0.80. Palette = cream (deliberate). Accent =
  teal. No music. Titles = mirror "The Economics of Owning a [X]". LLM = OmniRoute on **20128**
  (37777 is claude-mem). `HF_HUB_OFFLINE` must stay **unset**. torchaudio pinned **2.6.0** (cu124).
  Subjects must be **one simple object / stick figures**, never realistic anatomy. `make` produces
  everything; `publish` only uploads.

---

## 9. UPDATE (later same session) — image-model eval hit walls; OPEN DECISION

The "better image model" evaluation (§5) was pursued hard and hit **wall after wall**. Current
honest state:

**What works:** the **fixed sdxl-turbo baseline** (simple single-object subjects, 8 steps, hard
negative prompt, stick-figures, empty-space heading placement) produces **coherent, on-subject,
clean line art** at ~10 s/image. It is committed and produced a real end-to-end video. This is the
fallback and it is good enough to ship.

**What was tried and why each failed / is costly:**
- **sdxl-turbo + ColoringBook LoRA** and **sdxl-base + ColoringBook LoRA**: LoRA prettifies
  *objects* but **wrecks subject accuracy on people** (drew bottles / a desk scene instead of a
  stick figure). base+LoRA also slower (~28 s) and drifts. Not worth it. (LoRAs downloaded:
  `artificialguybr/ColoringBookRedmond-V2`, `LineAniRedmond-LinearMangaSDXL-V2`.)
- **PixArt-Sigma**: broken — its T5 `spiece.model` tokenizer mis-parses as tiktoken; didn't run.
- **Wan / HunyuanVideo / Seedance2** (operator asked): these are **video** models. Wan 2.2 on 6 GB
  = 480p + minutes/clip + architecture change (overkill for still line-art); HunyuanVideo needs
  14 GB+; **Seedance is API/closed, not offline**. Rejected.
- **FLUX.1-schnell Q8 GGUF via diffusers-direct**: the official repo is **gated**; the GGUF
  transformer loads, but assembling the pipeline needs the FLUX **components** (T5-xxl, CLIP-L, VAE,
  tokenizers) from an **ungated** diffusers repo — the mirror tried (`cocktailpeanut/xulf-schnell`)
  turned out **empty** (only `.no_exist` markers). Real FLUX-schnell transformer config was
  hand-written (guidance_embeds=false, 19 layers, 38 single layers). Still need real ungated
  components — **`Freepik/flux.1-lite-8B`** is open with `model_index.json` and shares FLUX's
  standard T5/CLIP/VAE, so its components + our schnell GGUF transformer *should* work
  (`FluxPipeline.from_pretrained("Freepik/flux.1-lite-8B", transformer=<gguf>)`). A background
  download of those components was started (`<scratch>/dl_fluxcomp.py`) — **not verified to work**.
- **Qwen-Image Q8 GGUF via diffusers-direct**: uses the **open** `Qwen/Qwen-Image` for components
  (has everything), transformer config from `Qwen/Qwen-Image` `transformer/`. **BLOCKED** by
  **`KeyError: None` in `diffusers/quantizers/gguf/utils.py` (`GGML_QUANT_SIZES[quant_type]`)** —
  **diffusers 0.39 does not recognise the Qwen-Image GGUF's quant types.** This is a diffusers/gguf
  version incompatibility, not a download problem.

**Downloads already on disk (reusable, ~126 GB HF cache):** FLUX.1-schnell Q8 GGUF (~12.5 GB, at
`city96--FLUX.1-schnell-gguf/.../flux1-schnell-Q8_0.gguf`), Qwen-Image Q8 GGUF (~20 GB, at
`city96--Qwen-Image-gguf/.../qwen-image-Q8_0.gguf`), `Qwen/Qwen-Image` components, SDXL-base, PixArt,
the two LoRAs. **Do not delete these until the model decision is final** — Wan2GP would reuse the
same GGUF files.

**Tooling reality:** **Wan2GP** (`deepbeepmeep/Wan2GP`, cloned to `<scratch>/Wan2GP`) is the tool the
operator asked for and is *built* for GGUF FLUX/Qwen on low VRAM — BUT it pins **diffusers 0.36 /
transformers 4.54 / numpy 2.1**, which **conflict with and would break** the working contentforge
env (transformers 5.14, diffusers 0.39). **It must live in its own isolated venv.** It is also a
**Gradio UI** app (headless scripted single-image A/B is fiddly) and primarily a video tool.

### THE OPEN DECISION (operator to pick — resume here)

> "FLUX/Qwen setup keeps hitting walls on 6 GB. How do you want to proceed?"

- **Option A — Ship fixed sdxl-turbo, move on (RECOMMENDED for progress).** The baseline works, is
  coherent and fast. Merge PR #2, finish the hermes-for-OmniVoice setup (§4 ⚠️), then do the cleanup
  pass. Revisit better image models later as a focused project, ideally on a bigger GPU.
- **Option B — Isolated Wan2GP venv, keep pursuing.** Build a separate venv for Wan2GP (won't touch
  the working pipeline), reuse the downloaded GGUF weights, work out headless FLUX/Qwen generation.
  More hours, uncertain payoff, ~1–3 min/image on 6 GB (a 200-shot video → hours).
- **Option C — Try upgrading diffusers in a throwaway venv.** A newer diffusers may load the Qwen
  GGUF (fix the `KeyError: None`). Faster than Wan2GP if it works; do it in a throwaway venv first so
  it can't break the working stack.

### 10. CLEANUP PASS (do once the model decision is final — operator asked for this)

Reclaim disk / remove what the final choice doesn't need:
- **HF model weights** (biggest — cache ~126 GB): delete the **losers**. If A wins: remove FLUX GGUF,
  Qwen GGUF + `Qwen/Qwen-Image` components, SDXL-base, PixArt, both LoRAs (~90 GB). Keep sd-turbo +
  sdxl-turbo (the pipeline default) + OmniVoice model. `rm -rf ~/.cache/huggingface/hub/models--<repo>`.
- **pip packages** not needed by the winner: `peft`, `tiktoken`, `gguf` (only for the GGUF eval);
  keep `omnivoice`, `soundfile`, `WeTextProcessing`, `torch/diffusers/transformers`.
- **Scratch eval artefacts:** `<scratch>/compare/`, `cmp.py`, `compare*.py`, `gen_*.py`,
  `dl_*.py/.log`, `robust_dl*`, `orch*.sh`, `Wan2GP/` (if not adopted), `flux_cfg/`.
- Verify tests still pass and `pipeline doctor` is green after any removal.
- `<scratch>` = `/tmp/claude-1000/-home-amardeep/35a61c40-e916-459f-b213-f713293bccc6/scratchpad`
  (session-temp; may be wiped — the eval scripts and logs there are disposable).

**Packages installed this session (host venv):** `omnivoice, soundfile, WeTextProcessing, peft,
tiktoken, gguf, google-genai` (google-genai only proved Gemini is dead — removable). `torchaudio`
pinned to **2.6.0** (cu124) — must stay pinned.
