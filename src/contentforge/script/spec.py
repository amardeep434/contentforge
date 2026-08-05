"""Turn a narration script into a per-beat visual specification.

The script says what is heard. This says what is seen: for every beat, the
subject to draw and the lettering to composite over it. Both come from one LLM
call over the whole script rather than one call per beat, because the model has
to see the surrounding beats to avoid drawing the same thing four times.

The lettering matters more than the drawing. Put a reference frame beside a
generated one and the difference is that theirs carries a heading and a
checklist, all legible, and the illustration exists to serve them.

Parsing is separated from calling so the awkward part - a model that wraps JSON
in prose, or returns the wrong number of beats - is unit tested without a
network.
"""

import json
import re
from dataclasses import dataclass, field, replace

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient

#: More than this on one frame and it stops reading as a glance-able point.
MAX_CHECKLIST_ITEMS = 4

#: Each heading word gets its own line, so this is a line count, not a width.
#: Four, not three: a real model returned "EMPTY ROOM, WASTED MONEY" and a
#: three-word cap failed the whole 20-beat chunk over one heading. The binding
#: constraint is the sheet's measured width, which `sheet.place` checks and
#: falls back from gracefully - this is only a sanity bound.
MAX_HEADING_WORDS = 4

SYSTEM = """You plan the visuals for a narrated explainer video in a hand-drawn
line-art style: bold black ink on plain cream, no photographs, no 3D.

For each narration beat you return:
- "subject": what to draw, as a concrete noun phrase. One scene, plainly
  describable. Never abstract ("the concept of risk") - draw the object that
  stands for it ("a wooden chair with one leg sawn short").
- "heading": at most four words in caps that name the point, or "" for none.
  Each word is drawn on its own line, so five words is five lines and will not
  fit. Count the words before you answer.
- "checklist": up to four very short ticked items, or [] for none.
- "chapter": the section number this beat belongs to, counting from 1, only
  ever increasing. Group consecutive beats that cover one idea into the same
  chapter; start a new chapter when the video turns to a distinctly new part.
  A typical video has 4 to 8 chapters.

Rules:
- Never put words in "subject". Lettering is composited separately; a diffusion
  model garbles text.
- Do not give every beat a heading and a checklist. A wall of lettering reads as
  a slide deck. Most beats are a drawing and nothing else.
- Never repeat a subject. A video where the same picture returns looks automated.

Return only a JSON array, one object per beat, in order. No prose, no code fence.
"""

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class BeatSpec:
    """One narrated beat and everything shown while it plays."""

    text: str
    subject: str
    heading: str = ""
    checklist: tuple[str, ...] = field(default_factory=tuple)
    stamp: str = ""
    chapter: int = 0

    @property
    def has_lettering(self) -> bool:
        return bool(self.heading or self.checklist)


#: Punctuation-only junk a model emits when it has nothing to put in a list.
#: Observed: gemma4 returned the literal string "[]" as a checklist item, which
#: would have been drawn on the frame as a ticked line reading "[]".
_PUNCTUATION_ONLY = frozenset("[]{}()-–—_.,:;\"' \t")


def _is_real_item(text: str) -> bool:
    return bool(text) and not set(text) <= _PUNCTUATION_ONLY


def _clean(raw: str) -> str:
    """Strip a code fence and any prose either side of the array."""
    stripped = _FENCE.sub("", raw).strip()
    start, end = stripped.find("["), stripped.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise MissingDataError(
            f"no JSON array in the visual spec response: {stripped[:160]!r}"
        )
    return stripped[start : end + 1]


def parse_spec(raw: str, beats: list[str]) -> list[BeatSpec]:
    """Pair a model response with the beats it describes.

    A count mismatch raises rather than truncating: a spec silently shortened by
    one leaves the last beat with no picture, which surfaces as a black frame
    twenty minutes into a render.
    """
    if not beats:
        raise MissingDataError("no beats to specify visuals for")
    try:
        entries = json.loads(_clean(raw))
    except json.JSONDecodeError as error:
        raise MissingDataError(f"visual spec is not valid JSON: {error}") from None
    if not isinstance(entries, list):
        raise MissingDataError("visual spec must be a JSON array, one entry per beat")
    if len(entries) != len(beats):
        raise MissingDataError(
            f"visual spec has {len(entries)} entries for {len(beats)} beats; "
            "a mismatch would leave a beat with nothing on screen"
        )

    specs = []
    for index, (entry, text) in enumerate(zip(entries, beats), start=1):
        if not isinstance(entry, dict):
            raise MissingDataError(f"visual spec entry {index} is not an object")
        subject = str(entry.get("subject", "")).strip()
        if not subject:
            raise MissingDataError(f"visual spec entry {index} has nothing to draw")
        heading = str(entry.get("heading", "") or "").strip().upper()
        if len(heading.split()) > MAX_HEADING_WORDS:
            raise MissingDataError(
                f"heading {heading!r} is longer than {MAX_HEADING_WORDS} words and "
                "will not fit the frame"
            )
        items = entry.get("checklist") or []
        if not isinstance(items, list):
            raise MissingDataError(f"checklist in entry {index} is not a list")
        checklist = tuple(
            cleaned for cleaned in (str(item).strip().upper() for item in items)
            if _is_real_item(cleaned)
        )
        if len(checklist) > MAX_CHECKLIST_ITEMS:
            raise MissingDataError(
                f"entry {index} has {len(checklist)} checklist items; more than "
                f"{MAX_CHECKLIST_ITEMS} stops being glance-able"
            )
        specs.append(BeatSpec(
            text=text, subject=subject, heading=heading, checklist=checklist,
            stamp=str(entry.get("stamp", "") or "").strip().upper(),
            chapter=_chapter_of(entry),
        ))
    return _monotonic_chapters(specs)


