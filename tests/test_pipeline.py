"""The end-to-end loop, driven entirely by injected fakes.

No GPU, no TTS service, no ffmpeg. The point of injecting every backend is that
the stage wiring - the part that used to live in a throwaway script and get
rebuilt by hand each run - is asserted on like any other code.
"""

import json
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.pipeline import (
    MANIFEST_NAME,
    SPEC_NAME,
    beats_for,
    build_video,
    clean_run,
    ensure_audio,
    ensure_frames,
    ensure_spec,
    load_or_write_script,
)
from contentforge.script.spec import BeatSpec

SCRIPT = (
    "A ceiling fan moves air but never cools it. "
    "The blades only push heat around the room. "
    "That is why an empty room does not need one running."
)


class Fakes:
    """Stand-ins that record what the loop asked them to do."""

    def __init__(self, headings=True):
        self.spoke, self.drew, self.upscaled, self.rendered = [], [], [], []
        self.headings = headings
        self.planned = 0

    def plan(self, beats):
        self.planned += 1
        return [
            BeatSpec(
                text=beat,
                subject=f"subject {n}",
                heading="LEGAL RISK" if self.headings and n == 1 else "",
            )
            for n, beat in enumerate(beats, start=1)
        ]

    def speak(self, text, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"RIFFfake")
        self.spoke.append(text)
        return path

    def timer(self, path):
        return 4.0

    def draw(self, subjects, out_dir):
        from PIL import Image

        out_dir.mkdir(parents=True, exist_ok=True)
        for index in range(1, len(subjects) + 1):
            # A real image, because the lettering stage measures it for empty
            # space before it decides where the words go.
            Image.new("RGB", (1920, 1080), (245, 241, 232)).save(
                out_dir / f"shot_{index:03d}.png"
            )
        self.drew.extend(subjects)
        return []

    def upscale(self, source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        self.upscaled.append(source)
        return target

    def render(self, shots, out_path, work_dir):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"mp4")
        self.rendered.append(shots)
        return out_path


def build(tmp_path, fakes, **kwargs):
    """Run the loop with lettering skipped - fonts are exercised in test_caption."""
    kwargs.setdefault("script", SCRIPT)
    return build_video(
        run_dir=tmp_path / "run",
        planner=fakes.plan,
        speak=fakes.speak,
        illustrator=fakes.draw,
        upscaler=fakes.upscale,
        renderer=fakes.render,
        timer=fakes.timer,
        log=lambda _: None,
        **kwargs,
    )


# --- script -----------------------------------------------------------------

def test_the_script_is_written_into_the_run_and_read_back(tmp_path):
    load_or_write_script(tmp_path, SCRIPT)
    assert load_or_write_script(tmp_path, None).startswith("A ceiling fan")


def test_a_missing_script_raises_rather_than_inventing_one(tmp_path):
    with pytest.raises(MissingDataError, match="no script at"):
        load_or_write_script(tmp_path, None)


def test_an_empty_script_raises(tmp_path):
    with pytest.raises(MissingDataError, match="nothing to narrate"):
        load_or_write_script(tmp_path, "   \n  ")


def test_beats_come_from_sentences():
    assert len(beats_for(SCRIPT)) == 3


# --- the whole loop ---------------------------------------------------------

def test_a_full_run_produces_a_video(tmp_path):
    fakes = Fakes()
    video = build(tmp_path, fakes)
    assert video.exists()
    assert len(fakes.spoke) == 3
    assert len(fakes.drew) == 3
    assert len(fakes.upscaled) == 3


def test_every_beat_gets_its_own_shot_timed_by_its_own_audio(tmp_path):
    fakes = Fakes(headings=False)
    build(tmp_path, fakes)
    shots = fakes.rendered[0]
    assert len(shots) == 3
    assert [shot.duration_s for shot in shots] == [4.0, 4.0, 4.0]
    assert shots[1].start_s == 4.0


def test_the_manifest_records_what_the_video_is_made_of(tmp_path):
    fakes = Fakes(headings=False)
    build(tmp_path, fakes)
    manifest = json.loads((tmp_path / "run" / MANIFEST_NAME).read_text())
    assert manifest["beats"] == 3
    assert manifest["duration_s"] == 12.0
    assert manifest["shots"][0]["subject"] == "subject 1"
    assert manifest["shots"][0]["text"].startswith("A ceiling fan")
    assert manifest["music"] is None   # no niche given


def test_the_manifest_records_the_niches_music_flag(tmp_path):
    from contentforge.niche import NicheConfig

    niche = NicheConfig(
        name="n", title_format="T {subject}", house_style="HS", negative="NEG",
        bg=(1, 2, 3), accent=(4, 5, 6), image_model="flux",
        voice_reference=Path("/ref.wav"), pace=0.7, music=True,
        script_system="SYS", metadata_system="MSYS", target_words=(100, 200),
    )
    fakes = Fakes(headings=False)
    build(tmp_path, fakes, niche=niche)
    manifest = json.loads((tmp_path / "run" / MANIFEST_NAME).read_text())
    assert manifest["music"] is True


