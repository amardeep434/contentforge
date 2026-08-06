# Generating pictures on your own machine, for free

This guide sets up image generation that runs on your computer instead of paying
an API per picture. Written for someone who has never used a GPU for anything.

**Why bother.** One video needs 150–250 illustrations. Google charges about
4 cents each, so three test videos cost roughly $25. Your graphics card does the
same job for nothing, forever, and works offline — which matters because this
pipeline is meant to run unattended.

---

## 1. Do you have the right hardware?

You need an **NVIDIA** graphics card. AMD and Intel cards technically work but
the setup is far more painful; this guide assumes NVIDIA.

```bash
nvidia-smi
```

If that prints a table, you have a working NVIDIA driver. Look at the number
under **Memory-Usage** on the right — that is your VRAM.

```
| NVIDIA GeForce RTX 3060 Laptop GPU    ...    6144MiB |
                                                ^^^^^^ this
```

Here is the surprising part: **VRAM is no longer the wall.** The good models
below are 12–20 billion parameters and do not fit a 6 GB card at all — yet they
run on one, because a library called **mmgp** keeps the whole model in ordinary
system RAM and feeds it to the GPU one layer at a time. So the thing that
actually limits you is **how much system RAM** you have, not how much VRAM.

| Your VRAM | What to use |
|---|---|
| 4 GB or less | Too tight for the streamed models. Use a draft model or the cloud. |
| **6 GB** | Everything here runs — Qwen-Image and FLUX are streamed from RAM |
| 8–12 GB | Same, with a bit more headroom |
| 12 GB+ | Same again; nothing here needs it, VRAM stays ~2–3 GB regardless |

If `nvidia-smi` says *command not found*, you have no NVIDIA driver. On Ubuntu:
`sudo ubuntu-drivers autoinstall` then reboot.

---

## 2. The models, and why these ones

There are two good models and two draft models. The good ones draw the stark,
minimal line art this project wants; the draft ones are only for checking pacing.

**Qwen-Image** — `--model qwen` — **the default.** Best line-art quality, and the
only model that reliably draws a simple **stick figure** instead of an
over-detailed, over-rendered person. The catch is speed: about **4 minutes per
image** on a 6 GB card.

**FLUX.1-schnell** — `--model flux` — about **19 seconds per image**. Good on
objects and scenes, but it draws detailed, realistic people rather than stick
figures. Use it as the fast alternative, or as a draft.

**sdxl-turbo / sd-turbo** — `--model stabilityai/sdxl-turbo` — about **10 s** and
**1.3 s** per image respectively, but low quality. These are **draft only**: run
one to check that the script and pacing work, never for a final video. A finished
video must have one consistent look, and the draft models cannot hold it.

### How a 20-billion-parameter model fits a 6 GB card

It doesn't — not the normal way. A 20 B model needs far more memory than a 6 GB
card has. **mmgp** ("Memory Management for the GPU Poor") keeps the entire model
sitting in ordinary system RAM and streams it to the GPU **a layer at a time**,
so at any instant only a small slice is on the card. VRAM stays around 2–3 GB no
matter how big the model is. The price you pay is system RAM (lots of it) and
time (the streaming is slower than having the whole model resident).

---

## 3. Install the software

Two base pieces — **PyTorch** (runs maths on the GPU) and **diffusers** (the
image library) — plus the low-VRAM streaming stack, **mmgp** and
**optimum-quanto**.

```bash
cd ~/Projects/contentforge
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu124   # cu124, NOT CPU-only
.venv/bin/pip install diffusers transformers accelerate safetensors pillow
.venv/bin/pip install mmgp optimum-quanto            # the low-VRAM streaming stack
```

The torch line downloads about 3 GB. The `cu124` part means "the CUDA 12.4
build" — using the plain `pip install torch` gives you a **CPU-only** version
that silently runs 50x slower, which is the single most common way this goes
wrong.

Check it worked:

```bash
.venv/bin/python -c "import torch; print(torch.cuda.is_available())"
```

**It must print `True`.** If it prints `False`, torch cannot see your card —
usually the CPU-only build got installed. Uninstall and redo the `cu124` line.

**One pin to be aware of.** The local voice model pulls in `torchaudio`, which
must stay pinned to **2.6.0** to match torch 2.6+cu124. If you upgrade torch,
upgrade torchaudio in step. See `local-voice.md`.

---

## 4. Build the pre-quantised weights (one-time, REQUIRED)

