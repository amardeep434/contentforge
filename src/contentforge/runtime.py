"""Resolve environment configuration into the callables the pipeline needs.

One place where "which TTS voice", "which diffusion model", "which LLM" are
decided, so `pipeline.build_video` never reads the environment and stays
testable, and so running under hermes is a matter of setting variables rather
than editing code.

Every import that needs a GPU, a network or ffmpeg is deferred into the factory
that needs it. Importing this module must stay free, or `pipeline research` on a
machine with no torch stops working.
"""

import os
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

# On a 6 GB card the stages run one model after another (voice, then the image
# model), and PyTorch's default caching allocator fragments across the many
# sequential image generations - a real end-to-end run OOM'd 130 MB short with
# 800 MB "reserved but unallocated". expandable_segments lets that reserved
# memory be reused. Must be set before torch initialises CUDA, so it lives at
# import of this module (imported before any model loads) and only if unset.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

#: How many times the scriptwriter regenerates when the policy gate rejects a
#: draft, feeding the violations back each time. Bounded so a script that is
#: fundamentally a re-read of a source hard-fails to the operator instead of
#: looping until it sneaks past a word-overlap check. Matches spec.py's attempts=2
#: pattern; 3 leaves two feedback-corrected retries after the first draft.
SCRIPT_ATTEMPTS = 3

#: Qwen-Image draws the house line-art style best and is the only model that
#: obeys "stick figure" instead of drawing a detailed person, so it is the model
#: for *every* final render - one video looks like one video. It is a GGUF model
#: streamed by mmgp to fit a 6 GB card (see visuals/gguf_backends.py), at ~4 s...
#: ~4 min/image; a full video is an overnight batch, which the resumable stages
#: are built for. If it cannot load, the render fails loudly rather than shipping
#: a lower-quality video from a different model. FLUX.1-schnell and sdxl-turbo
#: stay selectable via CONTENTFORGE_IMAGE_MODEL, but only as an explicit *draft*
#: pass to check script/pacing before committing to the slow Qwen final.
DEFAULT_IMAGE_MODEL = "qwen"

#: OmniVoice, local and offline. Gemini was the choice until Google restricted
#: the account to AQ-prefix keys its own API rejects (401, unresolved Google-side
#: regression). OmniVoice clones the exact voice we selected (Iapetus) from a
#: reference clip, on the GPU, with no key and no network - which fits the
#: offline-first goal Gemini never did. edge and gemini remain selectable.
DEFAULT_VOICE_BACKEND = "omnivoice"

#: OmniRoute's OpenAI-compatible API. Both the API and the dashboard are on
#: 20128 - the API at /v1, the dashboard at /. (37777 is unrelated; another
#: service squats it.) It binds 0.0.0.0, so the same host works from inside a
#: container via the docker bridge gateway.
DEFAULT_LLM_BASE_URL = "http://127.0.0.1:20128/v1"

#: Free, and measured at 8.6s for three beats against 74s for the best local
#: Ollama model. Routing is OmniRoute's job; the pipeline just names a combo.
DEFAULT_LLM_MODEL = "auto/best-free"

ENV_LLM_BASE_URL = "CONTENTFORGE_LLM_BASE_URL"
ENV_LLM_KEY = "CONTENTFORGE_LLM_KEY"
ENV_LLM_MODEL = "CONTENTFORGE_LLM_MODEL"
ENV_VOICE_BACKEND = "CONTENTFORGE_VOICE_BACKEND"
ENV_VOICE = "CONTENTFORGE_VOICE"
ENV_VOICE_REFERENCE = "CONTENTFORGE_VOICE_REFERENCE"
ENV_IMAGE_MODEL = "CONTENTFORGE_IMAGE_MODEL"
ENV_IMAGE_WIDTH = "CONTENTFORGE_IMAGE_WIDTH"
ENV_IMAGE_HEIGHT = "CONTENTFORGE_IMAGE_HEIGHT"


def llm_client():
    """The chat client, from environment configuration."""
    from contentforge.providers.llm import LLMClient

    base_url = os.environ.get(ENV_LLM_BASE_URL) or DEFAULT_LLM_BASE_URL
    model = os.environ.get(ENV_LLM_MODEL) or DEFAULT_LLM_MODEL
    return LLMClient(
        base_url=base_url,
        api_key=os.environ.get(ENV_LLM_KEY, ""),
        model=model,
    )


def spec_planner(client=None) -> Callable[[list[str]], list]:
    """Beats in, per-beat visual specification out."""
    from contentforge.script.spec import generate_spec

    resolved = client or llm_client()
    return lambda beats: generate_spec(resolved, beats)