# --- resuming ---------------------------------------------------------------

def test_a_second_run_regenerates_nothing(tmp_path):
    first = Fakes(headings=False)
    build(tmp_path, first)

    second = Fakes(headings=False)
    build(tmp_path, second, script=None)
    assert second.planned == 0
    assert second.spoke == []
    assert second.drew == []
    assert second.rendered == []


def test_forcing_a_stage_redoes_only_that_stage(tmp_path):
    build(tmp_path, Fakes(headings=False))

    again = Fakes(headings=False)
    build(tmp_path, again, script=None, force={"draw"})
    assert again.drew          # redrawn
    assert again.spoke == []   # narration untouched
    assert again.planned == 0


def test_an_edited_script_will_not_silently_reuse_the_old_spec(tmp_path):
    # Two beats of spec against three of script would leave a beat blank.
    fakes = Fakes(headings=False)
    build(tmp_path, fakes)
    longer = beats_for(SCRIPT) + ["A fourth sentence arrives here now."]
    with pytest.raises(MissingDataError, match="script changed"):
        ensure_spec(tmp_path / "run", longer, fakes.plan)


def test_cached_audio_is_re_measured_rather_than_trusted(tmp_path):
    fakes = Fakes()
    beats = beats_for(SCRIPT)
    ensure_audio(tmp_path, beats, fakes.speak, timer=fakes.timer)
    clips, stage = ensure_audio(tmp_path, beats, fakes.speak, timer=fakes.timer)
    assert stage.skipped
    assert [clip.duration_s for clip in clips] == [4.0, 4.0, 4.0]


# --- failure modes ----------------------------------------------------------

def test_an_illustrator_that_writes_nothing_raises(tmp_path):
    fakes = Fakes()
    fakes.draw = lambda subjects, out_dir: []
    with pytest.raises(MissingDataError, match="held black frame"):
        build(tmp_path, fakes)


def test_a_drawing_count_that_disagrees_with_the_spec_raises(tmp_path):
    fakes = Fakes()
    specs = fakes.plan(beats_for(SCRIPT))
    with pytest.raises(MissingDataError, match="must correspond"):
        ensure_frames(tmp_path, specs, [Path("only-one.png")], fakes.upscale)


def test_a_failed_stage_is_recorded_durably_with_what_remains(tmp_path):
    """A crash in one stage must leave status.json showing what worked, what
    failed and what is still pending - so a resume does not restart from zero."""
    import json

    fakes = Fakes()

    def boom(subjects, out_dir):
        raise RuntimeError("simulated OOM in draw")

    fakes.draw = boom
    with pytest.raises(RuntimeError, match="simulated OOM in draw"):
        build(tmp_path, fakes)

    status = json.loads((tmp_path / "run" / "meta" / "status.json").read_text())
    stages = status["stages"]
    assert stages["script"] == "ok"
    assert stages["spec"] == "ok"
    assert stages["audio"] == "ok"
    assert stages["draw"] == "failed"
    # render is downstream of draw and never ran; it must still read as pending.
    assert stages["render"] == "pending"
    assert status["failed"] == "draw"
    assert "render" in status["remaining"]
    assert "simulated OOM in draw" in status["error"]
    # the human trail exists too
    assert "FAILED" in (tmp_path / "run" / "meta" / "run.log").read_text()


def test_a_requested_stop_is_recorded_as_clean_and_resumable(tmp_path):
    """Ctrl-C mid-render must record a "stopped" (not "failed") status, with the
    finished stages kept, so a re-run resumes instead of restarting."""
    import json

    from contentforge import interrupt

    fakes = Fakes()
    interrupt.clear()
    interrupt._stop.set()  # request a stop before the first per-item stage (audio)
    try:
        with pytest.raises(interrupt.StopRequested):
            build(tmp_path, fakes)
    finally:
        interrupt.clear()

    status = json.loads((tmp_path / "run" / "meta" / "status.json").read_text())
    stages = status["stages"]
    assert stages["script"] == "ok"
    assert stages["spec"] == "ok"
    assert stages["audio"] == "stopped"  # clean stop, not "failed"
    assert stages["render"] == "pending"
    assert status["stopped"] == "audio"
    assert "draw" in status["remaining"]
    assert "error" not in status  # a stop is not an error
    assert "STOPPED" in (tmp_path / "run" / "meta" / "run.log").read_text()


def test_an_upscaler_that_writes_nothing_raises(tmp_path):
    fakes = Fakes(headings=False)
    fakes.upscale = lambda source, target: target
    with pytest.raises(MissingDataError, match="upscaling produced nothing"):
        build(tmp_path, fakes)


