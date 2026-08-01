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
CONTENTFORGE_LLM_BASE_URL=http://localhost:8080/v1
CONTENTFORGE_LLM_MODEL=your-model-name
CONTENTFORGE_LLM_KEY=                    # blank is fine for a local server

# Optional - these are the defaults.
CONTENTFORGE_VOICE_BACKEND=edge          # or: gemini
CONTENTFORGE_VOICE=en-GB-RyanNeural
CONTENTFORGE_IMAGE_MODEL=stabilityai/sd-turbo
CONTENTFORGE_IMAGE_WIDTH=768
CONTENTFORGE_IMAGE_HEIGHT=432
```

Load them into your shell before running anything:

```bash
set -a && . ./.env && set +a
```

`GEMINI_API_KEY` is only needed if you set the voice backend to `gemini`. The
default, `edge`, is free and needs no key.

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
script    the prose you wrote
  ↓ split into sentences, merging any too short to hold a shot
spec      one LLM call plans every beat: what to draw, what to letter
  ↓
audio     one narrated clip per beat, each timed with ffprobe
  ↓
draw      one illustration per beat on your GPU
  ↓
letter    upscale to 1080p, correct the palette, draw the sheet, add the words
  ↓
render    ffmpeg, one shot per beat, timed by the measured audio
```

### What it leaves behind

```
data/videos/ceiling-fans/
  script.txt      what you wrote
  spec.json       the visual plan - readable, and editable
  manifest.json   every shot with its subject, lettering and duration
  audio/          one wav per beat
  raw/            illustrations at generation size
  frames/         finished 1920x1080 frames
  video.mp4
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

Stage names: `spec`, `audio`, `draw`, `letter`, `render`.

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

Nothing is interactive and nothing prompts, so a container needs only:

- the environment variables from §2
- `--gpus all` and the Hugging Face cache mounted
  ([local-image-generation.md](local-image-generation.md) §6)
- `ffmpeg` in the image
- the fonts and the upscaler on a persistent volume, or baked into the image

`pipeline doctor` is the first thing to run inside the container when something
misbehaves. It distinguishes "the GPU was not passed through" from "the fonts
are not mounted" from "the code is wrong", which otherwise all present as the
same failed render.
