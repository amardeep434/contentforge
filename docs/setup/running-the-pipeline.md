# Making a video, start to finish

One command builds a whole video from a script. This page explains what it needs
first, what it does, what it leaves behind, and how to stop and resume safely.

Written for someone setting this up for the first time. If you only want image
generation working, read
[local-image-generation.md](local-image-generation.md) instead — this page
assumes it is already done.

---

## 0. The command

The command is `pipeline`, a small console script installed when you run
`pip install -e .` in the repo. Everything on this page starts with it:

```bash
pipeline make my-video --script-file script.txt
```

**Gotcha:** `python -m contentforge.cli ...` does **not** work — the module has
no `__main__` guard, so it silently exits doing nothing. If for some reason you
cannot use the installed `pipeline` script, invoke it like this instead:

```bash
python -c "import sys; from contentforge.cli import main; sys.exit(main())" make my-video --script-file script.txt
```

Everywhere below just uses `pipeline`.

---

## 1. What has to be installed

Run this first. It checks everything and tells you what is missing:

```bash
pipeline doctor
```

A healthy machine prints something like:

```
gpu       NVIDIA GeForce RTX 3060 Laptop GPU, 6.4 GB VRAM, torch 2.5.1
upscaler  found
fonts     found
ffmpeg    /usr/bin/ffmpeg
ffprobe   /usr/bin/ffprobe
llm       configured
```

Anything reading `MISSING` or `NOT configured` is fixed below.

| Line | If it is missing |
|---|---|
| `gpu` | [local-image-generation.md](local-image-generation.md) §1–2 |
| `upscaler` | [local-image-generation.md](local-image-generation.md) §7 |
| `fonts` | [local-image-generation.md](local-image-generation.md) §8 |
| `ffmpeg` / `ffprobe` | `sudo apt install ffmpeg` |
| `llm` | §2 below |
| voice model | [local-voice.md](local-voice.md) |

**`doctor` does not check everything.** It does not verify the image model's
pre-quantised qint8 weights, nor the OmniVoice model files. If either is
missing the render does not guess — it fails loudly at the stage that needs it,
with a clear message telling you exactly what to build or install. So a green
`doctor` plus the voice and image assets from their two pages is the full
picture.

---

## 2. Settings

Everything is read from the environment, so nothing prompts and the pipeline can
run unattended. **The defaults are baked in.** On a machine where the local
services (LLM, voice, GPU) are already up, you need **no `.env` at all** — the
values below are what the pipeline already assumes.

```bash
# Planning the visuals. Any OpenAI-compatible endpoint.
CONTENTFORGE_LLM_BASE_URL=http://127.0.0.1:20128/v1   # OmniRoute
CONTENTFORGE_LLM_MODEL=auto/best-free
CONTENTFORGE_LLM_KEY=                    # blank is fine for a local server

# Voice — local, offline, no API key. See local-voice.md.
CONTENTFORGE_VOICE_BACKEND=omnivoice     # or: edge  (low-quality fallback)

# Image model — Qwen-Image on the GPU. See local-image-generation.md.
CONTENTFORGE_IMAGE_MODEL=qwen
CONTENTFORGE_IMAGE_WIDTH=768             # generation size, NOT output size
CONTENTFORGE_IMAGE_HEIGHT=432            # output is always 1920x1080
```

If you do keep a `.env`, load it into your shell before running anything:

```bash
set -a && . ./.env && set +a
```

**Voice is OmniVoice** — local, offline, and needs no API key. You do not set
any `GEMINI_API_KEY`; there is no Gemini backend any more. `edge` is a
selectable low-quality fallback if OmniVoice is unavailable. See
[local-voice.md](local-voice.md) for the model files.

**`CONTENTFORGE_IMAGE_WIDTH` is the size frames are drawn at, not the size they
come out at.** Output is always 1920x1080. Frames are generated at 768x432
because a larger generation size runs a 6 GB card out of memory, then upscaled
4x and fitted to 1080p.

### Choosing an image model

The default is **`qwen`** (Qwen-Image) and that is what finals are made with.
The others are draft-only:

- `flux` — faster, lower quality (~19 s/image).
- `stabilityai/sdxl-turbo`, `stabilityai/sd-turbo` — fastest (~10 s/image),
  lowest quality.

Use them with `--model` or `CONTENTFORGE_IMAGE_MODEL` for a quick **draft** pass
to check pacing and framing before committing to the slow Qwen run. Do **not**
mix models in a final: one video must be one consistent look, so a final is one
model start to finish.

```bash
pipeline make my-video --script-file script.txt --model flux   # fast draft
```