def test_a_renderer_that_writes_nothing_raises(tmp_path):
    fakes = Fakes(headings=False)
    fakes.render = lambda shots, out_path, work_dir: out_path
    with pytest.raises(MissingDataError, match="missing or empty"):
        build(tmp_path, fakes)


def test_cleaning_keeps_the_hand_written_script(tmp_path):
    build(tmp_path, Fakes(headings=False))
    run_dir = tmp_path / "run"
    clean_run(run_dir)
    assert (run_dir / "meta" / "script.txt").exists()
    assert not (run_dir / SPEC_NAME).exists()
    assert not (run_dir / "final" / "video.mp4").exists()


# --- script generation (stage 0) --------------------------------------------

def test_a_provided_script_is_used_verbatim(tmp_path):
    from contentforge.pipeline import ensure_script

    text, stage = ensure_script(tmp_path, "A fan moves air.", writer=None)
    assert text == "A fan moves air."
    assert "provided" in stage.detail


def test_a_cached_script_is_reused_and_the_writer_not_called(tmp_path):
    from contentforge.pipeline import SCRIPT_NAME, ensure_script

    (tmp_path / SCRIPT_NAME).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / SCRIPT_NAME).write_text("Cached narration here.\n")
    called = []
    text, stage = ensure_script(tmp_path, None,
                                writer=lambda d: called.append(1) or "new")
    assert text == "Cached narration here."
    assert stage.skipped
    assert called == []


def test_the_writer_generates_when_nothing_exists(tmp_path):
    from contentforge.pipeline import SCRIPT_NAME, ensure_script

    text, stage = ensure_script(tmp_path, None,
                                writer=lambda d: "Generated from sources [1].")
    assert "Generated from sources" in text
    assert "generated" in stage.detail
    assert (tmp_path / SCRIPT_NAME).exists()   # persisted for reruns


def test_forcing_script_regenerates_over_a_cached_one(tmp_path):
    from contentforge.pipeline import SCRIPT_NAME, ensure_script

    (tmp_path / SCRIPT_NAME).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / SCRIPT_NAME).write_text("old\n")
    text, _ = ensure_script(tmp_path, None, writer=lambda d: "fresh [1]", force=True)
    assert text == "fresh [1]"


def test_a_writer_that_produces_nothing_raises(tmp_path):
    from contentforge.pipeline import ensure_script

    with pytest.raises(MissingDataError, match="nothing to narrate"):
        ensure_script(tmp_path, None, writer=lambda d: "   ")


def test_no_script_and_no_writer_raises_with_guidance(tmp_path):
    from contentforge.pipeline import ensure_script

    with pytest.raises(MissingDataError, match="--topic"):
        ensure_script(tmp_path, None, writer=None)


def test_build_video_generates_a_script_when_given_a_writer(tmp_path):
    fakes = Fakes(headings=False)
    build_video(
        run_dir=tmp_path / "run",
        planner=fakes.plan, speak=fakes.speak, illustrator=fakes.draw,
        upscaler=fakes.upscale, renderer=fakes.render, timer=fakes.timer,
        log=lambda _: None,
        script=None,
        scriptwriter=lambda d: SCRIPT,
    )
    assert (tmp_path / "run" / "meta" / "script.txt").read_text().startswith("A ceiling fan")
    assert len(fakes.rendered[0]) == 3


def test_a_full_run_writes_timed_subtitles(tmp_path):
    from contentforge.pipeline import SUBS_SRT, SUBS_VTT
    build(tmp_path, Fakes(headings=False))
    run = tmp_path / "run"
    srt = (run / SUBS_SRT).read_text()
    assert "00:00:00,000 --> 00:00:04,000" in srt
    assert (run / SUBS_VTT).read_text().startswith("WEBVTT")


# --- lettering style --------------------------------------------------------

def test_a_heading_only_beat_is_drawn_without_a_sheet(tmp_path):
    # The reference's dominant frame is one word on an empty background, no
    # document around it. A sheet for a single word reads as a form to fill in.
    from PIL import Image
    from contentforge.pipeline import letter_frame
    from contentforge.script.spec import BeatSpec
    from contentforge.visuals import sheet

    frame = tmp_path / "f.png"
    Image.new("RGB", (1920, 1080), (240, 232, 216)).save(frame)
    drawn = {"sheet": False}
    original = sheet.draw
    sheet.draw = lambda *a, **k: drawn.__setitem__("sheet", True)
    try:
        letter_frame(frame, BeatSpec(text="t", subject="s", heading="TRUTH"))
    finally:
        sheet.draw = original
    assert drawn["sheet"] is False