Before the first real render you must build the model weights once. The models
ship as large GGUF files; the pipeline actually loads a **qint8** ("quantised to
8-bit integers") version of them. This build step produces those qint8 files.

```bash
python scripts/build_prequant.py          # builds both Qwen + FLUX
python scripts/build_prequant.py qwen     # or just one
```

Before it can run, the GGUF source files must already be in the Hugging Face
cache — the build script **errors if they are missing, it does not download
them**. Fetch them once (each is large: Qwen ~20 GB, FLUX ~12 GB):

```bash
huggingface-cli download city96/Qwen-Image-gguf    qwen-image-Q8_0.gguf
huggingface-cli download city96/FLUX.1-schnell-gguf flux1-schnell-Q8_0.gguf
huggingface-cli download Qwen/Qwen-Image            # component configs (T5/VAE/tokenizer)
huggingface-cli download Freepik/flux.1-lite-8B     # FLUX components (only its transformer is replaced)
```

The `Qwen/Qwen-Image` and `Freepik/flux.1-lite-8B` component repos also resolve
automatically the first time the pipeline runs, but the two `.gguf` files above
must be present before `build_prequant.py`.

The build needs about **42 GB of system RAM** transiently — this is a job for a
real host machine, not a small container — and writes to
`~/.local/share/contentforge/models/`:

- `qwen-image-qint8.safetensors` (~20 GB)
- `flux-schnell-qint8.safetensors` (~12 GB)
- `flux-schnell-cfg/config.json`

Pre-quantising this way is **loss-free** relative to running the GGUF directly:
the pipeline would quantise to the same qint8 at load time anyway. Building it
up front just moves that cost to build time and roughly **halves** the RAM each
render needs. If a qint8 file is missing at render time, the render fails loudly
and tells you to run this script.

---

## 5. First run and the `--check` flag

```bash
pipeline illustrate --check
```

or `pipeline illustrate --check --model qwen`. This reports the card, the VRAM,
the torch version — or an explicit reason it cannot run (GPU not visible, weights
missing, code problem). **It is the first thing to run whenever image generation
misbehaves.**

Model files live in `~/.cache/huggingface/` (the GGUF sources) and
`~/.local/share/contentforge/models/` (the qint8 weights you built in step 4). Do
not delete those unless you want to download and rebuild everything.

---

## 6. When it runs out of memory

First, the good news: the pipeline sets
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` **automatically in code** (you
do not need to export it), and it frees each model between stages. So a normal
render on a dedicated 6 GB card fits without OOM.

If you still hit an out-of-memory error, work out **which** memory ran out.

**VRAM out of memory** looks like:

```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 224.00 MiB.
GPU 0 has a total capacity of 5.66 GiB of which 375.00 MiB is free.
```

Since the model lives in system RAM and only streams a slice onto the card, this
almost always means **something else is using the GPU**. A YouTube video playing
in a browser holds roughly 2 GB — close the tab. Check with `nvidia-smi` and look
at the process list at the bottom; a desktop environment legitimately uses
300–600 MB, which is fine. Finished images are kept when you rerun, so you lose no
progress.

**System RAM out of memory** means the real wall: you do not have enough RAM for
the model you asked for. Qwen needs about **36 GB**. Either switch to
`--model flux` (about 18 GB) or add RAM.

The render also defaults to **768x432** on purpose — ffmpeg upscales to 1080p at
render time and line art survives that with no visible loss, unlike photography.

---

## 7. What it costs, measured

Measured on an RTX 3060 Laptop, 6 GB:

| model | qint8 file | peak system RAM | VRAM | per image | ~150-image video |
|---|---|---|---|---|---|
| Qwen-Image (default) | 20 GB | ~36 GB | ~2–3 GB | ~4 min (20 steps) | ~10 hours |
| FLUX.1-schnell | 12 GB | ~18 GB | ~2 GB | ~19 s (4 steps) | ~48 min |
| sdxl-turbo (draft) | — | fits card | ~5 GB | ~10 s | ~25 min |

Read the columns carefully: the thing that OOMs is **system RAM**, not VRAM,
because the model lives in RAM. A dedicated machine with **≥40 GB of RAM** runs
Qwen comfortably; on a 6 GB card the VRAM is never the bottleneck.

Qwen is the default because it is the only model that draws the stark stick-figure
look this project wants. When you just need to check that a script and its pacing
work, run a draft model first, then commit to Qwen for the final.

---

## 8. Matching the reference quality

Generating at 768x432 and stretching to 1080p leaves soft lines that look cheap
next to the channel we are copying. The fix is an upscaler built for line art.

```bash
mkdir -p ~/.local/share/realesrgan && cd ~/.local/share/realesrgan
curl -sLO https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip
unzip -o realesrgan-ncnn-vulkan-20220424-ubuntu.zip
chmod +x realesrgan-ncnn-vulkan
```

This is a self-contained binary — no Python packages, no CUDA, it talks to the
GPU through Vulkan. About 47 MB including the models.

The pipeline then generates at 768x432, upscales 4x to 3072x1728 with the
**anime** model (trained on line art, so it rebuilds clean edges instead of
blurring them), and fits that to exactly 1920x1080. The upscale adds about a
second per image and fitting to 1080p is instant — negligible next to the
generation time.

---

## 9. Fonts for the lettering

The captions are not decoration. Put a reference frame beside a generated one and
the difference is that theirs carries a heading, a checklist, a stamp and a
signature, all legible — and the drawing exists to serve them.

```bash
mkdir -p ~/.local/share/fonts/contentforge && cd ~/.local/share/fonts/contentforge
B=https://github.com/google/fonts/raw/main
curl -sLO $B/apache/permanentmarker/PermanentMarker-Regular.ttf
curl -sLO $B/ofl/patrickhand/PatrickHand-Regular.ttf
curl -sLO $B/ofl/bangers/Bangers-Regular.ttf
```

Rename them lowercase (`permanentmarker.ttf`, `patrickhand.ttf`, `bangers.ttf`).
Permanent Marker is the bold caps heading face; Patrick Hand does list items.

Note the Google Fonts *API* serves woff2, which PIL cannot read. Pull the `.ttf`
straight from the GitHub repo as above.

---

## 10. Running it inside hermes / Docker

Four things a container needs that a normal program does not.

**The GPU must be passed in.** A container cannot see your card by default:

```bash
docker run --gpus all ...
```

If that errors, install the NVIDIA Container Toolkit:

```bash
sudo apt install nvidia-container-toolkit
sudo systemctl restart docker
```

**The weights must be volumes.** The container has no weights unless you mount
both the Hugging Face cache **and** the qint8 weights you built in step 4 (or copy
them in):

```bash
-v ~/.cache/huggingface:/root/.cache/huggingface
-v ~/.local/share/contentforge/models:/root/.local/share/contentforge/models
```

**Give it enough RAM.** Because the model is streamed from system RAM, the
container memory limit must be about **40 GB** for Qwen — not the 12 GB that
sufficed for the old small models. Too little RAM shows up as a system-RAM OOM
(see §6), not a VRAM error.

**Nothing may prompt for input.** Every setting comes from the environment:

```bash
CONTENTFORGE_IMAGE_MODEL=qwen
CONTENTFORGE_IMAGE_WIDTH=768
CONTENTFORGE_IMAGE_HEIGHT=432
```

**Do not set `HF_HUB_OFFLINE=1`.** It reads as an obvious optimisation once the
model is cached, but `diffusers` 0.39 resolves the `fp16` variant by calling the
Hub's metadata API even when the weights are already on disk, and with
`HF_HUB_OFFLINE=1` that call hard-fails with `OfflineModeIsEnabled` — the model
"is not cached locally" even though it is. Leave it unset: the metadata request
is tiny, the multi-gigabyte weights still load from cache, and inside a
network-restricted sandbox it goes through the proxy (whitelist `huggingface.co`,
which is usually already allowed). Measured cost of the online metadata check
with warm weights: about two seconds.

### Checking it from inside the container

```bash
pipeline illustrate --check
```

prints the card, the VRAM and the torch version, or an explicit reason it cannot
run. Run this first when something in hermes misbehaves — it distinguishes "the
GPU is not passed through" from "the weights are missing" from "the code is
wrong".

---

## 11. One deliberate quirk in the source

If you read the code you will find a patch that looks like a mistake but is not.
`transformers` 5.14 calls `safetensors.safe_open(..., backend=...)`, but the
installed `safetensors` 0.8.0 does not accept that `backend` keyword and rejects
the call. The code works around it automatically — it drops the unknown keyword —
in `visuals/gguf_backends.py`. It is mentioned here only so that a reader who
trips over it in the source knows it is intentional.

---

## 12. What this does not solve

**Text inside pictures.** Diffusion models garble lettering — a request for
"DREAM" produces something that looks like writing and is not. Captions are
drawn on afterwards with PIL, where they are exact.

**Style drift.** Every image gets the same house-style prefix and a derived seed
so a rerun reproduces the same pictures. Without that a video looks like several
different people drew it — which is also why a final video must stick to one
model rather than mixing draft and final output.
