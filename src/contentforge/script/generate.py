"""Script generation grounded in fetched sources.

The narration voice is modelled on the long-form business-explainer channel this
project studies (C-055): second person, one confident reframe up front, then the
mechanism unwound in plain spoken English. That is a *style* — second person,
metaphor, reveal structure — and styles are not copyrightable. What must stay
ours is the wording, the structure of each specific video, and the identity
around it (our palette, our title format, our accent), so a video is inspired by
the approach without being a copy of any particular one. YouTube's
inauthentic-content policy disqualifies "mass-produced templates reused across
multiple videos with the same structure", which is why the shape rotates and is
never the reference's fixed "The Economics of Owning a [X]" frame.

Citations stay in the written script - they are how provenance is checked
(validate.py) and how the description credits sources - but they are stripped
before narration (voice/speak.py) and before captions, because the reference
voice speaks none and neither should ours.
"""

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient
from contentforge.sourcing.fetch import Source

#: Reveal structures, not the reference's single fixed frame. One is chosen per
#: video and never repeats the previous, so no two videos share a skeleton.
SHAPES = (
    "reframe-first: open by naming what the thing REALLY is, against what it looks "
    "like ('it is not a gym, it is a subscription business with dumbbells in it'), "
    "then show how every number follows from that",
    "follow-the-money: trace one unit of the customer's money from the moment it "
    "enters to where it actually ends up, and where it quietly leaks on the way",
    "hidden-cost: open on the cost nobody counts, then rebuild the real economics "
    "around it",
    "who-actually-wins: separate the party that appears to make the money from the "
    "party that actually does, and show why",
)

#: About 142 words a minute (the measured narration pace), so this lands a video
#: in the reference's 20-37 minute band without one runaway LLM call. The lower
#: bound alone is ~17 minutes.
TARGET_WORDS_LOW = 2500
TARGET_WORDS_HIGH = 3200

SYSTEM = """You write long-form business-explainer narration, spoken by one
confident, faintly amused narrator talking directly to the viewer as "you".

Voice, all mandatory:
- Second person. Talk to the viewer. "You walk in, you see the rows of machines,
  and you assume..." Never "I", never "we", never "in this video".
- Open on a reframe: state what the subject REALLY is, against what it looks
  like, in the first two sentences. Earn the rest of the video from that.
- One idea per sentence, plain spoken English, the rhythm of someone explaining
  something they find quietly funny. Short sentences. Concrete numbers.
- Use a running metaphor where it clarifies, never as decoration.
- Reveal, do not list. Each section turns over one more rock.

Rules, all mandatory:
- Every factual claim must trace to a provided source and carry an inline marker
  like [1] naming it. Markers are stripped before narration; write them anyway.
- Never reproduce source wording. Rewrite everything.
- No fabricated authority. Never "I have studied", "in my experience", "experts
  agree". The narrator explains; it never credentials itself.
- Write only the spoken words. No headings, no stage directions, no timestamps,
  no "welcome back", no "don't forget to subscribe".
"""


def choose_shape(topic: str, previous: str | None = None) -> str:
    """Pick a narrative shape, deterministic per topic, never repeating `previous`."""
    index = sum(ord(character) for character in topic) % len(SHAPES)
    shape = SHAPES[index]
    if shape == previous:
        shape = SHAPES[(index + 1) % len(SHAPES)]
    return shape


def generate_script(client: LLMClient, topic: str, sources: list[Source],
                    shape: str, system: str = SYSTEM,
                    target_words: tuple[int, int] = (TARGET_WORDS_LOW, TARGET_WORDS_HIGH)
                    ) -> str:
    if not sources:
        raise MissingDataError(
            f"no sources for {topic!r}; refusing to generate an ungrounded script"
        )
    catalogue = "\n\n".join(
        f"[{n}] {source.title}\nURL: {source.url}\n{source.text[:8000]}"
        for n, source in enumerate(sources, start=1)
    )
    user = (
        f"Subject: {topic}\n"
        f"Structure for this video: {shape}\n\n"
        f"Sources:\n\n{catalogue}\n\n"
        f"Write {target_words[0]}-{target_words[1]} words of narration in the "
        "voice and structure above. Open on the reframe in the first two "
        "sentences. Keep it grounded in the sources throughout."
    )
    return client.complete(system, user, max_tokens=8000)
