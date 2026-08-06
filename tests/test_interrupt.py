"""Graceful stop and partial-resume: a stopped render keeps finished items and
resumes without redoing them."""
import json

import pytest
from PIL import Image

from contentforge import interrupt
from contentforge.visuals.illustrate import illustrate
from contentforge.voice.backends import synthesise_beats


@pytest.fixture(autouse=True)
def _clear_flag():
    interrupt.clear()
    yield
    interrupt.clear()


def test_check_raises_only_when_a_stop_was_requested():
    interrupt.check()  # not requested: no-op
    interrupt._stop.set()
    with pytest.raises(interrupt.StopRequested):
        interrupt.check()


def test_illustrate_skips_images_already_on_disk(tmp_path):
    """A draw resumed after a stop must not redraw finished images (~4 min each)."""
    for index in (1, 2):
        Image.new("RGB", (8, 8), (0, 0, 0)).save(tmp_path / f"shot_{index:03d}.png")

    drawn = []

    def generate(prompt, path, seed):
        drawn.append(path.name)
        Image.new("RGB", (8, 8), (255, 255, 255)).save(path)
        return path

    illustrate(["a", "b", "c"], tmp_path, generate=generate)
    assert drawn == ["shot_003.png"]  # only the missing image is generated


def test_synthesise_skips_clips_already_on_disk(tmp_path):
    (tmp_path / "beat_001.wav").write_bytes(b"RIFFdone")

    spoken = []

    def speak(text, path):
        spoken.append(text)
        path.write_bytes(b"RIFFnew")
        return path

    synthesise_beats(["one", "two"], tmp_path, speak=speak, timer=lambda p: 1.0)
    assert spoken == ["two"]  # the finished clip is reused, not re-synthesised


def test_illustrate_stops_between_images_when_requested(tmp_path):
    """A stop requested mid-draw finishes the current image, then raises - it
    never leaves a half-written file, and finished images stay."""
    drawn = []

    def generate(prompt, path, seed):
        drawn.append(path.name)
        Image.new("RGB", (8, 8), (255, 255, 255)).save(path)
        interrupt._stop.set()  # request a stop right after finishing this image
        return path

    with pytest.raises(interrupt.StopRequested):
        illustrate(["a", "b", "c"], tmp_path, generate=generate)
    # exactly one image was drawn (the next iteration's check() stopped it)
    assert drawn == ["shot_001.png"]
    assert (tmp_path / "shot_001.png").exists()
    assert not (tmp_path / "shot_002.png").exists()