### Choosing an LLM

**OmniRoute is the default.** It already runs here, it speaks the OpenAI API, and
one base URL covers both this machine and hermes. **Both the API and the
dashboard are on port 20128** (`http://localhost:20128`); the API answers at
`/v1`, the dashboard at `/`. Nothing OmniRoute runs on 37777 — if a browser
there says "not responding", that port belongs to another service (claude-mem
was squatting it during this build).

```bash
omniroute health                 # is the server up
curl -s localhost:20128/v1/models | head    # what it routes to (219 models here)
```

Measured on this machine, planning three beats end to end:

| endpoint | model | time |
|---|---|---|
| OmniRoute | `auto/fast` | **5.4 s** |
| OmniRoute | `auto/cheap` | 5.6 s |
| OmniRoute | `auto/best-free` | 8.6 s |
| Ollama | `gemma4:latest` | 74 s |
| Ollama | `qwen3.6:35b-a3b` | timed out at 180 s |
| Ollama | `qwen3.5:latest-32k` | timed out at 110 s |

`auto/best-free` is the default: free, and 9x faster than the best local option.

**If you use Ollama directly instead**, pick a model that does not think out
loud. The qwen builds emit a long chain of thought before answering, which is
wasted on a task whose output is a JSON array — that is why they time out above.
Ollama serves an OpenAI-compatible API at `/v1`, so it needs no adapter:
`http://127.0.0.1:11434/v1`.

The spec stage is chunked at 20 beats per call, so a 200-beat script is ten
calls — a few minutes through OmniRoute, 20-40 through Ollama, all of it before
any GPU work begins.

---

## 3. Making a video

Write the narration to a file — plain prose, one idea per sentence — then:

```bash
pipeline make ceiling-fans --script-file my-script.txt
```

`ceiling-fans` is the run name. Everything lands in `data/videos/ceiling-fans/`.

Check the beats before spending hours of GPU time on them:

```bash
pipeline make ceiling-fans --script-file my-script.txt --dry-run
```

That splits the script and prints what each shot will cover, without generating
anything.

### What it does

`make` runs eight stages, in order:

```
script  →  spec  →  audio  →  draw  →  letter  →  render  →  metadata  →  thumbnail
```

- **script** — the prose you wrote (`--script-file`), OR generated from
  `--topic` + `--source` URLs (grounded in those sources and checked for
  verbatim lifting), OR a cached `script.txt` from an earlier run.
- **spec** — one LLM call per 20 beats: what to draw and what to letter for each
  beat.
- **audio** — one narrated clip per beat (OmniVoice), each timed with `ffprobe`.
- **draw** — one illustration per beat on your GPU (Qwen by default). **This is
  the slow stage:** roughly **4 min/image** with Qwen, so ~150 images is about
  **10 hours** — an overnight or background batch. Draft first with a fast
  `--model` to check pacing: FLUX is ~19 s/image, sdxl-turbo ~10 s/image.
- **letter** — upscale to 1080p (Real-ESRGAN), correct the palette, then draw
  the sheet and add the lettering.
- **render** — ffmpeg, one shot per beat timed by the measured audio, plus
  `subtitles.srt` / `subtitles.vtt` from the same timing.
- **metadata** — title, description, tags and thumbnail headline from the LLM.
  Reviewable before you publish.
- **thumbnail** — a 1280x720 image built from a finished frame.

Beats are sentences (very short ones are merged), so a 2500–3200-word script is
roughly **150 images**.

`make` now produces **everything**, including `metadata.json` and
`thumbnail.png`, so by the time it finishes there is nothing left to generate —
`publish` only uploads what you have already reviewed.

To generate the script instead of writing it:

```bash
pipeline make ceiling-fans --topic 'how ceiling fans work' \
    --source https://en.wikipedia.org/wiki/Ceiling_fan \
    --source https://example.com/another-primary-source
```

Every factual claim in the generated script must trace to a source; a topic with
no `--source` is refused rather than invented.

To publish the result, see [publishing.md](publishing.md):

```bash
pipeline publish ceiling-fans          # private by default, asks before uploading
```

### What it leaves behind

```
data/videos/ceiling-fans/
  script.txt      what you wrote, or what was generated
  sources.json    the primary sources a generated script was grounded in
  spec.json       the visual plan - readable, and editable
  manifest.json   every shot with its subject, lettering and duration
  status.json     machine-readable per-stage state, plus what remains
  run.log         human, timestamped, append-only trail of every stage event
  audio/          one wav per beat
  raw/            illustrations at generation size
  frames/         finished 1920x1080 frames
  video.mp4
  subtitles.srt   timed captions, from the same shot timing
  subtitles.vtt
  metadata.json   title, description, tags — review before publishing
  thumbnail.png   1280x720, built from a finished frame
  published.json  written after a successful upload
```

