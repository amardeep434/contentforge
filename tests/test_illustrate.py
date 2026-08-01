"""Local line-art generation. The GPU is injected; tests never load a model."""

from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from pathlib import Path

from contentforge.visuals.illustrate import (
    DEFAULT_MODEL,
    HOUSE_STYLE,
    NEGATIVE,
    TURBO_GUIDANCE,
    TURBO_STEPS,
    HOUSE_STYLE,
    NEGATIVE,
    build_prompt,
    illustrate,
)


def fake_generate(calls):
    def _generate(prompt, path, seed):
        calls.append((prompt, path, seed))
        path.write_bytes(b"png")
        return path

    return _generate


def test_house_style_leads_the_prompt():
    # Early tokens carry more weight in a short prompt, and the style is what
    # must never drift between shots.
    prompt = build_prompt("a dumbbell with a dollar sign")
    assert prompt.startswith(HOUSE_STYLE)
    assert prompt.endswith("a dumbbell with a dollar sign")


def test_an_empty_subject_raises():
    with pytest.raises(MissingDataError):
        build_prompt("   ")


def test_one_image_per_subject_in_order(tmp_path):
    calls = []
    made = illustrate(["a gym", "a crowd", "a street"], tmp_path,
                      generate=fake_generate(calls))
    assert len(made) == 3
    assert [m.path.name for m in made] == ["shot_001.png", "shot_002.png", "shot_003.png"]


def test_every_image_carries_the_same_style(tmp_path):
    calls = []
    illustrate(["a gym", "a crowd"], tmp_path, generate=fake_generate(calls))
    assert all(prompt.startswith(HOUSE_STYLE) for prompt, _, _ in calls)


def test_seeds_are_derived_so_a_rerun_reproduces_the_video(tmp_path):
    # A video whose pictures change on every render cannot be reviewed and then
    # re-rendered.
    first = illustrate(["a", "b"], tmp_path, seed=100, generate=fake_generate([]))
    second = illustrate(["a", "b"], tmp_path, seed=100, generate=fake_generate([]))
    assert [i.seed for i in first] == [i.seed for i in second] == [101, 102]


def test_different_run_seeds_give_different_images(tmp_path):
    a = illustrate(["x"], tmp_path, seed=1, generate=fake_generate([]))
    b = illustrate(["x"], tmp_path, seed=999, generate=fake_generate([]))
    assert a[0].seed != b[0].seed


def test_a_generator_that_writes_nothing_raises(tmp_path):
    def broken(prompt, path, seed):
        return path            # never writes

    with pytest.raises(MissingDataError, match="nothing on screen"):
        illustrate(["a"], tmp_path, generate=broken)


def test_no_subjects_raises(tmp_path):
    with pytest.raises(MissingDataError):
        illustrate([], tmp_path, generate=fake_generate([]))


def test_turbo_settings_are_what_the_distilled_models_expect():
    # Turbo checkpoints are distilled for 1-4 steps with no guidance; raising
    # either degrades output rather than improving it.
    assert TURBO_STEPS <= 4
    assert TURBO_GUIDANCE == 0.0


def test_the_negative_prompt_pushes_away_from_observed_failures():
    # "shading" was dropped: the reference frame has subtle shading and
    # excluding it flattened output away from the target, not toward it.
    for failure in ("photo", "3d render", "text", "grain"):
        assert failure in NEGATIVE


def test_the_default_model_is_the_small_one():
    # It fits a 6 GB card resident and is 3x faster than the XL variant.
    assert DEFAULT_MODEL == "stabilityai/sd-turbo"


# --- upscaling ---------------------------------------------------------------

def test_the_house_style_matches_the_reference_palette():
    # Checked against a native-resolution frame: cream background, not blue.
    assert "cream" in HOUSE_STYLE
    assert "blue" not in HOUSE_STYLE


def test_text_is_pushed_out_of_generated_images():
    # Diffusion garbles lettering; captions are composited afterwards.
    for word in ("text", "letters", "words"):
        assert word in NEGATIVE


def test_upscaling_lands_exactly_on_1080p(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from PIL import Image
    from contentforge.visuals import illustrate as mod

    src = tmp_path / "small.png"
    Image.new("RGB", (768, 432), "white").save(src)
    monkeypatch.setattr(mod, "UPSCALER", tmp_path / "fake-upscaler")
    (tmp_path / "fake-upscaler").write_text("")

    def runner(argv, **kw):
        out = Path(argv[argv.index("-o") + 1])
        Image.new("RGB", (3072, 1728), "white").save(out)
        return SimpleNamespace(returncode=0, stderr="")

    dest = mod.upscale(src, tmp_path / "big.png", runner=runner)
    assert Image.open(dest).size == (1920, 1080)


def test_a_missing_upscaler_says_where_to_look(tmp_path, monkeypatch):
    from contentforge.visuals import illustrate as mod
    monkeypatch.setattr(mod, "UPSCALER", tmp_path / "absent")
    with pytest.raises(MissingDataError, match="local-image-generation"):
        mod.upscale(tmp_path / "a.png", tmp_path / "b.png")