def _chapter_of(entry: dict) -> int:
    """A non-negative chapter number, or 0 for 'no chapter marker'."""
    raw = entry.get("chapter", 0)
    try:
        number = int(raw)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _monotonic_chapters(specs: list[BeatSpec]) -> list[BeatSpec]:
    """Chapters only ever climb. A model that renumbers mid-video (3, then 2)
    would flash an earlier chapter marker back onto a later beat; each beat
    inherits the highest chapter seen so far."""
    highest = 0
    fixed = []
    for spec in specs:
        highest = max(highest, spec.chapter)
        fixed.append(spec if spec.chapter == highest
                     else replace(spec, chapter=highest))
    return fixed


#: Beats per call. One call for a whole 200-beat script overruns both the token
#: budget and any sane HTTP timeout, and a single malformed response would then
#: cost the entire script. Small enough to come back quickly, large enough that
#: the model still sees its neighbours and can avoid drawing the same thing
#: twice in a row.
CHUNK = 20

#: A JSON object per beat runs 60-90 tokens. This leaves generous headroom for a
#: full chunk plus whatever preamble the model insists on.
MAX_TOKENS = 4000


def generate_chunk(client: LLMClient, beats: list[str], offset: int = 0,
                   total: int | None = None, attempts: int = 2) -> list[BeatSpec]:
    """Visuals for one run of consecutive beats.

    Retried once, because the failure mode is a model breaking one stated
    constraint in one entry - an over-long heading, a checklist of five - and
    the whole chunk of twenty beats should not be lost to it. A second sample
    usually complies; if it does not, the error names what was wrong.
    """
    if not beats:
        raise MissingDataError("no beats to specify visuals for")
    numbered = "\n\n".join(
        f"{offset + n}. {beat}" for n, beat in enumerate(beats, start=1)
    )
    scope = (
        f" (beats {offset + 1}-{offset + len(beats)} of {total})" if total else ""
    )
    user = (
        f"{len(beats)} narration beats follow{scope}. Return exactly "
        f"{len(beats)} JSON objects, in the same order.\n\n{numbered}"
    )
    last: MissingDataError | None = None
    for _ in range(max(1, attempts)):
        try:
            return parse_spec(client.complete(SYSTEM, user, max_tokens=MAX_TOKENS), beats)
        except MissingDataError as error:
            last = error
    raise last


def generate_spec(client: LLMClient, beats: list[str], chunk: int = CHUNK,
                  log=None) -> list[BeatSpec]:
    """Visuals for every beat, a chunk at a time.

    Subjects already used are fed forward so the model does not restart its
    imagination at every chunk boundary - a video where the same picture returns
    every twenty shots looks exactly as automated as it is.
    """
    if not beats:
        raise MissingDataError("no beats to specify visuals for")

    specs: list[BeatSpec] = []
    for start in range(0, len(beats), chunk):
        window = beats[start : start + chunk]
        made = generate_chunk(client, window, offset=start, total=len(beats))
        specs.extend(made)
        if log:
            log(f"    spec {len(specs)}/{len(beats)} beats")
    return specs


#: Sized against the reference frame, where the heading is about a fifth of the
#: frame width rather than a third. Lettering that fills the sheet reads as a
#: slide; lettering with room around it reads as a drawn document.
HEADING_SIZE = 64
BODY_SIZE = 34


def caption_lines(spec: BeatSpec, heading_size: int = HEADING_SIZE,
                  body_size: int = BODY_SIZE) -> list[tuple[str, int, str]]:
    """Lettering for one beat, in the form `caption.place_blocks` expects.

    A long heading is split across lines here rather than in the layout code:
    where a heading breaks is a content decision, and the layout stacks whatever
    lines it is handed.
    """
    lines: list[tuple[str, int, str]] = []
    for word in spec.heading.split():
        lines.append((word, heading_size, "heading"))
    for item in spec.checklist:
        lines.append((f"[x]  {item}", body_size, "body"))
    return lines
