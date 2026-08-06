#!/usr/bin/env python
"""One-time: turn the GGUF image models into pre-quantised qint8 weights.

The GGUF files (city96/FLUX.1-schnell-gguf, city96/Qwen-Image-gguf) can't be fed
to mmgp directly, and dequantising them on every run costs ~42 GB RAM for Qwen -
too much for a memory-limited container. This script does that dequant once and
saves a qint8 file that reloads with roughly half the RAM and no per-run dequant.
The pixels are identical to the runtime dequant path (same quanto qint8); this
only moves *when* the quantisation happens.

Run on a machine with ~42 GB RAM and the GGUFs already in the HF cache:

    python scripts/build_prequant.py            # both
    python scripts/build_prequant.py flux       # just one

Outputs to ~/.local/share/contentforge/models/:
    flux-schnell-qint8.safetensors   (~12 GB)
    qwen-image-qint8.safetensors     (~20 GB)
    flux-schnell-cfg/config.json     (the schnell transformer config)
"""
import glob
import json
import os
import sys
import time

import torch
import torch.nn as nn
import diffusers  # noqa: F401  (pull transformers.modeling_utils in before patching)
from mmgp import offload
from diffusers import (
    FluxTransformer2DModel,
    GGUFQuantizationConfig,
    QwenImageTransformer2DModel,
)
from diffusers.quantizers.gguf.utils import dequantize_gguf_tensor

# transformers 5.14 passes backend= to safetensors.safe_open, which the installed
# safetensors rejects; drop the unknown kwarg. Must come after mmgp is imported.
import safetensors
import transformers.modeling_utils as _mu

_orig_safe_open = _mu.safe_open


def _safe_open(*args, **kwargs):
    kwargs.pop("backend", None)
    return _orig_safe_open(*args, **kwargs)


safetensors.safe_open = _safe_open
_mu.safe_open = _safe_open

OUT = os.path.expanduser("~/.local/share/contentforge/models")

#: FLUX.1-schnell's transformer config. schnell ships gated, so the config is
#: written out explicitly here: 19 double + 38 single layers, guidance disabled
#: (it is a 4-step turbo model with no classifier-free guidance).
FLUX_SCHNELL_CONFIG = {
    "_class_name": "FluxTransformer2DModel",
    "_diffusers_version": "0.30.0",
    "attention_head_dim": 128,
    "guidance_embeds": False,
    "in_channels": 64,
    "joint_attention_dim": 4096,
    "num_attention_heads": 24,
    "num_layers": 19,
    "num_single_layers": 38,
    "patch_size": 1,
    "pooled_projection_dim": 768,
}


def _dequantise(TrCls, gguf, cfg_dir):
    tr = TrCls.from_single_file(
        gguf,
        config=cfg_dir,
        quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
        torch_dtype=torch.bfloat16,
    )
    for module in tr.modules():
        for pname, p in list(module.named_parameters(recurse=False)):
            if hasattr(p, "quant_type") and p.quant_type is not None:
                deq = dequantize_gguf_tensor(p).to(torch.bfloat16).contiguous()
                setattr(module, pname, nn.Parameter(deq, requires_grad=False))
    return tr


def _build(name, TrCls, gguf, cfg_dir, cfg_json):
    out = os.path.join(OUT, f"{name}-qint8.safetensors")
    if os.path.exists(out):
        print(f"[{name}] exists, skipping: {out}")
        return
    print(f"[{name}] dequantising {os.path.basename(gguf)} ...")
    t0 = time.time()
    tr = _dequantise(TrCls, gguf, cfg_dir)
    print(f"[{name}] quantising to qint8 and saving -> {out}")
    offload.save_model(
        tr, out, do_quantize=True, quantizationType=offload.qint8,
        config_file_path=cfg_json, verboseLevel=1,
    )
    del tr
    import gc

    gc.collect()
    print(f"[{name}] done, {os.path.getsize(out) / 1e9:.1f} GB in {time.time() - t0:.0f}s")


def main():
    os.makedirs(OUT, exist_ok=True)

    # FLUX needs a directory containing config.json for from_single_file.
    flux_cfg_dir = os.path.join(OUT, "flux-schnell-cfg")
    os.makedirs(flux_cfg_dir, exist_ok=True)
    flux_cfg_json = os.path.join(flux_cfg_dir, "config.json")
    if not os.path.exists(flux_cfg_json):
        with open(flux_cfg_json, "w") as f:
            json.dump(FLUX_SCHNELL_CONFIG, f, indent=2)

    def find(pattern):
        matches = glob.glob(os.path.expanduser(pattern))
        if not matches:
            raise SystemExit(f"not found in HF cache: {pattern}")
        return matches[0]

    flux_gguf = find(
        "~/.cache/huggingface/hub/models--city96--FLUX.1-schnell-gguf/snapshots/*/flux1-schnell-Q8_0.gguf"
    )
    qwen_gguf = find(
        "~/.cache/huggingface/hub/models--city96--Qwen-Image-gguf/snapshots/*/qwen-image-Q8_0.gguf"
    )
    qwen_cfg_dir = os.path.dirname(
        find("~/.cache/huggingface/hub/models--Qwen--Qwen-Image/snapshots/*/transformer/config.json")
    )

    target = sys.argv[1] if len(sys.argv) > 1 else "both"
    if target in ("flux", "both"):
        _build("flux-schnell", FluxTransformer2DModel, flux_gguf, flux_cfg_dir, flux_cfg_json)
    if target in ("qwen", "both"):
        _build("qwen-image", QwenImageTransformer2DModel, qwen_gguf, qwen_cfg_dir,
               os.path.join(qwen_cfg_dir, "config.json"))
    print("done")


if __name__ == "__main__":
    main()
