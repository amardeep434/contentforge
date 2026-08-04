"""The whole video, one stage at a time, into one run directory.

Every end-to-end render before this lived in a throwaway script, which meant the
fixes found by rendering - accent folding, rate limiting, edge-tts word
boundaries, text stacking into the block beneath it - were fixed in a module and
then re-wired by hand on the next run. This is the wiring, kept.

    script -> beats -> visual spec -> narration -> illustration -> lettering -> mp4

**Stages are resumable.** Each writes a named artefact into the run directory and
is skipped if that artefact is already there. A twenty-minute video is around
twenty minutes of GPU and TTS work; losing all of it because ffmpeg was missing
is the difference between a pipeline and a demo. Pass `force=True` to redo one.

**Nothing is faked.** A stage with a missing input raises. There is no fallback
that substitutes a blank frame or a silent clip, because both render as a
finished video that nobody watches closely enough to catch.
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError
from contentforge.script.spec import BeatSpec, caption_lines
from contentforge.visuals import caption, palette, sheet
from contentforge.visuals.compose import (
    assert_continuous,
    merge_short_beats,
    plan_shots,
    split_beats,
    total_duration,
)
from contentforge.voice.backends import Clip, measure_duration, synthesise_beats

SCRIPT_NAME = "script.txt"
SPEC_NAME = "spec.json"
MANIFEST_NAME = "manifest.json"
VIDEO_NAME = "video.mp4"

AUDIO_DIR = "audio"
RAW_DIR = "raw"
FRAME_DIR = "frames"
WORK_DIR = "work"


@dataclass(frozen=True)
class Stage:
    """What a stage did, for the run log and for the manifest."""

    name: str
    detail: str
    skipped: bool = False


def run_dir_for(root: Path, slug: str) -> Path:
    return root / slug


# --- script -----------------------------------------------------------------

SOURCES_NAME = "sources.json"


def load_or_write_script(run_dir: Path, script: str | None) -> str:
    """The script is the one artefact a human may hand-write."""
    path = run_dir / SCRIPT_NAME
    if script is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(script.strip() + "\n")
    if not path.exists():
        raise MissingDataError(
            f"no script at {path}. Write one there, pass --script-file, or give "
            "--topic with --source URLs to generate one"
        )
    text = path.read_text().strip()
    if not text:
        raise MissingDataError(f"{path} is empty; there is nothing to narrate")
    return text


def ensure_script(run_dir: Path, script: str | None,
                  writer: Callable[[Path], str] | None = None,
                  force: bool = False) -> tuple[str, Stage]:
    """Resolve the narration: hand-written, cached, or generated from sources.

    A hand-written `--script-file` always wins - a human who wrote a script did
    not do it to have it overwritten. Otherwise a cached `script.txt` is reused
    unless forced, and only when neither exists does the injected `writer`
    generate one from a topic and its sources.

    `writer` is injected so the whole front of the pipeline is testable without
    a network or an LLM, exactly like every other stage.
    """
    path = run_dir / SCRIPT_NAME
    if script is not None:
        return load_or_write_script(run_dir, script), Stage(
            "script", f"{len(script.split())} words, provided"
        )
    if path.exists() and not force:
        text = load_or_write_script(run_dir, None)
        return text, Stage("script", f"{len(text.split())} words, cached", skipped=True)
    if writer is None:
        # No cached script and nothing to generate from.
        return load_or_write_script(run_dir, None), Stage("script", "loaded")

    run_dir.mkdir(parents=True, exist_ok=True)
    text = writer(run_dir).strip()
    if not text:
        raise MissingDataError("script generation produced nothing to narrate")
    path.write_text(text + "\n")
    return text, Stage("script", f"{len(text.split())} words, generated")


def beats_for(script: str) -> list[str]:
    """Sentences, with the too-short ones folded into their predecessor."""
    return merge_short_beats(split_beats(script))


# --- visual spec ------------------------------------------------------------

def _spec_to_json(specs: list[BeatSpec]) -> str:
    return json.dumps(
        [
            {
                "text": spec.text,
                "subject": spec.subject,
                "heading": spec.heading,
                "checklist": list(spec.checklist),
            }
            for spec in specs
        ],
        indent=2,
    )


def _spec_from_json(raw: str) -> list[BeatSpec]:
    return [
        BeatSpec(
            text=entry["text"],
            subject=entry["subject"],
            heading=entry.get("heading", ""),
            checklist=tuple(entry.get("checklist", ())),
        )
        for entry in json.loads(raw)
    ]


def ensure_spec(run_dir: Path, beats: list[str],
                planner: Callable[[list[str]], list[BeatSpec]],
                force: bool = False) -> tuple[list[BeatSpec], Stage]:
    """Visual spec for every beat, cached on disk.

    Cached hard: it is the one stage worth reading and editing by hand before
    committing an hour of GPU time to it.
    """
    path = run_dir / SPEC_NAME
    if path.exists() and not force:
        specs = _spec_from_json(path.read_text())
        if len(specs) != len(beats):
            raise MissingDataError(
                f"{path} describes {len(specs)} beats but the script has "
                f"{len(beats)}. The script changed - rerun with --force spec"
            )
        return specs, Stage("spec", f"{len(specs)} beats, cached", skipped=True)

    specs = planner(beats)
    run_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(_spec_to_json(specs))
    lettered = sum(1 for spec in specs if spec.has_lettering)
    return specs, Stage("spec", f"{len(specs)} beats, {lettered} with lettering")


# --- narration --------------------------------------------------------------

def ensure_audio(run_dir: Path, beats: list[str],
                 speak: Callable[[str, Path], Path],
                 force: bool = False,
                 timer: Callable[[Path], float] = measure_duration
                 ) -> tuple[list[Clip], Stage]:
    """One clip per beat. Existing clips are re-measured, not re-synthesised."""
    out_dir = run_dir / AUDIO_DIR
    existing = sorted(out_dir.glob("beat_*.wav")) if out_dir.exists() else []
    if len(existing) == len(beats) and not force:
        clips = [
            Clip(path=path, duration_s=timer(path), text=beat)
            for path, beat in zip(existing, beats)
        ]
        return clips, Stage(
            "audio", f"{len(clips)} clips, {total_seconds_str(clips)}, cached",
            skipped=True,
        )

    clips = synthesise_beats(beats, out_dir, speak=speak, timer=timer)
    return clips, Stage("audio", f"{len(clips)} clips, {total_seconds_str(clips)}")


def total_seconds_str(clips: list[Clip]) -> str:
    seconds = sum(clip.duration_s for clip in clips)
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


# --- pictures ---------------------------------------------------------------

def ensure_illustrations(run_dir: Path, specs: list[BeatSpec],
                         illustrator: Callable[[list[str], Path], list],
                         force: bool = False) -> tuple[list[Path], Stage]:
    """One drawing per beat, at generation resolution, before lettering."""
    out_dir = run_dir / RAW_DIR
    wanted = [out_dir / f"shot_{index:03d}.png" for index in range(1, len(specs) + 1)]
    if all(path.exists() for path in wanted) and not force:
        return wanted, Stage("draw", f"{len(wanted)} images, cached", skipped=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    illustrator([spec.subject for spec in specs], out_dir)
    missing = [path for path in wanted if not path.exists()]
    if missing:
        raise MissingDataError(
            f"{len(missing)} illustrations were not written, starting with "
            f"{missing[0]}; a beat with no picture renders as a held black frame"
        )
    return wanted, Stage("draw", f"{len(wanted)} images")


def ensure_frames(run_dir: Path, specs: list[BeatSpec], raws: list[Path],
                  upscaler: Callable[[Path, Path], Path],
                  force: bool = False) -> tuple[list[Path], Stage]:
    """Upscale to 1080p, then composite the lettering on top.

    Order matters. Upscaling after lettering would soften the text - the whole
    reason lettering is drawn rather than generated is that it is exact.
    """
    if len(raws) != len(specs):
        raise MissingDataError(
            f"{len(raws)} drawings for {len(specs)} beats; they must correspond"
        )
    out_dir = run_dir / FRAME_DIR
    wanted = [out_dir / f"frame_{index:03d}.png" for index in range(1, len(specs) + 1)]
    if all(path.exists() for path in wanted) and not force:
        return wanted, Stage("letter", f"{len(wanted)} frames, cached", skipped=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    lettered = 0
    for spec, raw, target in zip(specs, raws, wanted):
        upscaler(raw, target)
        if not target.exists():
            raise MissingDataError(f"upscaling produced nothing for {raw}")
        palette.normalise(target)
        if not spec.has_lettering:
            continue
        letter_frame(target, spec)
        lettered += 1
    return wanted, Stage("letter", f"{len(wanted)} frames, {lettered} lettered")


def letter_frame(frame_path: Path, spec: BeatSpec) -> Path:
    """Draw the sheet, then the words inside it.

    The reference channel letters onto a drawn document rather than over the
    background. Doing the same makes placement deterministic: the sheet's corner
    is known, so nothing has to search the frame for a gap and hope one exists.

    Where the lettering will not fit a sheet, it falls back to the measured
    empty-space placement rather than failing the whole render - one
    over-optimistic heading should not cost twenty minutes of work already done.
    """
    from PIL import Image

    lines = caption_lines(spec)
    footer = bool(spec.stamp)
    with Image.open(frame_path) as image:
        frame_size = image.size
        side = sheet.quieter_side(image)
    try:
        area = sheet.place(frame_size, sheet.size_for(lines, footer=footer), side)
    except MissingDataError:
        blocks = caption.place_blocks(frame_path, lines)
        return caption.apply(frame_path, blocks, frame_path)

    sheet.draw(frame_path, area, stamp=spec.stamp, signature=bool(spec.stamp))
    blocks = caption.stack_blocks(lines, area.text_left, area.text_top)
    return caption.apply(frame_path, blocks, frame_path)


# --- render -----------------------------------------------------------------

SUBS_SRT = "subtitles.srt"
SUBS_VTT = "subtitles.vtt"


def write_subtitles(run_dir: Path, shots) -> None:
    """Timed captions beside the mp4, from the same shot timing it was cut to.

    The subtitle track is the timed transcript: one cue per beat, spanning
    exactly that beat's measured audio, so it cannot drift from the voice the
    way a re-transcription would.
    """
    from contentforge.render.subtitles import cues_from_shots, to_srt, to_vtt

    cues = cues_from_shots(shots)
    (run_dir / SUBS_SRT).write_text(to_srt(cues))
    (run_dir / SUBS_VTT).write_text(to_vtt(cues))


def ensure_video(run_dir: Path, clips: list[Clip], frames: list[Path],
                 renderer: Callable, force: bool = False) -> tuple[Path, Stage]:
    out_path = run_dir / VIDEO_NAME
    shots = plan_shots(clips, [str(frame) for frame in frames])
    assert_continuous(shots)
    if out_path.exists() and not force:
        return out_path, Stage("render", f"{out_path}, cached", skipped=True)

    renderer(shots, out_path, run_dir / WORK_DIR)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise MissingDataError(f"{out_path} is missing or empty after rendering")
    write_subtitles(run_dir, shots)
    minutes = total_duration(shots) / 60
    return out_path, Stage(
        "render", f"{out_path} ({minutes:.1f} min, {len(shots)} shots)"
    )


# --- the loop ---------------------------------------------------------------

def build_video(
    run_dir: Path,
    planner: Callable[[list[str]], list[BeatSpec]],
    speak: Callable[[str, Path], Path],
    illustrator: Callable[[list[str], Path], list],
    upscaler: Callable[[Path, Path], Path],
    renderer: Callable,
    script: str | None = None,
    scriptwriter: Callable[[Path], str] | None = None,
    force: set[str] | None = None,
    log: Callable[[str], None] = print,
    timer: Callable[[Path], float] = measure_duration,
) -> Path:
    """Every stage, in order, resuming whatever is already on disk.

    The callables are injected rather than imported so the whole loop is
    testable without a GPU, a TTS service or ffmpeg - which is what makes it
    safe to change.
    """
    force = force or set()
    run_dir.mkdir(parents=True, exist_ok=True)

    stages = []
    text, stage = ensure_script(run_dir, script, scriptwriter, "script" in force)
    stages.append(stage)
    beats = beats_for(text)
    log(f"  script   {len(text.split())} words, {len(beats)} beats")

    specs, stage = ensure_spec(run_dir, beats, planner, "spec" in force)
    stages.append(stage)
    clips, stage = ensure_audio(run_dir, beats, speak, "audio" in force, timer)
    stages.append(stage)
    raws, stage = ensure_illustrations(run_dir, specs, illustrator, "draw" in force)
    stages.append(stage)
    frames, stage = ensure_frames(run_dir, specs, raws, upscaler, "letter" in force)
    stages.append(stage)
    video, stage = ensure_video(run_dir, clips, frames, renderer, "render" in force)
    stages.append(stage)

    for entry in stages:
        log(f"  {entry.name:<8} {entry.detail}{'  (skipped)' if entry.skipped else ''}")
    write_manifest(run_dir, beats, specs, clips, video, stages)
    return video


def write_manifest(run_dir: Path, beats: list[str], specs: list[BeatSpec],
                   clips: list[Clip], video: Path, stages: list[Stage]) -> Path:
    """What this video is made of, beside the video.

    A rendered mp4 with no record of the beats, prompts and seeds behind it
    cannot be corrected - only regenerated and hoped over.
    """
    path = run_dir / MANIFEST_NAME
    path.write_text(json.dumps({
        "video": str(video),
        "duration_s": round(sum(clip.duration_s for clip in clips), 2),
        "beats": len(beats),
        "stages": [{"name": s.name, "detail": s.detail, "skipped": s.skipped}
                   for s in stages],
        "shots": [
            {
                "index": index,
                "text": spec.text,
                "subject": spec.subject,
                "heading": spec.heading,
                "checklist": list(spec.checklist),
                "duration_s": round(clip.duration_s, 2),
            }
            for index, (spec, clip) in enumerate(zip(specs, clips), start=1)
        ],
    }, indent=2))
    return path


def clean_run(run_dir: Path, keep_script: bool = True) -> None:
    """Throw away derived artefacts, keeping the hand-written input."""
    if not run_dir.exists():
        return
    script = (run_dir / SCRIPT_NAME).read_text() if (
        keep_script and (run_dir / SCRIPT_NAME).exists()
    ) else None
    shutil.rmtree(run_dir)
    if script is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / SCRIPT_NAME).write_text(script)
