"""Generate line-art illustrations locally, on your own GPU.

Why local rather than an API: the target style needs one custom illustration per
narration beat, and a 22-minute video is 150-250 of them. Gemini image generation
has **no free tier allowance** (verified: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
with no value), which puts a three-video test at roughly $20-30. Pollinations is
free but serves a single model that renders 3D and garbles text. Local diffusion
is free, unlimited, offline, and runs inside a container — which matters because
this pipeline is meant to run unattended.

Measured on an RTX 3060 Laptop (6 GB):

    sd-turbo     2.58 GB model, 3.13 GB peak, 0.6-2.1 s/image
    sdxl-turbo   sequential offload, 2.43 GB peak, 6.4-7.3 s/image

`sd-turbo` is the default: it is three times faster and its output is closer to
the stark, minimal look the reference channel uses. `sdxl-turbo` composes better
when a beat needs several elements arranged deliberately, at 3x the time.

Default size is **768x432**, not 1080p. 1024x576 reliably OOMs on a 6 GB card
once a desktop is running, and ffmpeg upscales to 1920x1080 at render time -
line art survives that with no visible loss, unlike photography.

**Text is not generated into the image.** Diffusion models garble lettering, and
the reference channel's captions are clean. Words are composited afterwards with
PIL, where they are exact and legible - see `caption.py`.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

#: Small, fast, and stylistically closest. Fits a 6 GB card without offloading.
DEFAULT_MODEL = "stabilityai/sd-turbo"

#: Better composition, ~3x slower, needs sequential offload on 6 GB.
LARGE_MODEL = "stabilityai/sdxl-turbo"

#: Turbo models are distilled for 1-4 steps and expect no guidance. Raising
#: either does not improve them; it degrades them.
TURBO_STEPS = 4
TURBO_GUIDANCE = 0.0

#: Held constant across every image so the video looks like one hand drew it.
#: The reference channel's consistency across 22 minutes is the effect being
#: reproduced here.
HOUSE_STYLE = (
    "simple hand drawn line art, thick black ink outline, flat pale blue "
    "background, minimal cartoon doodle, childrens book illustration, "
    "no shading, no gradient, not 3d, not a photo"
)

#: Pushed away from the failure modes seen in testing.
NEGATIVE = "photo, photorealistic, 3d render, shading, gradient, text, watermark, blurry"


@dataclass(frozen=True)
class Illustration:
    path: Path
    prompt: str
    seed: int


def build_prompt(subject: str, style: str = HOUSE_STYLE) -> str:
    """House style first, subject second.

    Order matters for short prompts: tokens early carry more weight, and the
    style is what must never drift between shots.
    """
    subject = (subject or "").strip()
    if not subject:
        raise MissingDataError("an illustration needs a subject to draw")
    return f"{style}, {subject}"


def load_pipeline(model: str = DEFAULT_MODEL, device: str = "cuda"):
    """Load a diffusion pipeline sized to the available card.

    Imported lazily so the rest of the package works without torch installed -
    research and publishing need no GPU.
    """
    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError:
        raise MissingDataError(
            "torch and diffusers are not installed. See "
            "docs/setup/local-image-generation.md"
        ) from None

    if device == "cuda" and not torch.cuda.is_available():
        raise MissingDataError(
            "no CUDA GPU visible. Inside Docker this usually means the container "
            "was started without --gpus all"
        )
    pipeline = AutoPipelineForText2Image.from_pretrained(
        model, torch_dtype=torch.float16, variant="fp16", safety_checker=None
    )
    if model == LARGE_MODEL:
        # Does not fit a 6 GB card resident; offload layer by layer.
        pipeline.enable_sequential_cpu_offload()
    else:
        pipeline = pipeline.to(device)
    pipeline.enable_attention_slicing()
    pipeline.set_progress_bar_config(disable=True)
    return pipeline


def illustrate(
    subjects: list[str],
    out_dir: Path,
    pipeline=None,
    model: str = DEFAULT_MODEL,
    width: int = 768,
    height: int = 432,
    seed: int = 0,
    generate: Callable | None = None,
) -> list[Illustration]:
    """One illustration per subject, in order.

    A seed is derived per image from the run seed and the index, so a rerun
    reproduces the same pictures - a video that changes every time it renders
    cannot be reviewed and re-rendered.
    """
    if not subjects:
        raise MissingDataError("no subjects to illustrate")
    out_dir.mkdir(parents=True, exist_ok=True)

    if generate is None:
        import torch

        pipeline = pipeline or load_pipeline(model)

        def generate(prompt: str, path: Path, image_seed: int) -> Path:
            generator = torch.Generator(device="cpu").manual_seed(image_seed)
            image = pipeline(
                prompt=prompt,
                negative_prompt=NEGATIVE,
                num_inference_steps=TURBO_STEPS,
                guidance_scale=TURBO_GUIDANCE,
                width=width,
                height=height,
                generator=generator,
            ).images[0]
            image.save(path)
            return path

    made: list[Illustration] = []
    for index, subject in enumerate(subjects, start=1):
        prompt = build_prompt(subject)
        image_seed = seed + index
        path = out_dir / f"shot_{index:03d}.png"
        generate(prompt, path, image_seed)
        if not path.exists() or path.stat().st_size == 0:
            raise MissingDataError(
                f"illustration {index} was not written; a missing image would "
                "leave a beat with nothing on screen"
            )
        made.append(Illustration(path=path, prompt=prompt, seed=image_seed))
    return made


def gpu_report() -> str:
    """One line on what the machine can do, for logs and setup checks."""
    try:
        import torch
    except ImportError:
        return "torch not installed - local image generation unavailable"
    if not torch.cuda.is_available():
        return "no CUDA GPU visible - local image generation unavailable"
    properties = torch.cuda.get_device_properties(0)
    return (
        f"{properties.name}, {properties.total_memory / 1e9:.1f} GB VRAM, "
        f"torch {torch.__version__}"
    )
