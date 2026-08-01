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
from dataclasses import dataclass, field

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient

#: More than this on one frame and it stops reading as a glance-able point.
MAX_CHECKLIST_ITEMS = 4

#: Long headings wrap badly at 92px against a 1920px frame.
MAX_HEADING_WORDS = 3

SYSTEM = """You plan the visuals for a narrated explainer video in a hand-drawn
line-art style: bold black ink on plain cream, no photographs, no 3D.

For each narration beat you return:
- "subject": what to draw, as a concrete noun phrase. One scene, plainly
  describable. Never abstract ("the concept of risk") - draw the object that
  stands for it ("a wooden chair with one leg sawn short").
- "heading": two or three words in caps that name the point, or "" for none.
- "checklist": up to four very short ticked items, or [] for none.

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

    @property
    def has_lettering(self) -> bool:
        return bool(self.heading or self.checklist)


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
        checklist = tuple(str(item).strip().upper() for item in items if str(item).strip())
        if len(checklist) > MAX_CHECKLIST_ITEMS:
            raise MissingDataError(
                f"entry {index} has {len(checklist)} checklist items; more than "
                f"{MAX_CHECKLIST_ITEMS} stops being glance-able"
            )
        specs.append(BeatSpec(
            text=text, subject=subject, heading=heading, checklist=checklist,
            stamp=str(entry.get("stamp", "") or "").strip().upper(),
        ))
    return specs


def generate_spec(client: LLMClient, beats: list[str]) -> list[BeatSpec]:
    """One call for the whole script, so the model can avoid repeating itself."""
    if not beats:
        raise MissingDataError("no beats to specify visuals for")
    numbered = "\n\n".join(f"{n}. {beat}" for n, beat in enumerate(beats, start=1))
    user = (
        f"{len(beats)} narration beats follow. Return exactly {len(beats)} JSON "
        f"objects, in the same order.\n\n{numbered}"
    )
    return parse_spec(client.complete(SYSTEM, user, max_tokens=8000), beats)


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
