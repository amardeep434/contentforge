from pathlib import Path

import pytest

from contentforge.niche import NicheConfig, load_niche
from contentforge.errors import MissingDataError

GOOD = """
[niche]
name = "demo"
title_format = "The Economics of Owning a {subject}"
[visual]
house_style = "line art"
negative = "photo"
bg = [240, 232, 216]
accent = [38, 122, 118]
image_model = "qwen"
[voice]
reference = "~/ref.wav"
pace = 0.80
music = false
[script]
system = "You write narration."
target_words = [2500, 3200]
"""

def _write(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True)
    (d / "niche.toml").write_text(text)
    return tmp_path

def test_loads_a_full_profile(tmp_path):
    cfg = load_niche("demo", _write(tmp_path, "demo", GOOD))
    assert cfg.name == "demo"
    assert cfg.title_format == "The Economics of Owning a {subject}"
    assert cfg.bg == (240, 232, 216)
    assert cfg.accent == (38, 122, 118)
    assert cfg.image_model == "qwen"
    assert cfg.pace == 0.80
    assert cfg.music is False
    assert cfg.target_words == (2500, 3200)
    assert cfg.voice_reference == Path("~/ref.wav").expanduser()
    assert cfg.script_system == "You write narration."

def test_missing_file_raises_with_path(tmp_path):
    with pytest.raises(MissingDataError, match="niche.toml"):
        load_niche("nope", tmp_path)

def test_malformed_missing_key_raises_naming_the_field(tmp_path):
    bad = GOOD.replace('image_model = "qwen"', "")
    with pytest.raises(MissingDataError, match="image_model"):
        load_niche("demo", _write(tmp_path, "demo", bad))

def test_bad_colour_raises(tmp_path):
    bad = GOOD.replace("bg = [240, 232, 216]", "bg = [240, 232]")
    with pytest.raises(MissingDataError, match="bg"):
        load_niche("demo", _write(tmp_path, "demo", bad))
