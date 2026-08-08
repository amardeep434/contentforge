"""Wiring tests for the GGUF image backends and the Qwen->FLUX fallback.

None of these touch a GPU: the model loader is monkeypatched, so they exercise
selection and fallback logic without loading 20 GB of weights.
"""
from pathlib import Path

import pytest

from contentforge.visuals import gguf_backends
from contentforge import runtime


def test_canonical_resolves_aliases():
    assert gguf_backends.canonical("qwen-image") == "qwen"
    assert gguf_backends.canonical("flux-schnell") == "flux"
    assert gguf_backends.canonical("qwen") == "qwen"
    assert gguf_backends.canonical("stabilityai/sdxl-turbo") == "stabilityai/sdxl-turbo"


def test_is_gguf_model():
    assert gguf_backends.is_gguf_model("qwen")
    assert gguf_backends.is_gguf_model("flux-schnell")
    assert not gguf_backends.is_gguf_model("stabilityai/sdxl-turbo")


def test_default_uses_qwen(monkeypatch, tmp_path):
    loaded = []

    def fake_load(name, width=768, height=432, **kwargs):
        loaded.append(name)
        return object(), (lambda prompt, path, seed: path), (lambda: None)

    monkeypatch.delenv("CONTENTFORGE_IMAGE_MODEL", raising=False)
    monkeypatch.setattr(gguf_backends, "load_pipeline_and_generate", fake_load)
    # illustrate is imported lazily inside illustrator(); patch its source first.
    monkeypatch.setattr("contentforge.visuals.illustrate.illustrate", lambda *a, **k: [])

    draw = runtime.illustrator()
    draw(["a fan"], tmp_path)
    assert loaded == ["qwen"]


def test_qwen_failure_fails_loudly(monkeypatch, tmp_path):
    """A final render must never silently swap to a lower-quality model: if the
    default (Qwen) cannot load, the error propagates rather than falling back.
    """
    def fake_load(name, width=768, height=432, **kwargs):
        raise RuntimeError("simulated OOM at load")

    monkeypatch.delenv("CONTENTFORGE_IMAGE_MODEL", raising=False)
    monkeypatch.setattr(gguf_backends, "load_pipeline_and_generate", fake_load)
    monkeypatch.setattr("contentforge.visuals.illustrate.illustrate", lambda *a, **k: [])

    draw = runtime.illustrator()
    with pytest.raises(RuntimeError, match="simulated OOM at load"):
        draw(["a fan"], tmp_path)


def test_explicit_draft_model_still_fails_loudly(monkeypatch, tmp_path):
    """An explicit choice (e.g. flux for a draft) also propagates load errors."""
    def fake_load(name, width=768, height=432, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(gguf_backends, "load_pipeline_and_generate", fake_load)
    monkeypatch.setattr("contentforge.visuals.illustrate.illustrate", lambda *a, **k: [])

    draw = runtime.illustrator(model="flux")
    with pytest.raises(RuntimeError, match="simulated failure"):
        draw(["a fan"], tmp_path)


def test_missing_weights_raise_clear_error(monkeypatch):
    """Loading a model whose qint8 file is absent gives an actionable message."""
    monkeypatch.setattr(gguf_backends, "MODELS_DIR", Path("/nonexistent/models"))
    from contentforge.errors import MissingDataError

    with pytest.raises(MissingDataError, match="pre-quantised weights missing"):
        gguf_backends.load_pipeline_and_generate("qwen")
