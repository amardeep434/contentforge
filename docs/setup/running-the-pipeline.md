# Making a video, start to finish

One command builds a whole video from a script. This page explains what it needs
first, what it does, and what to do when a stage fails.

Written for someone setting this up for the first time. If you only want image
generation working, read
[local-image-generation.md](local-image-generation.md) instead — this page
assumes it is already done.

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

---

## 2. Settings

Everything is read from the environment, so nothing prompts and the pipeline can
run unattended. Add these to your `.env`:

```bash
# Planning the visuals. Any OpenAI-compatible endpoint.
CONTENTFORGE_LLM_BASE_URL=http://127.0.0.1:20128/v1
CONTENTFORGE_LLM_MODEL=auto/best-free
CONTENTFORGE_LLM_KEY=                    # blank is fine for a local server

# Optional - these are the defaults.
CONTENTFORGE_VOICE_BACKEND=gemini        # or: edge
CONTENTFORGE_VOICE=Iapetus
CONTENTFORGE_IMAGE_MODEL=stabilityai/sdxl-turbo
CONTENTFORGE_IMAGE_WIDTH=768             # generation size, NOT output size
CONTENTFORGE_IMAGE_HEIGHT=432            # output is always 1920x1080
```

Load them into your shell before running anything:

```bash
set -a && . ./.env && set +a
```

`GEMINI_API_KEY` is required, because `gemini` is the default voice backend —
six edge-tts voices were rejected by a listener as obviously synthetic (C-049).
Set `CONTENTFORGE_VOICE_BACKEND=edge` if you would rather not depend on a key.

**`CONTENTFORGE_IMAGE_WIDTH` is the size frames are drawn at, not the size they
come out at.** Output is always 1920x1080. Frames are generated at 768x432
because 1024x576 runs a 6 GB card out of memory, then upscaled 4x and fitted to
1080p.

### Choosing an LLM

**OmniRoute is the default.** It already runs here, it speaks the OpenAI API, and
one base URL covers both this machine and hermes. Its dashboard is on **37777**;
its API is on **20128** — a different port, which is the thing that wastes an
afternoon if you assume otherwise.

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

### Running the whole pipeline inside the hermes sandbox

**The sandbox runs the full pipeline** — this was made to work deliberately, and
each stage is verified from inside the running container, not inferred from the
host:

```
pipeline doctor        gpu + ffmpeg + upscaler + fonts + llm all green
spec generation        219 models reachable through OmniRoute over the bridge
image generation       a real 768x432 frame drawn on the passed-through GPU
```

What made it work, in order:

1. **GPU passthrough.** `nvidia-container-toolkit` on the host, then
   `--gpus=all` in the hermes `terminal.docker_extra_args`. Without the toolkit
   the flag fails every `docker run`, so install first, add the flag second.
2. **Memory.** sdxl-turbo offloads the model to system RAM, peaking ~8-9 GB, so
   `terminal.container_memory` is raised to `12288`. The 5 GB default OOMs.
3. **Reaching OmniRoute.** The sandbox has no route to the host and a
   default-deny egress proxy. One `ufw` rule allows the egress subnet to reach
   the API port, and the OmniRoute host is added to the proxy whitelist. The LLM
   base URL inside the sandbox is `http://172.21.0.1:20128/v1` (the bridge
   gateway), set in `terminal.docker_env`.
4. **Assets, not downloads.** The Hugging Face model cache, the Real-ESRGAN
   binary, the fonts and the contentforge source are copied into the sandbox
   home (`~/.hermes/sandboxes/docker/default/home`, which is `/root` in the
   container). torch, diffusers and contentforge are `pip install --user`ed
   there so they persist; ffmpeg is a static binary in `/root/.local/bin`.
5. **No `HF_HUB_OFFLINE`.** It breaks fp16-variant loading under diffusers 0.39
   (see local-image-generation.md). Weights still load from the copied cache;
   only the tiny metadata check goes online, through the proxy.

The Telegram agent makes a video by running `pipeline make` in its own terminal
— there is a `contentforge-video` hermes skill describing exactly that. No host
round-trip and no mailbox: the container is the worker.

Two secrets the agent cannot supply and the user must add to
`terminal.docker_env`: `GEMINI_API_KEY` (narration) and, only if OmniRoute
requires one, `CONTENTFORGE_LLM_KEY`.

---

## 3. Making a video

Write the narration to a file — plain prose, one idea per sentence — then:

```bash
pipeline make ceiling-fans --script-file my-script.txt
```

`ceiling-fans` is the run name. Everything lands in `data/videos/ceiling-fans/`.

Check the beats before spending an hour of GPU time on them:

```bash
pipeline make ceiling-fans --script-file my-script.txt --dry-run
```

That splits the script and prints what each shot will cover, without generating
anything.

### What it does

```
script    the prose you wrote, OR generated from --topic + --source URLs,
  ↓       grounded in the sources and checked for verbatim lifting
spec      one LLM call per 20 beats: what to draw, what to letter
  ↓
audio     one narrated clip per beat, each timed with ffprobe
  ↓
draw      one illustration per beat on your GPU
  ↓
letter    upscale to 1080p, correct the palette, draw the sheet, add the words
  ↓
render    ffmpeg, one shot per beat, timed by the measured audio,
          plus subtitles.srt / subtitles.vtt from the same timing
```

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
  audio/          one wav per beat
  raw/            illustrations at generation size
  frames/         finished 1920x1080 frames
  video.mp4
  subtitles.srt   timed captions, from the same shot timing
  subtitles.vtt
  thumbnail.png   built at publish time, from the first frame
  published.json  written after a successful upload
```

---

## 4. Rerunning

**Stages are skipped if their output is already there.** Rerunning after a crash
picks up where it stopped rather than starting over — which matters, because a
twenty-minute video is roughly that much GPU and TTS work.

To redo one stage deliberately:

```bash
pipeline make ceiling-fans --force draw          # just the illustrations
pipeline make ceiling-fans --force draw --force letter
pipeline make ceiling-fans --force all
```

Stage names: `script`, `spec`, `audio`, `draw`, `letter`, `render`.

**Editing `spec.json` by hand is expected.** It is the cheapest place to fix a
video: change a subject or a heading, then `--force draw --force letter --force
render` and only those stages rerun.

If you edit `script.txt` so it has a different number of sentences, the next run
refuses rather than pairing the wrong picture with the wrong words. Rerun with
`--force spec`.

---

## 5. When something fails

Every failure names the stage and what was missing. The common ones:

**`CUDA out of memory`** — something else is using the GPU. A browser playing
video holds around 2 GB. Close it and rerun; finished stages are kept.

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

## 6. Running it under hermes

**The pipeline runs inside the hermes sandbox** — see the sandbox subsection of
§2 for how it was made to work and what is verified. The Telegram agent makes a
video by running `pipeline make` in its own terminal; the `contentforge-video`
hermes skill spells out the commands.

`pipeline doctor` is the first thing to run inside the container when something
misbehaves. It now probes the LLM endpoint rather than merely checking that a
variable is set, so it distinguishes "the GPU was not passed through" from "the
fonts are not mounted" from "the LLM URL points at the dashboard port" — which
otherwise all present as the same failed render.