`status.json` records each stage as `pending`, `running`, `ok`, `skipped`,
`failed` or `stopped`, with the error and what still remains. `run.log` is the
plain-English version: a timestamped line for every stage event, only ever
appended to, so the record of a run survives a crash.

---

## 4. Resuming, and stopping safely

The draw stage alone can run overnight, so stopping and resuming is a normal
part of using this — not just crash recovery.

**Between stages:** a stage is skipped if its artefact already exists. Rerunning
after a crash picks up from the first stage that has not finished.

**Within a stage:** finished items are kept too. Audio clips, drawn images and
lettered frames already on disk are **not** redone. So if you stop part way
through the ~10-hour draw stage, every image finished so far stays, and the
rerun continues from the first unfinished one.

### Stopping by hand

Press **Ctrl-C** (or send `SIGTERM`). The pipeline finishes the **current**
item first — so no half-written file is ever left — and then stops cleanly:

- `status.json` records the stage as `"stopped"` (not `failed`), with what
  remains.
- `run.log` gets a `STOPPED` line.
- the CLI prints `stopped safely… resume by re-running: pipeline make <slug>`
  and exits `130`.

Re-running resumes from the first unfinished item. A **second** Ctrl-C
hard-kills immediately, without waiting for the current item.

```bash
pipeline make ceiling-fans          # resumes exactly where it stopped
```

### Memory is always freed

On any exit — graceful stop or hard kill — the OS frees all GPU and CPU memory.
And across stages the pipeline frees models it no longer needs: the voice model
is released before drawing, and the image model is released after drawing, so a
~36 GB image model is not still held in memory during rendering.

### Forcing a redo

```bash
pipeline make ceiling-fans --force draw          # just the illustrations
pipeline make ceiling-fans --force draw --force letter
pipeline make ceiling-fans --force all
```

Stage names: `script`, `spec`, `audio`, `draw`, `letter`, `render`, `metadata`,
`thumbnail`, `all`. A forced stage clears **its own** outputs first and then
redoes them; finished items in other stages are kept.

**Editing `spec.json` by hand is expected.** It is the cheapest place to fix a
video: change a subject or a heading, then `--force draw --force letter --force
render` and only those stages rerun.

If you edit `script.txt` so it has a different number of sentences, the next run
refuses rather than pairing the wrong picture with the wrong words. Rerun with
`--force spec`.

---

## 5. When something fails

Every failure names the stage. Between them, `status.json` and `run.log` capture
exactly what worked, what failed (with the error) and what remains — so you
never lose the record or the finished work. The common ones:

