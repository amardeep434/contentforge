"""Script generation grounded in fetched sources.

There is no script template in this codebase. A shape is selected per video from
what the sources support, and never repeats the previous video's shape — the
direct countermeasure to YouTube's "mass-produced templates reused across
multiple videos with the same structure" disqualifier.
"""

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient
from contentforge.sourcing.fetch import Source

SHAPES = (
    "mechanism-first: open on the counter-intuitive part of how it works, then unwind it",
    "failure-first: open on what goes wrong when it is built badly, then show the fix",
    "history-first: open on the problem that existed before it, then how it was solved",
    "comparison: two approaches to the same problem, and why one won",
)

SYSTEM = """You write short factual explainer scripts for narration.

Rules, all mandatory:
- Every factual claim must be supported by the provided sources, and must carry an
  inline citation marker like [1] naming the source it came from.
- Never reproduce source wording. Rewrite everything in plain spoken English.
- No filler credentials. Never claim personal experience, study, or expertise.
- Write only the narration. No headings, no stage directions, no timestamps.
"""


def choose_shape(topic: str, previous: str | None = None) -> str:
    """Pick a narrative shape, deterministic per topic, never repeating `previous`."""
    index = sum(ord(character) for character in topic) % len(SHAPES)
    shape = SHAPES[index]
    if shape == previous:
        shape = SHAPES[(index + 1) % len(SHAPES)]
    return shape


def generate_script(client: LLMClient, topic: str, sources: list[Source], shape: str) -> str:
    if not sources:
        raise MissingDataError(
            f"no sources for {topic!r}; refusing to generate an ungrounded script"
        )
    catalogue = "\n\n".join(
        f"[{n}] {source.title}\nURL: {source.url}\n{source.text[:6000]}"
        for n, source in enumerate(sources, start=1)
    )
    user = (
        f"Topic: how does {topic} work\n"
        f"Narrative shape: {shape}\n\n"
        f"Sources:\n\n{catalogue}\n\n"
        "Write a 700-900 word narration script following the shape above."
    )
    return client.complete(SYSTEM, user)