def scriptwriter(topic: str, source_urls: list[str], niche=None, client=None, sources=None):
    """A callable that writes one grounded, validated narration into a run.

    Returns None when no topic is given, so `make` falls back to a hand-written
    or cached script. When a topic IS given it refuses to proceed without
    sources - an ungrounded script is the exact failure this project exists to
    prevent, so the guard is here, not a warning.
    """
    if not topic:
        return None
    from contentforge.script import generate
    from contentforge.script.generate import choose_shape, generate_script
    from contentforge.script.validate import ValidationError, find_violations
    from contentforge.sourcing.fetch import fetch_source, save_sources

    if not source_urls and not sources:
        raise MissingDataError(
            f"--topic {topic!r} needs at least one --source URL (or a transcript); "
            "a script grounded in nothing is what this pipeline refuses to make"
        )
    resolved = client or llm_client()

    def write(run_dir: Path) -> str:
        srcs = sources if sources is not None else [fetch_source(url) for url in source_urls]
        save_sources(srcs, run_dir)
        system = niche.script_system if niche else generate.SYSTEM
        target_words = niche.target_words if niche else (
            generate.TARGET_WORDS_LOW, generate.TARGET_WORDS_HIGH
        )
        # The policy gate (verbatim/citation/credential) is hard. Rather than fail
        # the whole render on the first lifted phrase, feed every violation back to
        # the model and let it self-correct - bounded, then hard-fail so a script
        # that is fundamentally a re-read of a source still reaches the operator.
        violations: list[str] = []
        for _ in range(SCRIPT_ATTEMPTS):
            script = generate_script(
                resolved, topic, srcs, choose_shape(topic),
                system=system, target_words=target_words,
                feedback=violations or None,
            )
            violations = find_violations(script, srcs)
            if not violations:
                return script
        raise ValidationError(
            f"script still violates policy after {SCRIPT_ATTEMPTS} attempts: "
            + "; ".join(violations)
        )

    return write


def source_from_transcript(topic: str, text: str):
    """Wrap a competitor video's transcript as a Source the script rewrites.
    The video's topic is borrowed; check_verbatim (run in scriptwriter) enforces
    the script is not a copy of this text."""
    from datetime import datetime, timezone
    from contentforge.sourcing.fetch import Source
    return Source(url=f"transcript:{topic}", title=topic, text=text,
                  retrieved_at=datetime.now(timezone.utc))


def metadata_writer(niche=None, client=None):
    """A callable that derives YouTube metadata from a script and its sources."""
    from contentforge.publish.metadata import generate_metadata

    resolved = client or llm_client()
    system = niche.metadata_system.replace("{title_format}", niche.title_format) if niche else None
    return lambda script, sources=None: generate_metadata(
        resolved, script, sources, system=system
    )


class _GpuSpeaker:
    """A voice backend that holds a GPU model and can free it between stages.

    On a 6 GB card the voice model and the diffusion model cannot both be
    resident - loading sdxl-turbo for the draw stage while OmniVoice is still in
    VRAM is an out-of-memory crash. The pipeline calls `close()` after the audio
    stage, which drops the model and empties the CUDA cache so the GPU is free
    for image generation.
    """

    def __init__(self, backend, reference: Path, speed: float | None = None):
        self._backend = backend
        self._reference = reference
        self._speed = speed
        self._model = None

    def __call__(self, text: str, path: Path) -> Path:
        if self._model is None:
            self._model = self._backend.load_model()
        return self._backend.synthesise(
            self._model, text, path, self._reference,
            self._backend.DEFAULT_REFERENCE_TEXT,
            speed=self._speed if self._speed is not None else self._backend.DEFAULT_SPEED,
        )

    def close(self) -> None:
        if self._model is None:
            return
        self._model = None
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                # empty_cache alone left ~1.6 GB of the voice model resident in a
                # real run; synchronize + ipc_collect return it so the image
                # model has the whole card.
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass


def speaker(niche=None, backend: str | None = None, voice: str | None = None
            ) -> Callable[[str, Path], Path]:
    """Narrate one beat to one file.

    OmniVoice is the default: local, no key, cloning the selected voice. edge
    (free, no key, more synthetic) and gemini (blocked by Google's AQ-key
    regression) remain selectable.
    """
    chosen = (backend or os.environ.get(ENV_VOICE_BACKEND, DEFAULT_VOICE_BACKEND)).lower()

    if chosen == "omnivoice":
        from contentforge.voice import omnivoice_backend as ov

        reference = (
            niche.voice_reference if niche else
            Path(os.environ.get(ENV_VOICE_REFERENCE, str(ov.DEFAULT_REFERENCE)))
        )
        return _GpuSpeaker(ov, reference, speed=niche.pace if niche else None)

    if chosen == "edge":
        from contentforge.voice.speak import DEFAULT_VOICE, synthesise

        name = voice or os.environ.get(ENV_VOICE, DEFAULT_VOICE)

        def speak(text: str, path: Path) -> Path:
            synthesise(text, path, voice=name)
            return path

        return speak

    if chosen == "gemini":
        from contentforge.voice.backends import DEFAULT_GEMINI_VOICE, gemini_runner
        from contentforge.voice.speak import strip_citations

        name = voice or os.environ.get(ENV_VOICE, DEFAULT_GEMINI_VOICE)

        def speak(text: str, path: Path) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Strip [1] markers so the narrator never says "bracket one"; edge
            # does this inside synthesise, Gemini needs it done here.
            path.write_bytes(gemini_runner(strip_citations(text), voice=name))
            return path

        return speak

    raise MissingDataError(
        f"unknown voice backend {chosen!r}; use 'edge' or 'gemini'"
    )