def test_a_checklist_beat_still_uses_the_sheet(tmp_path):
    from PIL import Image
    from contentforge.pipeline import letter_frame
    from contentforge.script.spec import BeatSpec
    from contentforge.visuals import sheet

    frame = tmp_path / "f.png"
    Image.new("RGB", (1920, 1080), (240, 232, 216)).save(frame)
    drawn = {"sheet": False}
    original = sheet.draw
    sheet.draw = lambda *a, **k: drawn.__setitem__("sheet", True) or frame
    try:
        letter_frame(frame, BeatSpec(text="t", subject="s", heading="LEGAL",
                                     checklist=("AIR INTAKE", "VENTILATION")))
    finally:
        sheet.draw = original
    assert drawn["sheet"] is True


# --- metadata + thumbnail are made by `make`, reviewable before publish ------

def _meta():
    from contentforge.publish.metadata import Metadata
    return Metadata(title="How Fans Work", description="They move air.",
                    tags=("fans", "cooling"))


def test_make_writes_metadata_and_thumbnail_for_review(tmp_path):
    from contentforge.pipeline import METADATA_NAME, THUMBNAIL_NAME
    fakes = Fakes(headings=False)
    build(tmp_path, fakes, metadata_writer=lambda script, sources: _meta())
    run = tmp_path / "run"
    assert (run / METADATA_NAME).exists()
    assert (run / THUMBNAIL_NAME).exists()      # a real 1280x720 png
    from PIL import Image
    assert Image.open(run / THUMBNAIL_NAME).size == (1280, 720)


def test_metadata_round_trips_through_disk(tmp_path):
    from contentforge.pipeline import load_metadata
    build(tmp_path, Fakes(headings=False),
          metadata_writer=lambda script, sources: _meta())
    meta = load_metadata(tmp_path / "run")
    assert meta.title == "How Fans Work"
    assert meta.tags == ("fans", "cooling")


def test_publish_side_load_metadata_missing_raises(tmp_path):
    from contentforge.pipeline import load_metadata
    with pytest.raises(MissingDataError, match="run .pipeline make"):
        load_metadata(tmp_path)


def test_the_metadata_writer_receives_the_script(tmp_path):
    seen = {}
    def writer(script, sources):
        seen["script"] = script
        return _meta()
    build(tmp_path, Fakes(headings=False), metadata_writer=writer)
    assert seen["script"].startswith("A ceiling fan")


def test_metadata_and_thumbnail_are_cached_on_a_second_run(tmp_path):
    calls = []
    def writer(script, sources):
        calls.append(1)
        return _meta()
    build(tmp_path, Fakes(headings=False), metadata_writer=writer)
    build(tmp_path, Fakes(headings=False), script=None, metadata_writer=writer)
    assert len(calls) == 1          # not regenerated on the second run


def test_forcing_metadata_regenerates_it(tmp_path):
    calls = []
    def writer(script, sources):
        calls.append(1)
        return _meta()
    build(tmp_path, Fakes(headings=False), metadata_writer=writer)
    build(tmp_path, Fakes(headings=False), script=None, metadata_writer=writer,
          force={"metadata"})
    assert len(calls) == 2


def test_run_dir_is_grouped_by_niche(tmp_path):
    from contentforge.pipeline import run_dir_for

    assert run_dir_for(tmp_path, "biz", "laundromat") == (
        tmp_path / "biz" / "videos" / "laundromat"
    )


def test_build_writes_into_work_meta_final(tmp_path):
    fakes = Fakes()
    build(tmp_path, fakes)                 # run_dir defaults to tmp_path / "run"
    run = tmp_path / "run"
    assert (run / "meta" / "spec.json").exists()
    assert (run / "meta" / "status.json").exists()
    assert (run / "meta" / "manifest.json").exists()
    assert (run / "work" / "audio").is_dir()
    assert (run / "work" / "raw").is_dir()
    assert (run / "final" / "video.mp4").exists()
    assert (run / "final" / "subtitles.srt").exists()


def test_normalise_writes_the_given_background(tmp_path):
    from PIL import Image
    from contentforge.visuals import palette
    src = tmp_path / "x.png"
    dst = tmp_path / "y.png"
    # A solid fill at the reference background colour flattens to itself (no
    # texture, no chroma to stretch), so the final background-snap is the only
    # thing left that can move a pixel - which is exactly what `background`
    # controls.
    Image.new("RGB", (32, 32), palette.REFERENCE_BACKGROUND).save(src)
    palette.normalise(src, dst, background=(1, 2, 3))
    pixels = list(Image.open(dst).convert("RGB").getdata())
    assert pixels[0] == (1, 2, 3)
    assert pixels.count((1, 2, 3)) == len(pixels)


def test_chapter_label_accepts_a_colour():
    from contentforge.visuals import caption
    block = caption.chapter_label((1920, 1080), 2, colour=(4, 5, 6))
    assert block.colour == (4, 5, 6)
