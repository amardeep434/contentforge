"""Local, offline narration in the chosen voice, via OmniVoice voice cloning.

Why this exists: Gemini TTS was the intended voice, but Google restricted the
account to AQ-prefix keys that the Gemini API rejects (a live, unresolved
Google-side regression - every REST call and the official SDK return 401
ACCESS_TOKEN_TYPE_UNSUPPORTED). OmniVoice sidesteps it entirely: it runs on the
local GPU, needs no key, and clones the exact voice we selected from a short
reference clip - so the narrator is the same one we picked, with no dependency
on any external service. That also fits the pipeline's offline-first goal, which
Gemini never did.

The model is loaded once and reused across every beat: loading is a few seconds,
and a 200-beat video would otherwise pay that cost 200 times. The reference clip
and its transcript are held constant so every beat is the same speaker.

Text normalization (numbers, "$150" -> spoken) needs OmniVoice's optional
WeTextProcessing dependency. It is used when installed and skipped otherwise -
a missing normaliser should make numbers sound wrong, never crash a render.
"""

from pathlib import Path

from contentforge.errors import MissingDataError

#: The selected voice, cloned from this reference. Lives beside the fonts and the
#: upscaler in ~/.local/share/contentforge, copied into the sandbox the same way.
REFERENCE_DIR = Path.home() / ".local/share/contentforge/voices"
DEFAULT_REFERENCE = REFERENCE_DIR / "iapetus-reference.wav"

#: Exactly what the reference clip says. Voice cloning needs the reference audio
#: paired with its transcript; a wrong transcript degrades the clone.
DEFAULT_REFERENCE_TEXT = (
    "Your ceiling fan does not cool the room. It never has. It moves air across "
    "your skin, and that is the entire trick. Leave it running in an empty room "
    "and you are paying to make the room very slightly warmer."
)

DEFAULT_MODEL = "k2-fsa/OmniVoice"

#: OmniVoice emits 24 kHz mono, same as Gemini did, so nothing downstream cares
#: which backend produced a clip - `measure_duration` reads it from the file.
SAMPLE_RATE = 24_000

#: The reference channel narrates at 142 words per minute (C-047). Calibrated by
#: measurement against the cloned Iapetus voice, two sentences each:
#:
#:     speed 1.00   ~172 wpm
#:     speed 0.89   ~153 wpm
#:     speed 0.82   ~144 wpm
#:     speed 0.80   ~141 wpm   <- lands on 142
#:
#: It varies a little with the sentence, which is why the pipeline still times
#: every clip from its own audio rather than trusting a target.
DEFAULT_SPEED = 0.80


def _normalisation_available() -> bool:
    try:
        import tn.english.normalizer  # noqa: F401  (WeTextProcessing)

        return True
    except Exception:
        return False


def load_model(model: str = DEFAULT_MODEL, device: str = "cuda"):
    """Load OmniVoice once. Imported lazily so the package works without it."""
    try:
        import torch
        from omnivoice import OmniVoice
    except ImportError:
        raise MissingDataError(
            "omnivoice is not installed. Run: pip install 'contentforge[voice]'"
        ) from None
    if device == "cuda" and not torch.cuda.is_available():
        raise MissingDataError(
            "no CUDA GPU visible for OmniVoice; inside Docker this usually means "
            "the container was started without --gpus all"
        )
    return OmniVoice.from_pretrained(model).to(device).eval()


def synthesise(model, text: str, out_path: Path, reference: Path,
               reference_text: str, normalize: bool | None = None,
               speed: float = DEFAULT_SPEED) -> Path:
    """Narrate one beat in the cloned voice, written to `out_path`."""
    import numpy as np
    import soundfile as sf

    spoken = (text or "").strip()
    if not spoken:
        raise MissingDataError("nothing to narrate for this beat")
    if not reference.exists():
        raise MissingDataError(
            f"no voice reference at {reference}; the cloned voice needs it. See "
            "docs/setup/local-voice.md"
        )
    if normalize is None:
        normalize = _normalisation_available()

    audio = model.generate(
        spoken, language="en",
        ref_audio=str(reference), ref_text=reference_text,
        normalize_text=normalize, speed=speed,
    )
    wave = np.asarray(audio[0] if isinstance(audio, list) else audio,
                      dtype=np.float32).squeeze()
    if wave.size == 0:
        raise MissingDataError(
            "OmniVoice returned no audio; a silent clip renders as a video with "
            "no narration"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), wave, SAMPLE_RATE)
    return out_path
