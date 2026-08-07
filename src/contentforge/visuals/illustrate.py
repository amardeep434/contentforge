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

`sdxl-turbo` is the default. It composes better when a beat needs several
elements arranged deliberately, which every lettered frame does, and matching the
reference turned out to be a composition problem rather than a fidelity one
(C-060). `sd-turbo` is three times faster and worth a draft pass.

**Generation size is 768x432; output size is 1920x1080.** These are different
numbers and the environment variable names refer to the first. 1024x576 reliably
OOMs on a 6 GB card once a desktop is running, so frames are drawn small and then
upscaled 4x with Real-ESRGAN's anime model and fitted to exactly 1080p - line art
survives that with no visible loss, unlike photography.

**Text is not generated into the image.** Diffusion models garble lettering, and
the reference channel's captions are clean. Words are composited afterwards with
PIL, where they are exact and legible - see `caption.py`.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

#: Better composition, which is what matching the reference turned out to need.
#: Needs sequential offload on a 6 GB card, and takes ~6.5 s/image against
#: sd-turbo's ~1.3 s - about 23 minutes for a 200-shot video rather than four.
#: That trade was made deliberately: the frames carry a diagram with several
#: arranged elements, and sd-turbo reliably delivers two of any three things
#: asked for in one prompt.
DEFAULT_MODEL = "stabilityai/sdxl-turbo"

#: Three times faster, worse at arranging several elements. Worth passing
#: --model for a draft pass over a script before committing to a full render.
FAST_MODEL = "stabilityai/sd-turbo"

#: Kept as the name the offload branch tests against.
LARGE_MODEL = DEFAULT_MODEL

#: Turbo models expect no guidance, but 4 steps is too few for a coherent scene:
#: a first end-to-end render produced a garbled kitchen scale for "a ceiling fan
#: above a thermometer". 8 steps holds the subject together at ~10s/image; the
#: bigger lever was simplifying the subjects (see spec.py) and a harder negative.
TURBO_STEPS = 8
TURBO_GUIDANCE = 0.0

#: Real-ESRGAN's anime model, which is trained on line art and reconstructs
#: clean edges rather than smoothing them. Generating at 768x432 and upscaling
#: 4x beats generating large: the card cannot do 1080p directly, and a lanczos
#: stretch leaves soft lines that read as low quality beside the reference.
UPSCALER = Path.home() / ".local/share/realesrgan/realesrgan-ncnn-vulkan"
UPSCALE_MODEL = "realesr-animevideov3"
FINAL_WIDTH, FINAL_HEIGHT = 1920, 1080

#: Held constant across every image so the video looks like one hand drew it.
#: The reference channel's consistency across 22 minutes is the effect being
#: reproduced here.
#: Matched against a native-resolution frame from the reference channel: cream
#: background, not blue; muted browns and greys; confident bold ink.
HOUSE_STYLE = (
    "simple hand drawn line-art illustration, one single object centered, bold "
    "black ink outlines, flat plain cream off-white background, minimal, lots of "
    "empty space, muted colours, clean confident linework, no shading, no "
    "gradient, no texture, no text, not 3d, not a photograph"
)

#: Empty by default now. Headings are lettered top-centre on the background (not
#: on a half-frame sheet), so the drawing no longer has to vacate one side, and a
#: centred single object reads best. The old "subject on the right, empty left"
#: also overran CLIP's 77-token limit and was silently truncated. Kept as a hook
#: a caller can still set.
COMPOSITION = ""

#: Pushed away from the failure modes seen in testing.
#: "text" and "letters" are pushed away deliberately: diffusion garbles
#: lettering, and the reference channel's captions are clean. Words are
#: composited afterwards instead.
NEGATIVE = (
    "photo, photorealistic, 3d render, gradient, blurry, watermark, signature, "
    "label, text, letters, words, numbers, digits, dial, gauge, clock, "
    "cluttered, busy, multiple objects, frame border, grain, noise, "
    "realistic hand, hands, fingers, extra fingers, deformed hands, mutated "
    "hands, realistic face, detailed anatomy, person"
)


@dataclass(frozen=True)
class Illustration:
    path: Path
    prompt: str
    seed: int


def build_prompt(subject: str, style: str = HOUSE_STYLE,
                 composition: str = COMPOSITION) -> str:
    """House style first, subject second, composition last.

    Order matters for short prompts: tokens early carry more weight, and the
    style is what must never drift between shots.
    """
    subject = (subject or "").strip()
    if not subject:
        raise MissingDataError("an illustration needs a subject to draw")
    parts = [style, subject]
    if composition:
        parts.append(composition)
    return ", ".join(parts)


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
    house_style: str = HOUSE_STYLE,
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

    from contentforge import interrupt

    made: list[Illustration] = []
    for index, subject in enumerate(subjects, start=1):
        interrupt.check()  # stop between images, never mid-generation
        prompt = build_prompt(subject, style=house_style)
        image_seed = seed + index
        path = out_dir / f"shot_{index:03d}.png"
        # An image already drawn (from an earlier, interrupted run) is kept, so a
        # stop part way through the draw stage does not redo hours of finished
        # work - each image is ~4 min on a 6 GB card.
        if not (path.exists() and path.stat().st_size > 0):
            generate(prompt, path, image_seed)
        if not path.exists() or path.stat().st_size == 0:
            raise MissingDataError(
                f"illustration {index} was not written; a missing image would "
                "leave a beat with nothing on screen"
            )
        made.append(Illustration(path=path, prompt=prompt, seed=image_seed))
    return made


def upscale(source: Path, destination: Path, runner: Callable | None = None) -> Path:
    """4x with the anime model, then fit exactly to 1080p.

    Two steps rather than one because the upscaler only does integer factors;
    4x overshoots 1080p and the downscale lands it precisely while keeping the
    reconstructed edges sharp.
    """
    import subprocess

    from PIL import Image

    if not UPSCALER.exists():
        raise MissingDataError(
            f"upscaler not found at {UPSCALER}. See "
            "docs/setup/local-image-generation.md"
        )
    enlarged = destination.with_suffix(".4x.png")
    finished = (runner or subprocess.run)(
        [str(UPSCALER), "-i", str(source), "-o", str(enlarged),
         "-n", UPSCALE_MODEL, "-s", "4", "-f", "png"],
        capture_output=True, text=True, timeout=600,
    )
    if getattr(finished, "returncode", 1) != 0 or not enlarged.exists():
        raise MissingDataError(
            f"upscaling failed: {(getattr(finished, 'stderr', '') or '')[-200:]}"
        )
    Image.open(enlarged).resize(
        (FINAL_WIDTH, FINAL_HEIGHT), Image.LANCZOS
    ).save(destination)
    enlarged.unlink()
    return destination


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
