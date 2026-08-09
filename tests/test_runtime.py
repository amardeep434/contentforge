from pathlib import Path

import pytest

from contentforge.niche import NicheConfig


def _cfg(**over):
    base = dict(name="n", title_format="T {subject}", house_style="HS", negative="NEG",
                bg=(1, 2, 3), accent=(4, 5, 6), image_model="flux",
                voice_reference=Path("/ref.wav"), pace=0.7, music=False,
                script_system="SYS", metadata_system="MSYS {title_format}",
                target_words=(100, 200))
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


class _FakeLLM:
    def __init__(self):
        self.seen_system = None

    def complete(self, system, user, max_tokens=0):
        self.seen_system = system
        return '{"title": "x", "description": "y", "tags": ["a"]}'


def test_metadata_writer_fills_the_niches_title_format_into_its_prompt():
    from contentforge import runtime
    cfg = _cfg(title_format="T {subject}", metadata_system="Titles look like {title_format}.")
    client = _FakeLLM()
    write = runtime.metadata_writer(niche=cfg, client=client)
    write("a script")
    assert client.seen_system == "Titles look like T {subject}."


def test_metadata_writer_with_no_niche_sends_no_custom_system():
    from contentforge import runtime
    from contentforge.publish.metadata import SYSTEM
    client = _FakeLLM()
    write = runtime.metadata_writer(niche=None, client=client)
    write("a script")
    assert client.seen_system == SYSTEM


def test_source_from_transcript_builds_a_source():
    from contentforge import runtime
    src = runtime.source_from_transcript("Owning a Laundromat", "THE TRANSCRIPT")
    assert src.text == "THE TRANSCRIPT"
    assert src.title == "Owning a Laundromat"
    assert src.url.startswith("transcript:")


def test_scriptwriter_uses_prebuilt_transcript_source(tmp_path, monkeypatch):
    from contentforge import runtime
    src = runtime.source_from_transcript("T", "TRANSCRIPT")
    seen = {}

    def fake_generate_script(client, topic, sources, shape, **kw):
        seen["sources"] = sources
        return "SCRIPT"

    monkeypatch.setattr("contentforge.script.generate.generate_script", fake_generate_script)
    monkeypatch.setattr("contentforge.script.validate.find_violations", lambda s, sources: [])
    monkeypatch.setattr("contentforge.sourcing.fetch.save_sources", lambda sources, run_dir: None)
    monkeypatch.setattr(runtime, "llm_client", lambda: object())
    writer = runtime.scriptwriter("T", [], sources=[src])
    assert writer(tmp_path) == "SCRIPT"
    assert seen["sources"][0].text == "TRANSCRIPT"     # the transcript, not a fetched URL


def test_scriptwriter_retries_feeding_back_the_violations_until_it_validates(tmp_path, monkeypatch):
    from contentforge import runtime
    src = runtime.source_from_transcript("T", "TRANSCRIPT")
    feedback_seen = []

    def fake_generate_script(client, topic, sources, shape, **kw):
        feedback_seen.append(kw.get("feedback"))
        return "BAD" if len(feedback_seen) == 1 else "GOOD"

    def fake_find_violations(script, sources):
        return ["reproduces 12 words verbatim"] if script == "BAD" else []

    monkeypatch.setattr("contentforge.script.generate.generate_script", fake_generate_script)
    monkeypatch.setattr("contentforge.script.validate.find_violations", fake_find_violations)
    monkeypatch.setattr("contentforge.sourcing.fetch.save_sources", lambda sources, run_dir: None)
    monkeypatch.setattr(runtime, "llm_client", lambda: object())

    writer = runtime.scriptwriter("T", [], sources=[src])
    assert writer(tmp_path) == "GOOD"
    assert feedback_seen[0] is None                              # first draft: no feedback
    assert feedback_seen[1] == ["reproduces 12 words verbatim"]  # second: fed the violation


def test_scriptwriter_hard_fails_after_the_attempt_cap(tmp_path, monkeypatch):
    from contentforge import runtime
    from contentforge.script.validate import ValidationError
    src = runtime.source_from_transcript("T", "TRANSCRIPT")
    calls = []

    def fake_generate_script(client, topic, sources, shape, **kw):
        calls.append(1)
        return "BAD"

    monkeypatch.setattr("contentforge.script.generate.generate_script", fake_generate_script)
    monkeypatch.setattr("contentforge.script.validate.find_violations",
                        lambda script, sources: ["still verbatim"])
    monkeypatch.setattr("contentforge.sourcing.fetch.save_sources", lambda sources, run_dir: None)
    monkeypatch.setattr(runtime, "llm_client", lambda: object())

    writer = runtime.scriptwriter("T", [], sources=[src])
    with pytest.raises(ValidationError, match="after"):
        writer(tmp_path)
    assert len(calls) == runtime.SCRIPT_ATTEMPTS   # bounded, does not loop forever
