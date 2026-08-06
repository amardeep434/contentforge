# Narrating on your own machine, for free

This guide sets up the voice that reads each beat aloud. It runs on your
computer instead of calling an API, so there is no key to get, nothing to pay
per line, and it works offline — which matters because this pipeline is meant
to run unattended.

**What does the narrating.** A local model called **OmniVoice**
(`k2-fsa/OmniVoice`, Apache-2.0) runs on your graphics card. It is a
voice-*cloning* model: you give it one short reference clip of a voice, and it
speaks new lines in that same voice. This project clones a voice called
**Iapetus** from a reference clip that has been confirmed to match.

This replaced Gemini TTS, which is dead-ended and no longer works — see the end
of this page if you are wondering where it went.

---

## 1. Prerequisites

You need the same working GPU + CUDA PyTorch that image generation needs. If you
have not set that up yet, do
[local-image-generation.md](./local-image-generation.md) first — step 2 there
installs the `cu124` torch, and the check `torch.cuda.is_available()` must print
`True`.

**Both stages share one card.** On a 6 GB card the voice model and the image
model cannot both sit in VRAM at the same time. You do not have to manage this:
the pipeline loads the voice model for the audio stage and frees it before it
starts drawing. Just know that the two stages take turns on the card.

---

## 2. Install the software

```bash
cd ~/Projects/contentforge
.venv/bin/pip install omnivoice soundfile
.venv/bin/pip install WeTextProcessing        # optional: reads "$150" out loud as words; used if present, skipped if not
```

**One pin you must not skip.** Installing `omnivoice` can drag in a `torchaudio`
built for the wrong CUDA — it tried to pull torchaudio 2.11 (CUDA 13) on top of
our torch 2.6+cu124, which breaks the image stack. Force the matching one:

```bash
.venv/bin/pip install "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cu124
```

Keep `torchaudio` at **2.6.0 (cu124)** — it has to match `torch` 2.6+cu124.

---

## 3. The reference voice clip

OmniVoice clones from a reference `.wav`. Drop the Iapetus clip at the path the
code looks for by default:

```
~/.local/share/contentforge/voices/iapetus-reference.wav
```

If you need it somewhere else, point at it with an environment variable:

```
CONTENTFORGE_VOICE_REFERENCE=/path/to/clip.wav
```

The code also has a default reference *transcript* (the words the clip speaks)
baked in, so you do not have to supply that.

---

## 4. Settings

```
CONTENTFORGE_VOICE_BACKEND=omnivoice     # the default; also: edge (low quality)
CONTENTFORGE_VOICE_REFERENCE=            # optional override for the reference wav
```

`omnivoice` needs no API key. The `edge` backend (edge-tts) needs no key either,
but it is only a fallback — see the note at the bottom.

---

## 5. Speed and pacing

The narration speed is tuned so the delivered words-per-minute matches the
reference channel (~142 wpm). The code uses a default speed of **0.80**:

```
speed 1.0  → ~172 wpm
speed 0.89 → ~153 wpm
speed 0.82 → ~144 wpm
speed 0.80 → ~141 wpm   ← default
```

You normally never touch this.

---

## 6. No background music

The reference channel's audio measures about **-50 dB** in the gaps between
speech — that is real silence, not a quiet music bed. So the pipeline adds no
background music. This is deliberate, not an omission.

---

## 7. Checking it

Run a short render and listen:

```bash
pipeline make test --script-file a-few-sentences.txt
```

The wavs land in `data/videos/test/audio/`. Each beat is one `beat_NNN.wav`,
timed with ffprobe. If a beat comes out with no audio the pipeline fails loudly
rather than shipping a silent gap, so a clean run means every beat actually
spoke.

---

## 8. Running it inside hermes / Docker

The voice model is provisioned just like the image models — the sandbox does not
inherit anything from your machine:

1. Install the packages in the sandbox:
   `pip install omnivoice soundfile WeTextProcessing`
2. Copy the OmniVoice model cache into the sandbox.
3. Copy the Iapetus reference wav in.
4. Set `CONTENTFORGE_VOICE_BACKEND=omnivoice` in `docker_env`.

The old sandbox was set up for Gemini, so it must be redone. This is part of the
hermes deployment checklist — see
[running-the-pipeline.md](./running-the-pipeline.md).

---

## 9. Where Gemini went

Gemini TTS used to do the narration and no longer works. The Google account is
restricted to new `AQ.`-prefix API keys, and the generativelanguage API rejects
those with `401 ACCESS_TOKEN_TYPE_UNSUPPORTED` on every endpoint and through the
official SDK. It is a known Google-side regression with no workaround, so Gemini
is not a usable backend — do not try to wire it back in.

`edge` (edge-tts) is still selectable as a low-quality fallback, but a listener
rejected all six edge voices as obviously synthetic. Use `omnivoice`.
