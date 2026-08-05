"""OmniVoice backend: cloned-voice narration, model injected so no GPU is needed."""

import numpy as np
import pytest
import soundfile as sf

from contentforge.errors import MissingDataError
from contentforge.voice import omnivoice_backend as ov


class FakeModel:
    """Records the call and returns a fixed waveform, like OmniVoice.generate."""

    def __init__(self, wave=None):
        self.wave = wave if wave is not None else np.zeros(ov.SAMPLE_RATE, dtype=np.float32)
        self.calls = []

    def generate(self, text, language=None, ref_audio=None, ref_text=None,
                 normalize_text=False, **kw):
        self.calls.append({"text": text, "ref_audio": ref_audio,
                           "ref_text": ref_text, "normalize": normalize_text})
        return [self.wave]


def reference(tmp_path):
    path = tmp_path / "ref.wav"
    sf.write(str(path), np.zeros(ov.SAMPLE_RATE, dtype=np.float32), ov.SAMPLE_RATE)
    return path


def test_a_beat_is_written_as_a_wav(tmp_path):
    model = FakeModel(np.ones(ov.SAMPLE_RATE, dtype=np.float32))
    out = ov.synthesise(model, "A gym is a subscription business.", tmp_path / "b.wav",
                        reference(tmp_path), ov.DEFAULT_REFERENCE_TEXT, normalize=False)
    assert out.exists()
    data, sr = sf.read(str(out))
    assert sr == ov.SAMPLE_RATE
    assert len(data) == ov.SAMPLE_RATE


def test_the_reference_voice_and_its_text_reach_the_model(tmp_path):
    model = FakeModel()
    ref = reference(tmp_path)
    ov.synthesise(model, "hello", tmp_path / "b.wav", ref,
                  "the reference transcript", normalize=False)
    call = model.calls[0]
    assert call["ref_audio"] == str(ref)
    assert call["ref_text"] == "the reference transcript"


def test_empty_text_raises(tmp_path):
    with pytest.raises(MissingDataError, match="nothing to narrate"):
        ov.synthesise(FakeModel(), "   ", tmp_path / "b.wav",
                      reference(tmp_path), "ref", normalize=False)


def test_a_missing_reference_raises(tmp_path):
    with pytest.raises(MissingDataError, match="no voice reference"):
        ov.synthesise(FakeModel(), "hi", tmp_path / "b.wav",
                      tmp_path / "absent.wav", "ref", normalize=False)


def test_empty_audio_from_the_model_raises(tmp_path):
    silent = FakeModel(np.zeros(0, dtype=np.float32))
    with pytest.raises(MissingDataError, match="no audio"):
        ov.synthesise(silent, "hi", tmp_path / "b.wav",
                      reference(tmp_path), "ref", normalize=False)


def test_normalisation_is_used_when_asked(tmp_path):
    model = FakeModel()
    ov.synthesise(model, "it costs 150 dollars", tmp_path / "b.wav",
                  reference(tmp_path), "ref", normalize=True)
    assert model.calls[0]["normalize"] is True


def test_the_default_reference_and_its_text_are_paired():
    # A wrong transcript degrades the clone, so the shipped pair must match the
    # shipped reference clip.
    assert ov.DEFAULT_REFERENCE.name == "iapetus-reference.wav"
    assert "ceiling fan" in ov.DEFAULT_REFERENCE_TEXT


def test_the_speed_is_passed_to_the_model(tmp_path):
    # Calibrated to land the cloned voice near the reference's 142 wpm.
    model = FakeModel()
    ov.synthesise(model, "hello", tmp_path / "b.wav", reference(tmp_path),
                  "ref", normalize=False, speed=0.8)
    assert model.calls[0].get("normalize") is False
    assert ov.DEFAULT_SPEED < 1.0     # slower than raw, to hit 142 wpm
