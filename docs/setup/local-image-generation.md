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

| Your VRAM | What to use |
|---|---|
| 4 GB or less | Too tight. Use the cloud options instead. |
| **6 GB** | `sd-turbo` — what this project defaults to |
| 8–12 GB | `sd-turbo`, or `sdxl-turbo` without offloading |
| 12 GB+ | Anything, including Flux |

If `nvidia-smi` says *command not found*, you have no NVIDIA driver. On Ubuntu:
`sudo ubuntu-drivers autoinstall` then reboot.

---

## 2. Install the software

Two pieces: **PyTorch** (runs maths on the GPU) and **diffusers** (the
image-generation library).

```bash
cd ~/Projects/contentforge
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu124
.venv/bin/pip install diffusers transformers accelerate safetensors pillow
```

The first line downloads about 3 GB. The `cu124` part means "the CUDA 12.4
build" — using the plain `pip install torch` gives you a **CPU-only** version
that silently runs 50x slower, which is the single most common way this goes
wrong.

Check it worked:

```bash
.venv/bin/python -c "import torch; print(torch.cuda.is_available())"
```

**It must print `True`.** If it prints `False`, torch cannot see your card —
usually the CPU-only build got installed. Uninstall and redo the `cu124` line.

---

## 3. First run

```bash
pipeline illustrate --check
```

This downloads the model (~2.5 GB, once) and generates one test picture. Expect
a minute or two the first time and a second or two after that.

Model files land in `~/.cache/huggingface/`. Do not delete that folder unless you
want to download it all again.

---

## 4. When it runs out of memory

You will see:

```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 224.00 MiB.
GPU 0 has a total capacity of 5.66 GiB of which 375.00 MiB is free.
```

**This is normal on a 6 GB card and it is almost always something else using the
GPU.** During this project's setup, a YouTube video playing in a browser was
holding roughly 2 GB — closing the tab fixed it immediately.

Check what is holding memory:

```bash
nvidia-smi
```

Look at the process list at the bottom. Browsers, games and video calls are the
usual culprits. A desktop environment legitimately uses 300–600 MB; that is fine.

If it still will not fit:

```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True   # reduces fragmentation
```

and generate at a smaller size. **768x432 is already the default** for exactly
this reason: 1024x576 OOMs on a 6 GB card once a desktop environment is running.
ffmpeg upscales to 1920x1080 at render time and line art survives that with no
visible loss, unlike photography.

---

## 5. Choosing a model

```bash
pipeline illustrate --model sd-turbo     # default
pipeline illustrate --model sdxl-turbo   # better composition, ~3x slower
```

Measured on an RTX 3060 Laptop, 6 GB:

| | size | peak VRAM | per image | 200 images |
|---|---|---|---|---|
| `sd-turbo` | 2.5 GB | 3.1 GB | 0.6–2.1 s | ~4 min |
| `sdxl-turbo` | 6.9 GB | 2.4 GB* | 6.4–7.3 s | ~23 min |

\* lower peak because it offloads layer by layer to system RAM — that is also
why it is slower.

`sd-turbo` is the default because its output is closer to the stark, minimal
look we want, and because three minutes beats twenty-three.

---

## 6. Running it inside hermes / Docker

Three things a container needs that a normal program does not.

**The GPU must be passed in.** A container cannot see your card by default:

```bash
docker run --gpus all ...
```

If that errors, install the NVIDIA Container Toolkit:

```bash
sudo apt install nvidia-container-toolkit
sudo systemctl restart docker
```

**The model cache must be a volume**, or every container start re-downloads
2.5 GB:

```bash
-v ~/.cache/huggingface:/root/.cache/huggingface
```

**Nothing may prompt for input.** Every setting comes from the environment:

```bash
CONTENTFORGE_IMAGE_MODEL=stabilityai/sdxl-turbo
CONTENTFORGE_IMAGE_WIDTH=768
CONTENTFORGE_IMAGE_HEIGHT=432
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
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
GPU is not passed through" from "the model is missing" from "the code is wrong".

---

## 7. Matching the reference quality

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
blurring them), and fits that to exactly 1920x1080.

Measured end to end, per image:

```
sdxl-turbo generate   6.2 s     better composition
upscale 4x            ~1 s
fit to 1080p          instant
                      ~7 s  →  200 images in about 23 minutes
```

`sd-turbo` is ~1.3s instead of 6.2s if you want speed over composition.

---

## 8. Fonts for the lettering

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

## 9. What this does not solve

**Text inside pictures.** Diffusion models garble lettering — a request for
"DREAM" produces something that looks like writing and is not. Captions are
drawn on afterwards with PIL, where they are exact.

**Prompt obedience.** `sd-turbo` is a small model. Ask for three specific things
in one picture and it will usually give you two. `sdxl-turbo` is better at this
and takes three times as long; that is the trade.

**Style drift.** Every image gets the same house-style prefix and a derived seed
so a rerun reproduces the same pictures. Without that a video looks like several
different people drew it.
