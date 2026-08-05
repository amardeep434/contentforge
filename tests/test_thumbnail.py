"""Thumbnail: a real frame from the video, with a few huge words over it."""

import pytest
from PIL import Image

from contentforge.errors import MissingDataError
from contentforge.visuals.thumbnail import HEIGHT, WIDTH, compose


def hero(tmp_path, size=(1920, 1080)):
    path = tmp_path / "hero.png"
    Image.new("RGB", size, (240, 232, 216)).save(path)
    return path


def test_the_thumbnail_is_exactly_1280x720(tmp_path):
    out = compose(hero(tmp_path), "Ceiling Fans", tmp_path / "t.png")
    assert Image.open(out).size == (WIDTH, HEIGHT)


def test_a_portrait_hero_still_fills_the_frame_without_distortion(tmp_path):
    # A frame of the wrong aspect is cropped to cover, never squashed.
    out = compose(hero(tmp_path, size=(720, 1280)), "Air", tmp_path / "t.png")
    assert Image.open(out).size == (WIDTH, HEIGHT)


def test_the_headline_changes_the_pixels(tmp_path):
    src = hero(tmp_path)
    out = compose(src, "Big News", tmp_path / "t.png")
    assert list(Image.open(out).getdata()) != list(
        Image.open(src).convert("RGB").resize((WIDTH, HEIGHT)).getdata()
    )


def test_a_missing_hero_raises(tmp_path):
    with pytest.raises(MissingDataError, match="no hero frame"):
        compose(tmp_path / "absent.png", "Words", tmp_path / "t.png")


def test_an_empty_headline_raises(tmp_path):
    with pytest.raises(MissingDataError, match="needs a headline"):
        compose(hero(tmp_path), "   ", tmp_path / "t.png")


def test_too_many_words_is_truncated_not_raised(tmp_path):
    # A finished render must not die at the last stage; the metadata stage keeps
    # the hook short, and this is the backstop.
    out = compose(hero(tmp_path), "one two three four five six", tmp_path / "t.png")
    assert Image.open(out).size == (WIDTH, HEIGHT)


def test_a_long_headline_still_produces_a_valid_image(tmp_path):
    # Five words wraps to two lines and must still fit.
    out = compose(hero(tmp_path), "Why Your Fan Wastes Money", tmp_path / "t.png")
    assert Image.open(out).size == (WIDTH, HEIGHT)


def test_an_overlong_headline_is_truncated_not_crashed(tmp_path):
    # A finished render must never die at the last stage over a long headline.
    out = compose(hero(tmp_path), "one two three four five six seven", tmp_path / "t.png")
    assert Image.open(out).size == (WIDTH, HEIGHT)