**`CUDA out of memory`** — the pipeline already sets
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` for you and frees each model
between stages, so a normal render fits on a dedicated 6 GB card. If it still
OOMs, something else is holding the GPU — a browser playing video keeps ~2 GB.
Close it and rerun; finished work is kept.

**`ffprobe not found`** — `sudo apt install ffmpeg`. Durations are measured from
the audio files, never assumed, so this is not optional.

**`font missing at ...`** — [local-image-generation.md](local-image-generation.md)
§8. The lettering is the content; the pipeline will not silently render frames
without it.

**`visual spec has N entries for M beats`** — the model returned the wrong
number. Rerun with `--force spec`.

**`the lettering needs a NNNpx sheet but only NNNpx is available`** — a heading
or checklist item is too long. Shorten it in `spec.json` and rerun `letter`.

---

## 6. Running it under hermes — deployment checklist

The pipeline runs inside the hermes Docker sandbox, provisioned for the current
stack (Qwen + OmniVoice). **This has been done and verified** — a full video was
rendered end to end inside the sandbox (Qwen images, OmniVoice narration,
nvidia-Vulkan upscale, `video.mp4` on the host). The one-time provisioning is
scripted in `~/hermes-provision.sh`; the checklist below is what it sets up, so a
rebuild or a second machine is reproducible.

**Renders are launched detached and polled, not run as a blocking command.** A
Qwen video is ~10 h and a hermes terminal command times out in minutes, so the
agent runs `setsid pipeline make … --root /root/videos &` and polls
`status.json` (see the `contentforge-video` / `contentforge-render-status`
skills). `terminal.lifetime_seconds` is raised so the container survives the run,
and `daemon_term_grace_seconds` is raised so a SIGTERM can finish the current
image before stopping.

1. **GPU passthrough.** `nvidia-container-toolkit` on the host, then
   `--gpus=all` in the hermes `terminal.docker_extra_args`. Without the toolkit
   the flag fails every `docker run`, so install the toolkit first, add the flag
   second.

2. **Custom sandbox image (needed for the upscaler).** Set
   `terminal.docker_image: contentforge-sandbox:latest`, built from
   `~/hermes-sandbox.Dockerfile` (base image + `libvulkan1 libglvnd0 libgl1
   libegl1 libglx0 mesa-vulkan-drivers` + a static `ffmpeg`/`ffprobe`).
   **Why:** Real-ESRGAN (`realesrgan-ncnn-vulkan`) needs a Vulkan loader **and**
   the GLVND dispatch layer. The nvidia-container-toolkit injects nvidia's vendor
   libs (`libGLX_nvidia`, `libEGL_nvidia`) at runtime but **not** the GLVND
   dispatch libs (`libEGL.so.1`, `libGLX.so.0`) that nvidia's combined lib
   dlopens at init — without `libglvnd0` the nvidia Vulkan ICD returns NULL
   (`Could not get vkCreateInstance`) and the upscaler finds no GPU. With it, the
   passed-through nvidia GPU does the upscale at ~2.8 s/image, byte-identical to
   the host. mesa is kept as a CPU (llvmpipe) fallback.

3. **Memory — `container_memory` must be ~`40960` (40 GB).** Qwen's inference
   peak is ~36 GB of *system* RAM, because the model is streamed from CPU RAM.
   The old `12288` was sized for sdxl-turbo and will get Qwen **SIGKILLed**
   mid-draw — a cgroup RAM kill is uncatchable, so no graceful stop can save it.
   The host has 58 GB, so 40 GB fits.

4. **Host-mounted run directory.** Bind-mount the `--root`/`data` directory into
   the container (`-v /home/amardeep/hermes-videos:/root/videos`) so the assets
   are reviewable from the host as they land; the agent runs
   `pipeline make … --root /root/videos`.

5. **Stop with SIGTERM, not SIGKILL.** hermes must send `SIGTERM` to stop a
   render gracefully. `SIGKILL` still frees memory, but it skips the "finish the
   current item" grace, so it can leave the current item half-done.

6. **Copy the assets into the sandbox** (they are not downloaded there) — the
   sandbox home is root-owned, so copy via a root container mounting it:
   - the pre-quantised **qint8 weights** (~32 GB),
   - the `Qwen/Qwen-Image` and Freepik component directories,
   - the **OmniVoice** model plus the Iapetus reference wav,
   - `pip install --user` the **exact host versions** into `/root/.local` (the
     sandbox is python3.11, the host 3.13; the qint8 files are python-agnostic):
     `torch==2.6.0 torchaudio==2.6.0` (cu124), `diffusers==0.39.0
     transformers==5.14.1 accelerate safetensors mmgp optimum-quanto omnivoice
     soundfile WeTextProcessing`, then `-e` the contentforge source.
   (`libvulkan`, `libglvnd0` and `ffmpeg` come from the custom image, step 2.)

7. **Set `docker_env`:**
   - `CONTENTFORGE_VOICE_BACKEND=omnivoice`
   - `CONTENTFORGE_VOICE_REFERENCE=/root/.local/share/contentforge/voices/iapetus-reference.wav`
   - `CONTENTFORGE_IMAGE_MODEL=qwen`
   - `CONTENTFORGE_LLM_BASE_URL=http://172.21.0.1:20128/v1` (the bridge gateway
     to OmniRoute)
   - Do **not** set `HF_HUB_OFFLINE` — it breaks fp16-variant loading under
     diffusers (see local-image-generation.md). Weights still load from the
     copied cache; only the tiny metadata check goes online, through the proxy.

8. **Reaching OmniRoute.** The sandbox has no route to the host and a
   default-deny egress proxy. One `ufw` rule allows the egress subnet to reach
   the API port, and the OmniRoute host is added to the proxy whitelist. That is
   why the base URL above is the bridge gateway (`172.21.0.1`) rather than
   `127.0.0.1`.

`pipeline doctor` is the first thing to run inside the container when something
misbehaves. It probes the LLM endpoint rather than merely checking that a
variable is set, so it distinguishes "the GPU was not passed through" from "the
fonts are not mounted" from "the LLM URL points at the dashboard port" — which
otherwise all present as the same failed render. Remember it does **not** verify
the qint8 weights or the OmniVoice model (§1); those fail at their own stage
with a clear message.
