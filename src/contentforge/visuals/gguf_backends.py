"""GGUF-quantised image backends (Qwen-Image, FLUX.1-schnell) on a 6 GB card.

These two models are far better at the house line-art style than sdxl-turbo -
Qwen in particular is the only model that draws a real stick figure rather than
a detailed person. Neither fits a 6 GB card resident, so mmgp streams them layer
by layer from CPU RAM (VRAM stays ~2 GB).

Weights are shipped **pre-quantised to qint8** (see scripts/build_prequant.py):
loading the raw GGUF and dequantising on the fly costs ~42 GB RAM for Qwen, which
will not fit a memory-limited container. The pre-quantised file reloads with
roughly half that and skips the per-run dequant. The pixels are identical either
way - the runtime path also quantised to quanto qint8; this only moves *when*.

The default is Qwen, with FLUX as the fallback when Qwen cannot be loaded (its
weights are missing, or it runs out of memory): see runtime.illustrator.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError
from contentforge.visuals.illustrate import NEGATIVE, build_prompt

MODELS_DIR = Path.home() / ".local" / "share" / "contentforge" / "models"

#: Where to find the T5/CLIP/VAE/tokenizer components each transformer needs.
#: FLUX borrows the (ungated) Freepik lite components - only its transformer is
#: overridden; the text encoders and VAE are the standard FLUX ones.
_FREEPIK = "~/.cache/huggingface/hub/models--Freepik--flux.1-lite-8B/snapshots/*"

#: name -> how to build and drive that model.
MODELS = {
    "qwen": {
        "qint8": "qwen-image-qint8.safetensors",
        "transformer": ("diffusers", "QwenImageTransformer2DModel"),
        "pipeline": ("diffusers", "QwenImagePipeline"),
        "components": "Qwen/Qwen-Image",
        #: Qwen is guidance-distilled through true_cfg_scale and wants ~20 steps.
        "gen": {"num_inference_steps": 20, "true_cfg_scale": 4.0, "use_negative": True},
    },
    "flux": {
        "qint8": "flux-schnell-qint8.safetensors",
        "transformer": ("diffusers", "FluxTransformer2DModel"),
        "pipeline": ("diffusers", "FluxPipeline"),
        "components": _FREEPIK,
        #: schnell is a 4-step turbo model with no classifier-free guidance and
        #: no negative prompt (guidance_embeds is false in its config).
        "gen": {"num_inference_steps": 4, "guidance_scale": 0.0, "use_negative": False},
    },
}

ALIASES = {"qwen-image": "qwen", "flux-schnell": "flux", "flux.1-schnell": "flux"}


def is_gguf_model(name: str) -> bool:
    return canonical(name) in MODELS


def canonical(name: str) -> str:
    return ALIASES.get(name, name)


def _patch_safe_open() -> None:
    """transformers 5.14 passes backend= to safetensors.safe_open, which the
    installed safetensors does not accept. Drop the unknown kwarg. Must run
    after mmgp is imported - mmgp re-touches transformers and would undo it.
    """
    import safetensors
    import transformers.modeling_utils as mu

    if getattr(mu, "_cf_safe_open_patched", False):
        return
    original = mu.safe_open

    def wrapped(*args, **kwargs):
        kwargs.pop("backend", None)
        return original(*args, **kwargs)

    safetensors.safe_open = wrapped
    mu.safe_open = wrapped
    mu._cf_safe_open_patched = True


def _resolve_components(components: str) -> str:
    """A local snapshot glob resolves to its path; a bare repo id passes through
    for diffusers to resolve from its cache.
    """
    if components.startswith("~") or "*" in components:
        matches = glob.glob(os.path.expanduser(components))
        if not matches:
            raise MissingDataError(
                f"image-model components not found at {components}; the model "
                "cache is not populated"
            )
        return matches[0]
    return components


def load_pipeline_and_generate(
    name: str, width: int = 768, height: int = 432
) -> tuple[object, Callable, Callable]:
    """Load a pre-quantised GGUF model and return (pipeline, generate, release).

    The pipeline is streamed by mmgp so it fits a 6 GB card. The generate
    closure carries the per-model step/guidance/negative settings, so the caller
    (illustrate) does not need to know which model it is driving. ``release``
    frees the model's ~36 GB of CPU RAM and its VRAM once the draw stage is done,
    so it does not sit resident through the rest of the render.
    """
    spec = MODELS[canonical(name)]
    qint8 = MODELS_DIR / spec["qint8"]
    if not qint8.exists():
        raise MissingDataError(
            f"pre-quantised weights missing: {qint8}. Build them with "
            "scripts/build_prequant.py (one-time, runs on a machine with ~42 GB RAM)."
        )

    try:
        import importlib

        import torch  # noqa: F401
        import diffusers  # noqa: F401  (pull transformers.modeling_utils in first)
        from mmgp import offload, profile_type
    except ImportError as exc:
        raise MissingDataError(
            "torch, diffusers and mmgp are required for GGUF image models. "
            "See docs/setup/local-image-generation.md"
        ) from exc

    _patch_safe_open()

    tr_mod, tr_cls = spec["transformer"]
    pipe_mod, pipe_cls = spec["pipeline"]
    TransformerClass = getattr(importlib.import_module(tr_mod), tr_cls)
    PipelineClass = getattr(importlib.import_module(pipe_mod), pipe_cls)

    import torch

    # A prior stage (the voice model) may have left the card fragmented; clear
    # what it can before this model starts allocating on a 6 GB card.
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    transformer = offload.fast_load_transformers_model(
        str(qint8), modelClass=TransformerClass, verboseLevel=0
    )
    pipe = PipelineClass.from_pretrained(
        _resolve_components(spec["components"]),
        transformer=transformer,
        torch_dtype=torch.bfloat16,
    )
    # transformer is already qint8; only the text encoder gets quantised here.
    offload_obj = offload.profile(pipe, profile_type.VerylowRAM_LowVRAM,
                                  quantizeTransformer=False, verboseLevel=0)

    gen = spec["gen"]

    def generate(prompt: str, path: Path, image_seed: int) -> Path:
        kwargs = {k: v for k, v in gen.items() if k != "use_negative"}
        if gen["use_negative"]:
            kwargs["negative_prompt"] = NEGATIVE
        image = pipe(
            prompt=prompt,
            width=width,
            height=height,
            generator=torch.Generator(device="cpu").manual_seed(image_seed),
            **kwargs,
        ).images[0]
        image.save(path)
        return path

    def release() -> None:
        """Free the model's CPU RAM and VRAM. Safe to call more than once."""
        try:
            if offload_obj is not None and hasattr(offload_obj, "release"):
                offload_obj.release()
            offload.clear_caches()
        except Exception:
            pass
        try:
            import gc

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

    return pipe, generate, release