def illustrator(niche=None, model: str | None = None, width: int | None = None,
                height: int | None = None) -> Callable[[list[str], Path], list]:
    """Subjects in, one image file per subject out.

    The diffusion pipeline is loaded once and reused across every beat. Loading
    it per image would add roughly ten seconds each, which over 200 beats is
    half an hour of doing nothing.
    """
    from contentforge.visuals import gguf_backends
    from contentforge.visuals.illustrate import HOUSE_STYLE, NEGATIVE, illustrate, load_pipeline

    name = (
        model or (niche.image_model if niche else None)
        or os.environ.get(ENV_IMAGE_MODEL, DEFAULT_IMAGE_MODEL)
    )
    w = width or int(os.environ.get(ENV_IMAGE_WIDTH, 768))
    h = height or int(os.environ.get(ENV_IMAGE_HEIGHT, 432))
    # loaded once on first draw and reused: reloading per beat would add the full
    # model-load cost (tens of seconds) to every one of ~200 beats.
    state: dict = {"pipeline": None, "generate": None, "release": None, "ready": False}

    def _prepare() -> None:
        # A GGUF model (Qwen, or FLUX/sdxl chosen for a draft) is streamed by
        # mmgp; anything else goes through the plain diffusers path. Loading
        # failures propagate: a final render must not silently swap models.
        if gguf_backends.is_gguf_model(name):
            _, state["generate"], state["release"] = (
                gguf_backends.load_pipeline_and_generate(
                    name, w, h, negative=niche.negative if niche else NEGATIVE
                )
            )
        else:
            state["pipeline"] = load_pipeline(name)
        state["ready"] = True

    def draw(subjects: list[str], out_dir: Path) -> list:
        if not state["ready"]:
            _prepare()
        return illustrate(
            subjects, out_dir, pipeline=state["pipeline"], model=name,
            width=w, height=h, generate=state["generate"],
            house_style=niche.house_style if niche else HOUSE_STYLE,
        )

    def close() -> None:
        """Free the image model once the draw stage is done, so ~36 GB of RAM and
        its VRAM are not held through lettering, rendering and metadata. Called by
        the pipeline after draw; symmetric with the voice model's close()."""
        if state["release"] is not None:
            state["release"]()
        elif state["pipeline"] is not None:
            try:
                import gc

                import torch

                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        state["pipeline"] = state["generate"] = state["release"] = None
        state["ready"] = False

    draw.close = close
    return draw


def upscaler() -> Callable[[Path, Path], Path]:
    """768x432 line art to exactly 1920x1080, with the edges rebuilt."""
    from contentforge.visuals.illustrate import upscale

    return upscale


def renderer() -> Callable:
    from contentforge.render.video import render

    return render


def _llm_report() -> str:
    """Whether the configured endpoint actually answers, not just whether it is set.

    A base URL in the environment proves nothing - the most common failure is a
    correct-looking URL pointing at OmniRoute's dashboard port instead of its
    API port, which 404s at request time rather than at startup.
    """
    import json
    import urllib.request

    base = os.environ.get(ENV_LLM_BASE_URL) or DEFAULT_LLM_BASE_URL
    model = os.environ.get(ENV_LLM_MODEL) or DEFAULT_LLM_MODEL
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=5) as reply:
            count = len(json.loads(reply.read()).get("data", []))
        return f"{base} reachable, {count} models, using {model}"
    except Exception as error:
        return f"{base} UNREACHABLE ({type(error).__name__}) - see docs/setup/running-the-pipeline.md"


def report() -> str:
    """What this machine can actually run, for a setup check."""
    from contentforge.visuals.illustrate import UPSCALER, gpu_report

    lines = [f"gpu       {gpu_report()}"]
    lines.append(
        f"upscaler  {'found' if UPSCALER.exists() else 'MISSING at ' + str(UPSCALER)}"
    )
    from contentforge.visuals.caption import BODY_FONT, HEADING_FONT

    missing = [p for p in (HEADING_FONT, BODY_FONT) if not p.exists()]
    lines.append("fonts     " + ("found" if not missing else
                                 f"MISSING {', '.join(p.name for p in missing)}"))
    for tool in ("ffmpeg", "ffprobe"):
        from shutil import which

        lines.append(f"{tool:<10}{which(tool) or 'MISSING - apt install ffmpeg'}")
    lines.append(f"llm       {_llm_report()}")
    return "\n".join(lines)
