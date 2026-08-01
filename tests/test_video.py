"""ffmpeg composition. The argv is pure and asserted; ffmpeg itself is injected."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from contentforge.errors import MissingDataError
from contentforge.render.video import (
    FPS,
    build_commands,
    build_concat_file,
    build_filter_script,
    preview_command,
    render,
)
from contentforge.visuals.compose import Shot


def shots(n=2):
    return [
        Shot(f"img{i}.jpg", f"beat_{i}.wav", i * 5.0, 5.0, f"beat {i}")
        for i in range(n)
    ]


def test_every_image_reaches_the_command():
    argv, _ = build_commands(shots(3), Path("out.mp4"), Path("/w"))
    for i in range(3):
        assert f"img{i}.jpg" in argv


def test_the_narration_is_mapped_as_the_audio_track():
    argv, _ = build_commands(shots(2), Path("out.mp4"), Path("/w"))
    assert "-map" in argv and "2:a" in argv       # index 2 = the concat input
    assert "[outv]" in argv


def test_shortest_is_set_or_the_render_never_ends():
    # The stills are -loop 1, so without -shortest ffmpeg runs forever.
    argv, _ = build_commands(shots(), Path("out.mp4"), Path("/w"))
    assert "-shortest" in argv


def test_each_shot_gets_its_own_frame_count():
    # A single global duration, rounded once and repeated, drifts the picture
    # off the narration across a long video.
    s = [Shot("a.jpg", "a.wav", 0.0, 4.0, "x"), Shot("b.jpg", "b.wav", 4.0, 9.5, "y")]
    script = build_filter_script(s)
    assert f"d={int(round(4.0 * FPS))}" in script
    assert f"d={int(round(9.5 * FPS))}" in script


def test_the_filter_concatenates_every_segment():
    script = build_filter_script(shots(3))
    assert "concat=n=3:v=1:a=0[outv]" in script


def test_audio_clips_are_listed_in_order():
    text = build_concat_file(shots(3))
    assert text.startswith("ffconcat version 1.0")
    assert text.index("beat_0.wav") < text.index("beat_1.wav") < text.index("beat_2.wav")


def test_quotes_in_a_path_cannot_break_the_concat_file():
    s = [Shot("a.jpg", "it's/beat.wav", 0.0, 3.0, "x")]
    assert r"'\''" in build_concat_file(s)


def test_no_shots_raises():
    for fn in (build_concat_file, build_filter_script):
        with pytest.raises(MissingDataError):
            fn([])


def test_a_successful_render_returns_the_path(tmp_path):
    out = tmp_path / "v.mp4"

    def runner(argv, **kw):
        out.write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="")

    assert render(shots(), out, tmp_path / "w", runner=runner) == out


def test_a_failed_render_raises_with_ffmpeg_stderr(tmp_path):
    def runner(argv, **kw):
        return SimpleNamespace(returncode=1, stderr="Invalid data found\nline2")

    with pytest.raises(MissingDataError, match="Invalid data found"):
        render(shots(), tmp_path / "v.mp4", tmp_path / "w", runner=runner)


def test_a_partial_file_is_deleted_on_failure(tmp_path):
    # A truncated mp4 looks like success to everything downstream.
    out = tmp_path / "v.mp4"

    def runner(argv, **kw):
        out.write_bytes(b"half a file")
        return SimpleNamespace(returncode=1, stderr="boom")

    with pytest.raises(MissingDataError):
        render(shots(), out, tmp_path / "w", runner=runner)
    assert not out.exists()


def test_success_with_no_output_file_still_raises(tmp_path):
    def runner(argv, **kw):
        return SimpleNamespace(returncode=0, stderr="")

    with pytest.raises(MissingDataError, match="missing or empty"):
        render(shots(), tmp_path / "v.mp4", tmp_path / "w", runner=runner)


def test_sidecar_files_are_written_before_ffmpeg_runs(tmp_path):
    seen = {}

    def runner(argv, **kw):
        seen["concat_exists"] = (tmp_path / "w" / "audio.ffconcat").exists()
        seen["filter_exists"] = (tmp_path / "w" / "filter.txt").exists()
        (tmp_path / "v.mp4").write_bytes(b"x")
        return SimpleNamespace(returncode=0, stderr="")

    render(shots(), tmp_path / "v.mp4", tmp_path / "w", runner=runner)
    assert seen == {"concat_exists": True, "filter_exists": True}


def test_preview_command_is_shell_safe():
    cmd = preview_command(shots(), Path("out.mp4"), Path("/w"))
    assert cmd.startswith("ffmpeg")
    assert "filter.txt" in cmd
