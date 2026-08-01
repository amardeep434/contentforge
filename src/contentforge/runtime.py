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

#: Free, offline, and the closest match to the reference channel's pacing.
DEFAULT_VOICE_BACKEND = "edge"

ENV_LLM_BASE_URL = "CONTENTFORGE_LLM_BASE_URL"
ENV_LLM_KEY = "CONTENTFORGE_LLM_KEY"
ENV_LLM_MODEL = "CONTENTFORGE_LLM_MODEL"
ENV_VOICE_BACKEND = "CONTENTFORGE_VOICE_BACKEND"
ENV_VOICE = "CONTENTFORGE_VOICE"
ENV_IMAGE_MODEL = "CONTENTFORGE_IMAGE_MODEL"
ENV_IMAGE_WIDTH = "CONTENTFORGE_IMAGE_WIDTH"
ENV_IMAGE_HEIGHT = "CONTENTFORGE_IMAGE_HEIGHT"


def llm_client():
    """The chat client, from environment configuration."""
    from contentforge.providers.llm import LLMClient

    base_url = os.environ.get(ENV_LLM_BASE_URL, "")
    model = os.environ.get(ENV_LLM_MODEL, "")
    if not base_url or not model:
        raise MissingDataError(
            f"{ENV_LLM_BASE_URL} and {ENV_LLM_MODEL} must be set to plan visuals. "
            "See docs/setup/running-the-pipeline.md"
        )
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


def speaker(backend: str | None = None, voice: str | None = None
            ) -> Callable[[str, Path], Path]:
    """Narrate one beat to one file.

    edge is the default: free, offline-capable, and measured at the reference
    channel's 142 wpm. Gemini is available for a different timbre and costs a
    free-tier key.
    """
    chosen = (backend or os.environ.get(ENV_VOICE_BACKEND, DEFAULT_VOICE_BACKEND)).lower()

    if chosen == "edge":
        from contentforge.voice.speak import DEFAULT_VOICE, synthesise

        name = voice or os.environ.get(ENV_VOICE, DEFAULT_VOICE)

        def speak(text: str, path: Path) -> Path:
            synthesise(text, path, voice=name)
            return path

        return speak

    if chosen == "gemini":
        from contentforge.voice.backends import DEFAULT_GEMINI_VOICE, gemini_runner

        name = voice or os.environ.get(ENV_VOICE, DEFAULT_GEMINI_VOICE)

        def speak(text: str, path: Path) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gemini_runner(text, voice=name))
            return path

        return speak

    raise MissingDataError(
        f"unknown voice backend {chosen!r}; use 'edge' or 'gemini'"
    )


def illustrator(model: str | None = None, width: int | None = None,
                height: int | None = None) -> Callable[[list[str], Path], list]:
    """Subjects in, one image file per subject out.

    The diffusion pipeline is loaded once and reused across every beat. Loading
    it per image would add roughly ten seconds each, which over 200 beats is
    half an hour of doing nothing.
    """
    from contentforge.visuals.illustrate import DEFAULT_MODEL, illustrate, load_pipeline

    name = model or os.environ.get(ENV_IMAGE_MODEL, DEFAULT_MODEL)
    size = (
        width or int(os.environ.get(ENV_IMAGE_WIDTH, 768)),
        height or int(os.environ.get(ENV_IMAGE_HEIGHT, 432)),
    )
    loaded = None

    def draw(subjects: list[str], out_dir: Path) -> list:
        nonlocal loaded
        if loaded is None:
            loaded = load_pipeline(name)
        return illustrate(
            subjects, out_dir, pipeline=loaded, model=name,
            width=size[0], height=size[1],
        )

    return draw


def upscaler() -> Callable[[Path, Path], Path]:
    """768x432 line art to exactly 1920x1080, with the edges rebuilt."""
    from contentforge.visuals.illustrate import upscale

    return upscale


def renderer() -> Callable:
    from contentforge.render.video import render

    return render


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
    configured = all(os.environ.get(name) for name in (ENV_LLM_BASE_URL, ENV_LLM_MODEL))
    lines.append(f"llm       {'configured' if configured else 'NOT configured'}")
    return "\n".join(lines)
