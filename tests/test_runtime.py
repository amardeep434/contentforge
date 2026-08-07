from pathlib import Path

from contentforge.niche import NicheConfig


def _cfg(**over):
    base = dict(name="n", title_format="T {subject}", house_style="HS", negative="NEG",
                bg=(1, 2, 3), accent=(4, 5, 6), image_model="flux",
                voice_reference=Path("/ref.wav"), pace=0.7, music=False,
                script_system="SYS", target_words=(100, 200))
    base.update(over)
    return NicheConfig(**base)


def test_illustrator_accepts_a_niche(monkeypatch):
    from contentforge import runtime
    captured = {}

    def fake_load(name, w=768, h=432, negative=None):
        captured["name"] = name
        captured["negative"] = negative
        return object(), (lambda p, path, seed: path), (lambda: None)

    monkeypatch.setattr("contentforge.visuals.gguf_backends.load_pipeline_and_generate", fake_load)
    monkeypatch.setattr("contentforge.visuals.illustrate.illustrate", lambda subjects, out_dir, **k: [])
    draw = runtime.illustrator(niche=_cfg(image_model="flux", negative="NEG"))
    draw(["a fan"], Path("/tmp"))          # triggers _prepare
    assert captured["name"] == "flux"      # image_model from the niche
    assert captured["negative"] == "NEG"   # negative from the niche


def test_speaker_uses_niche_reference_and_pace(monkeypatch):
    from contentforge import runtime
    cfg = _cfg(voice_reference=Path("/my/ref.wav"), pace=0.9)
    spk = runtime.speaker(niche=cfg)
    assert spk._reference == Path("/my/ref.wav")
    assert spk._speed == 0.9
