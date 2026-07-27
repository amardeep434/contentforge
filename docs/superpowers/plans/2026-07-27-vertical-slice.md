# Plan 2 — Vertical Slice to a Published Video

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish three "how does X work" explainers, then read retention before making a fourth.

**Architecture:** Filesystem stages, as in the spec. `topic → sources → script → voice → visuals → render → published`. Every factual claim in a script resolves to a fetched source; the validator refuses anything that does not.

**Tech Stack:** Python 3.11+, `edge-tts` (free), `ffmpeg`, `google-api-python-client`. LLM via any OpenAI-compatible endpoint.

## Niche

**Tech explainers, "how does X work".** Chosen because it is the only candidate pairing an
unlimited episode template with a high-RPM audience (~$20 US). Two templates:
`how does X work` and `why is my X not working`. Neither runs out of instances.

## Global Constraints

- **Provenance or nothing.** Every claim carries a source URL and retrieval timestamp.
- **Transform, never relay.** Verbatim overlap with any source is capped; this is the
  policy gate, not a style preference.
- **No script template.** Structure is chosen per video from what the sources support.
- **Fail loudly, write nothing.** No stage emits partial output.
- **Zero paid dependencies.**
- **No AI attribution** in commits or documents.

## File Structure

```
src/contentforge/providers/llm.py        OpenAI-compatible client            [Task 1]
src/contentforge/sourcing/fetch.py       retrieve + store primary sources    [Task 2]
src/contentforge/script/generate.py      script from sources                 [Task 3]
src/contentforge/script/validate.py      THE POLICY GATE                     [Task 4]
src/contentforge/voice/speak.py          edge-tts + word timings             [Task 5]
src/contentforge/visuals/gather.py       Openverse images + licences         [Task 6]
src/contentforge/render/compose.py       ffmpeg                              [Task 7]
src/contentforge/publish/youtube.py      OAuth upload                        [Task 8]
```

---

### Task 1: LLM client

**Files:** Create `src/contentforge/providers/llm.py`, `tests/providers/test_llm.py`

**Interfaces:**
- Produces: `LLMClient(base_url, api_key, model, transport)`; `.complete(system, user, max_tokens) -> str`

Transport is injected, same as `YouTubeClient` — tests never make network calls.

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_llm.py
import pytest
from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient


def transport_returning(text):
    def _transport(url, payload, headers):
        return {"choices": [{"message": {"content": text}}]}
    return _transport


def test_complete_returns_message_content():
    client = LLMClient("http://x/v1", "", "m", transport_returning("hello"))
    assert client.complete("sys", "user") == "hello"


def test_sends_system_and_user_messages():
    seen = {}

    def _transport(url, payload, headers):
        seen.update(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    LLMClient("http://x/v1", "", "m", _transport).complete("SYS", "USER")
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]
    assert seen["messages"][0]["content"] == "SYS"
    assert seen["model"] == "m"


def test_empty_response_raises_rather_than_returning_blank():
    client = LLMClient("http://x/v1", "", "m", lambda u, p, h: {"choices": []})
    with pytest.raises(MissingDataError):
        client.complete("s", "u")


def test_api_key_goes_in_the_header_not_the_payload():
    seen = {}

    def _transport(url, payload, headers):
        seen["headers"] = headers
        seen["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    LLMClient("http://x/v1", "secret", "m", _transport).complete("s", "u")
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert "secret" not in str(seen["payload"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/providers/test_llm.py -q`
Expected: `ModuleNotFoundError: contentforge.providers.llm`

- [ ] **Step 3: Implement**

```python
# src/contentforge/providers/llm.py
"""OpenAI-compatible chat client.

base_url is a config value, not an integration. Points at omniroute today;
changing provider is one environment variable.
"""

import json
import urllib.request
from typing import Callable

from contentforge.errors import MissingDataError

Transport = Callable[[str, dict, dict], dict]


def http_transport(url: str, payload: dict, headers: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


class LLMClient:
    def __init__(
        self, base_url: str, api_key: str, model: str, transport: Transport = http_transport
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._transport = transport

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = self._transport(self._url, payload, headers)
        choices = body.get("choices") or []
        if not choices:
            raise MissingDataError(f"LLM returned no choices: {str(body)[:200]}")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise MissingDataError("LLM returned an empty message")
        return content
```

- [ ] **Step 4: Run tests** — `.venv/bin/pytest tests/providers/test_llm.py -q`, expect 4 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add OpenAI-compatible LLM client"`

---

### Task 2: Sourcing

**Files:** Create `src/contentforge/sourcing/fetch.py`, `tests/sourcing/test_fetch.py`

**Interfaces:**
- Produces: `Source(url, title, text, retrieved_at)`; `fetch_source(url, transport) -> Source`; `save_sources(sources, out_dir) -> Path`; `load_sources(dir) -> list[Source]`

Sources are fetched and stored in full. The script stage reads only from disk, so a script
can always be re-checked against exactly what was available when it was written.

- [ ] **Step 1: Write the failing test**

```python
# tests/sourcing/test_fetch.py
import json
from datetime import datetime, timezone
import pytest
from contentforge.errors import MissingDataError
from contentforge.sourcing.fetch import Source, fetch_source, load_sources, save_sources

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


def test_fetch_captures_text_and_provenance():
    def transport(url):
        return "<html><title>How Air Fryers Work</title><body>Hot air circulates.</body></html>"

    source = fetch_source("https://example.org/airfryer", transport, NOW)
    assert "Hot air circulates" in source.text
    assert source.url == "https://example.org/airfryer"
    assert source.retrieved_at == NOW


def test_empty_page_raises_rather_than_storing_nothing():
    with pytest.raises(MissingDataError):
        fetch_source("https://example.org/x", lambda u: "", NOW)


def test_sources_round_trip_through_disk(tmp_path):
    sources = [Source("https://a", "A", "text a", NOW), Source("https://b", "B", "text b", NOW)]
    save_sources(sources, tmp_path)
    loaded = load_sources(tmp_path)
    assert [s.url for s in loaded] == ["https://a", "https://b"]
    assert loaded[0].text == "text a"


def test_loading_an_empty_directory_raises():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as empty:
        with pytest.raises(MissingDataError):
            load_sources(Path(empty))
```

- [ ] **Step 2: Run to verify it fails** — expected `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/contentforge/sourcing/fetch.py
"""Retrieve and store primary sources.

Stored in full so a script can be re-checked later against exactly what was
available when it was written. A source that cannot be fetched is an error,
never an empty entry - a script grounded in nothing is the failure mode this
whole design exists to prevent.
"""

import html
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "contentforge/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _strip(markup: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", _TAGS.sub(" ", markup))).strip()


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    text: str
    retrieved_at: datetime


def fetch_source(url: str, transport: Callable[[str], str] = http_get, now=None) -> Source:
    now = now or datetime.now(timezone.utc)
    markup = transport(url)
    text = _strip(markup)
    if not text:
        raise MissingDataError(f"{url} yielded no text")
    match = _TITLE.search(markup)
    return Source(
        url=url,
        title=_strip(match.group(1)) if match else url,
        text=text,
        retrieved_at=now,
    )


def save_sources(sources: list[Source], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sources.json"
    path.write_text(
        json.dumps(
            [
                {
                    "url": s.url,
                    "title": s.title,
                    "text": s.text,
                    "retrieved_at": s.retrieved_at.isoformat(),
                }
                for s in sources
            ],
            indent=2,
        )
    )
    return path


def load_sources(directory: Path) -> list[Source]:
    path = directory / "sources.json"
    if not path.exists():
        raise MissingDataError(f"no sources at {path}")
    records = json.loads(path.read_text())
    if not records:
        raise MissingDataError(f"{path} is empty")
    return [
        Source(r["url"], r["title"], r["text"], datetime.fromisoformat(r["retrieved_at"]))
        for r in records
    ]
```

- [ ] **Step 4: Run tests** — expect 4 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add source fetching and storage"`

---

### Task 3: Script generation

**Files:** Create `src/contentforge/script/generate.py`, `tests/script/test_generate.py`

**Interfaces:**
- Consumes: `LLMClient` (Task 1), `Source` (Task 2)
- Produces: `SHAPES: tuple[str, ...]`; `choose_shape(topic, previous) -> str`; `generate_script(client, topic, sources, shape) -> str`

`choose_shape` rotates deliberately: no two consecutive videos share a narrative shape.
That is the countermeasure to "mass-produced templates reused with the same structure".

- [ ] **Step 1: Write the failing test**

```python
# tests/script/test_generate.py
from datetime import datetime, timezone
import pytest
from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient
from contentforge.script.generate import SHAPES, choose_shape, generate_script
from contentforge.sourcing.fetch import Source

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
SOURCES = [Source("https://a", "A", "Hot air circulates rapidly.", NOW)]


def test_shape_never_repeats_the_previous_one():
    for previous in SHAPES:
        assert choose_shape("air fryers", previous) != previous


def test_shape_is_deterministic_for_a_topic():
    assert choose_shape("air fryers", None) == choose_shape("air fryers", None)


def test_prompt_carries_the_source_text_and_urls():
    seen = {}

    def transport(url, payload, headers):
        seen["user"] = payload["messages"][1]["content"]
        return {"choices": [{"message": {"content": "script [1]"}}]}

    client = LLMClient("http://x/v1", "", "m", transport)
    generate_script(client, "air fryers", SOURCES, SHAPES[0])
    assert "Hot air circulates rapidly." in seen["user"]
    assert "https://a" in seen["user"]


def test_no_sources_raises_before_calling_the_model():
    calls = []

    def transport(url, payload, headers):
        calls.append(1)
        return {"choices": [{"message": {"content": "x"}}]}

    client = LLMClient("http://x/v1", "", "m", transport)
    with pytest.raises(MissingDataError):
        generate_script(client, "air fryers", [], SHAPES[0])
    assert calls == [], "must not spend a model call on an ungrounded script"
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```python
# src/contentforge/script/generate.py
"""Script generation grounded in fetched sources.

There is no script template in this codebase. A shape is selected per video from
what the sources support, and never repeats the previous video's shape - the
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
    "comparison: two approaches to the same problem, why one won",
)

SYSTEM = """You write short factual explainer scripts for narration.

Rules, all mandatory:
- Every factual claim must be supported by the provided sources, and must carry an
  inline citation marker like [1] naming the source it came from.
- Never reproduce source wording. Rewrite everything in plain spoken English.
- No filler credentials. Never claim personal experience, study, or expertise.
- Write only the narration. No headings, no stage directions, no timestamps.
"""


def choose_shape(topic: str, previous: str | None) -> str:
    """Pick a narrative shape, deterministic per topic, never repeating `previous`."""
    index = sum(ord(character) for character in topic) % len(SHAPES)
    shape = SHAPES[index]
    if shape == previous:
        shape = SHAPES[(index + 1) % len(SHAPES)]
    return shape


def generate_script(
    client: LLMClient, topic: str, sources: list[Source], shape: str
) -> str:
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
```

- [ ] **Step 4: Run tests** — expect 4 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add per-video shape selection and grounded script generation"`

---

### Task 4: The validator

**Files:** Create `src/contentforge/script/validate.py`, `tests/script/test_validate.py`

**Interfaces:**
- Produces: `MAX_OVERLAP_WORDS = 12`; `ValidationError`; `check_citations(script, sources)`; `check_verbatim(script, sources)`; `validate_script(script, sources)`

This module is the reason the project can publish at low human effort. It gets adversarial
tests and is treated as security code.

- [ ] **Step 1: Write the failing test**

```python
# tests/script/test_validate.py
from datetime import datetime, timezone
import pytest
from contentforge.script.validate import (
    MAX_OVERLAP_WORDS, ValidationError, check_citations, check_verbatim, validate_script,
)
from contentforge.sourcing.fetch import Source

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
SOURCES = [Source("https://a", "A", "Hot air is circulated by a fan around the food basket.", NOW)]


def test_script_with_citations_passes():
    validate_script("An air fryer moves heated air quickly [1].", SOURCES)


def test_script_with_no_citations_at_all_is_rejected():
    with pytest.raises(ValidationError, match="citation"):
        check_citations("An air fryer moves heated air quickly.", SOURCES)


def test_citation_pointing_at_a_nonexistent_source_is_rejected():
    with pytest.raises(ValidationError, match="source 7"):
        check_citations("Air moves fast [7].", SOURCES)


def test_verbatim_lift_longer_than_the_cap_is_rejected():
    lifted = "Hot air is circulated by a fan around the food basket [1]."
    with pytest.raises(ValidationError, match="verbatim"):
        check_verbatim(lifted, SOURCES)


def test_short_shared_phrasing_is_allowed():
    check_verbatim("Hot air is circulated [1] which cooks the food evenly.", SOURCES)


def test_paraphrase_passes():
    check_verbatim("A fan pushes heated air around the basket [1].", SOURCES)


def test_case_and_punctuation_do_not_defeat_the_check():
    lifted = "HOT AIR IS CIRCULATED, BY A FAN, AROUND THE FOOD BASKET! [1]"
    with pytest.raises(ValidationError, match="verbatim"):
        check_verbatim(lifted, SOURCES)


def test_fabricated_credential_claims_are_rejected():
    with pytest.raises(ValidationError, match="credential"):
        validate_script("I have spent years studying this topic [1].", SOURCES)


def test_the_cap_is_what_the_test_says_it_is():
    assert MAX_OVERLAP_WORDS == 12
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```python
# src/contentforge/script/validate.py
"""The policy gate.

YouTube's inauthentic-content policy disqualifies "readings of other materials you
did not create" and "mass-produced templates". Shape rotation handles the second.
This module handles the first, plus the fabricated-authority filler that LLMs
produce by default ("I've spent years studying this").

Treated as security code: adversarial tests, and a hard failure rather than a warning.
"""

import re

from contentforge.errors import ContentforgeError
from contentforge.sourcing.fetch import Source

# Longest run of consecutive words a script may share with any source. Twelve is a
# starting value - long enough for unavoidable technical phrasing, short enough that
# a lifted sentence trips it. Tune against real scripts, never upward without cause.
MAX_OVERLAP_WORDS = 12

_CITATION = re.compile(r"\[(\d+)\]")
_WORD = re.compile(r"[a-z0-9]+")

# Unearned authority. The model has no experience to cite.
_CREDENTIAL_CLAIMS = (
    "i have spent", "i've spent", "i have studied", "i've studied",
    "in my experience", "i have analysed", "i have analyzed",
    "i've analysed", "i've analyzed", "years of research",
    "i have interviewed", "i've interviewed",
)


class ValidationError(ContentforgeError):
    """The script violates a publication rule."""


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def check_citations(script: str, sources: list[Source]) -> None:
    markers = [int(n) for n in _CITATION.findall(script)]
    if not markers:
        raise ValidationError("script contains no citation markers")
    for marker in markers:
        if not 1 <= marker <= len(sources):
            raise ValidationError(
                f"script cites source {marker}, but only {len(sources)} were provided"
            )


def check_verbatim(script: str, sources: list[Source]) -> None:
    script_words = _words(script)
    for index, source in enumerate(sources, start=1):
        source_words = _words(source.text)
        window = MAX_OVERLAP_WORDS
        if len(script_words) < window or len(source_words) < window:
            continue
        source_runs = {
            tuple(source_words[i : i + window])
            for i in range(len(source_words) - window + 1)
        }
        for i in range(len(script_words) - window + 1):
            run = tuple(script_words[i : i + window])
            if run in source_runs:
                raise ValidationError(
                    f"script reproduces {window} consecutive words verbatim from "
                    f"source {index} ({source.url}): {' '.join(run)!r}"
                )


def check_credentials(script: str) -> None:
    lowered = script.lower()
    for phrase in _CREDENTIAL_CLAIMS:
        if phrase in lowered:
            raise ValidationError(f"script makes a fabricated credential claim: {phrase!r}")


def validate_script(script: str, sources: list[Source]) -> None:
    check_citations(script, sources)
    check_verbatim(script, sources)
    check_credentials(script)
```

- [ ] **Step 4: Run tests** — expect 9 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add the script policy gate"`

---

### Task 5: Voice

**Files:** Create `src/contentforge/voice/speak.py`, `tests/voice/test_speak.py`

**Interfaces:**
- Produces: `strip_citations(script) -> str`; `synthesise(text, out_path, voice) -> Path`

Citation markers are for the validator and the description, not the narrator. `[1]` must
never be spoken.

Add `edge-tts` to `pyproject.toml` dependencies.

- [ ] **Step 1: Write the failing test**

```python
# tests/voice/test_speak.py
from contentforge.voice.speak import strip_citations


def test_citation_markers_are_removed_before_narration():
    assert strip_citations("Air moves fast [1] and cooks food [2].") == (
        "Air moves fast and cooks food."
    )


def test_spacing_is_left_clean():
    assert "  " not in strip_citations("A [1] B [22] C.")


def test_text_without_markers_is_unchanged():
    assert strip_citations("Air moves fast.") == "Air moves fast."
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```python
# src/contentforge/voice/speak.py
"""Narration via edge-tts.

Free, no key, no quota. Citation markers are stripped before synthesis: they exist
for the validator and the video description, and a narrator reading "bracket one"
is the fastest way to sound machine-made.
"""

import asyncio
import re
from pathlib import Path

DEFAULT_VOICE = "en-US-AndrewNeural"
_CITATION = re.compile(r"\s*\[\d+\]")


def strip_citations(script: str) -> str:
    return re.sub(r"\s{2,}", " ", _CITATION.sub("", script)).strip()


def synthesise(text: str, out_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    """Render narration to mp3. Returns the path written."""
    import edge_tts

    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        communicate = edge_tts.Communicate(strip_citations(text), voice)
        await communicate.save(str(out_path))

    asyncio.run(_run())
    return out_path
```

- [ ] **Step 4: Run tests** — expect 3 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add edge-tts narration"`

---

### Task 6: Visuals

**Files:** Create `src/contentforge/visuals/gather.py`, `tests/visuals/test_gather.py`

**Interfaces:**
- Produces: `Asset(url, title, licence, creator, source_page)`; `search_openverse(query, transport, limit) -> list[Asset]`; `write_attribution(assets, out_dir) -> Path`

Openverse indexes openly-licensed media. Licence and creator are captured per asset and
written to an attribution file — CC-BY requires credit, and an unattributed video is a
takedown waiting to happen.

- [ ] **Step 1: Write the failing test**

```python
# tests/visuals/test_gather.py
import pytest
from contentforge.errors import MissingDataError
from contentforge.visuals.gather import search_openverse, write_attribution

BODY = {"results": [
    {"url": "https://img/1.jpg", "title": "Fan", "license": "by",
     "creator": "Ada", "foreign_landing_url": "https://page/1"},
    {"url": "https://img/2.jpg", "title": "Basket", "license": "cc0",
     "creator": "Bo", "foreign_landing_url": "https://page/2"},
]}


def test_assets_capture_licence_and_creator():
    assets = search_openverse("air fryer", lambda u: BODY, limit=5)
    assert assets[0].licence == "by"
    assert assets[0].creator == "Ada"


def test_no_results_raises_rather_than_returning_empty():
    with pytest.raises(MissingDataError):
        search_openverse("nonsense", lambda u: {"results": []}, limit=5)


def test_attribution_file_credits_every_asset(tmp_path):
    assets = search_openverse("air fryer", lambda u: BODY, limit=5)
    path = write_attribution(assets, tmp_path)
    text = path.read_text()
    assert "Ada" in text and "Bo" in text
    assert "https://page/1" in text
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```python
# src/contentforge/visuals/gather.py
"""Openly-licensed imagery from Openverse.

Free, no key. Licence and creator are captured per asset and written to an
attribution file: CC-BY requires credit, and an unattributed video is a takedown
waiting to happen.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

API = "https://api.openverse.org/v1/images/"


def http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "contentforge/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class Asset:
    url: str
    title: str
    licence: str
    creator: str
    source_page: str


def search_openverse(
    query: str, transport: Callable[[str], dict] = http_get_json, limit: int = 12
) -> list[Asset]:
    url = f"{API}?{urllib.parse.urlencode({'q': query, 'page_size': limit})}"
    results = (transport(url) or {}).get("results") or []
    if not results:
        raise MissingDataError(f"Openverse returned no images for {query!r}")
    return [
        Asset(
            url=r.get("url", ""),
            title=r.get("title", ""),
            licence=r.get("license", ""),
            creator=r.get("creator", "") or "unknown",
            source_page=r.get("foreign_landing_url", ""),
        )
        for r in results
    ]


def write_attribution(assets: list[Asset], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "attribution.md"
    lines = ["# Image credits", ""]
    for asset in assets:
        lines.append(
            f"- \"{asset.title}\" by {asset.creator}, licensed {asset.licence.upper()} "
            f"— {asset.source_page}"
        )
    path.write_text("\n".join(lines))
    return path
```

- [ ] **Step 4: Run tests** — expect 3 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add Openverse asset gathering with attribution"`

---

### Task 7: Render

**Files:** Create `src/contentforge/render/compose.py`, `tests/render/test_compose.py`

**Interfaces:**
- Produces: `ffmpeg_command(images, audio, out_path, width, height) -> list[str]`; `render(images, audio, out_path) -> Path`

The command builder is pure and unit-tested; `render` only executes it. That keeps the
whole thing testable without invoking ffmpeg in CI.

- [ ] **Step 1: Write the failing test**

```python
# tests/render/test_compose.py
from pathlib import Path
import pytest
from contentforge.errors import MissingDataError
from contentforge.render.compose import ffmpeg_command


def test_command_includes_every_image_and_the_audio():
    cmd = ffmpeg_command([Path("a.jpg"), Path("b.jpg")], Path("v.mp3"), Path("out.mp4"))
    joined = " ".join(cmd)
    assert "a.jpg" in joined and "b.jpg" in joined and "v.mp3" in joined


def test_output_is_1080p_by_default():
    cmd = ffmpeg_command([Path("a.jpg")], Path("v.mp3"), Path("out.mp4"))
    assert "1920:1080" in " ".join(cmd)


def test_shortest_stops_at_the_narration_end():
    assert "-shortest" in ffmpeg_command([Path("a.jpg")], Path("v.mp3"), Path("o.mp4"))


def test_no_images_raises():
    with pytest.raises(MissingDataError):
        ffmpeg_command([], Path("v.mp3"), Path("out.mp4"))
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```python
# src/contentforge/render/compose.py
"""ffmpeg composition: a slideshow under narration.

The command builder is pure so it can be unit-tested without running ffmpeg. Deliberately
plain - a Ken Burns pan or captions would be the first upgrade, once retention data says
whether the visuals matter at all.

ponytail: still slideshow, add motion/captions when retention shows visuals are the drop-off cause.
"""

import subprocess
from pathlib import Path

from contentforge.errors import MissingDataError


def ffmpeg_command(
    images: list[Path], audio: Path, out_path: Path, width: int = 1920, height: int = 1080
) -> list[str]:
    if not images:
        raise MissingDataError("cannot render a video with no images")

    command = ["ffmpeg", "-y"]
    for image in images:
        command += ["-loop", "1", "-t", "8", "-i", str(image)]
    command += ["-i", str(audio)]

    scale = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    filters = "".join(f"[{n}:v]{scale}[v{n}];" for n in range(len(images)))
    concat = "".join(f"[v{n}]" for n in range(len(images)))
    filters += f"{concat}concat=n={len(images)}:v=1:a=0[v]"

    command += [
        "-filter_complex", filters,
        "-map", "[v]", "-map", f"{len(images)}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out_path),
    ]
    return command


def render(images: list[Path], audio: Path, out_path: Path) -> Path:
    """Render to a temp file and move on success, so a crash leaves no half-video."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp = out_path.with_suffix(".partial.mp4")
    result = subprocess.run(
        ffmpeg_command(images, audio, temp), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise MissingDataError(f"ffmpeg failed: {result.stderr[-500:]}")
    temp.replace(out_path)
    return out_path
```

- [ ] **Step 4: Run tests** — expect 4 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add ffmpeg slideshow render"`

---

### Task 8: Publish

**Files:** Create `src/contentforge/publish/youtube.py`, `tests/publish/test_youtube.py`

**Interfaces:**
- Produces: `build_metadata(title, script, sources, assets) -> dict`; `upload(video_path, metadata, service) -> str`

Upload costs **1,600 quota units** — six per day maximum. Charge the ledger.

Description is built from citations and attribution, so credit is automatic rather than remembered.

- [ ] **Step 1: Write the failing test**

```python
# tests/publish/test_youtube.py
from datetime import datetime, timezone
from contentforge.publish.youtube import build_metadata
from contentforge.sourcing.fetch import Source
from contentforge.visuals.gather import Asset

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
SOURCES = [Source("https://a", "A Title", "text", NOW)]
ASSETS = [Asset("https://img/1", "Fan", "by", "Ada", "https://page/1")]


def test_description_lists_every_source_url():
    meta = build_metadata("How Air Fryers Work", "script [1]", SOURCES, ASSETS)
    assert "https://a" in meta["snippet"]["description"]


def test_description_carries_image_attribution():
    meta = build_metadata("t", "s [1]", SOURCES, ASSETS)
    assert "Ada" in meta["snippet"]["description"]


def test_not_marked_made_for_kids():
    """Made for Kids disables personalized ads and memberships - a ~10x RPM
    decision that must never default silently."""
    meta = build_metadata("t", "s [1]", SOURCES, ASSETS)
    assert meta["status"]["selfDeclaredMadeForKids"] is False


def test_starts_private_so_nothing_publishes_unreviewed():
    meta = build_metadata("t", "s [1]", SOURCES, ASSETS)
    assert meta["status"]["privacyStatus"] == "private"
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

```python
# src/contentforge/publish/youtube.py
"""YouTube upload.

videos.insert costs 1,600 quota units - six uploads per day at the free tier.

Uploads start **private**. Nothing reaches an audience without a human opening it
first, which is the last gate before the policy risk becomes real.
"""

from pathlib import Path

from contentforge.sourcing.fetch import Source
from contentforge.visuals.gather import Asset

CATEGORY_SCIENCE_TECH = "28"


def build_metadata(
    title: str, script: str, sources: list[Source], assets: list[Asset]
) -> dict:
    lines = [
        "Sources:",
        *[f"[{n}] {s.title} — {s.url}" for n, s in enumerate(sources, start=1)],
        "",
        "Image credits:",
        *[
            f"\"{a.title}\" by {a.creator}, {a.licence.upper()} — {a.source_page}"
            for a in assets
        ],
    ]
    return {
        "snippet": {
            "title": title[:100],
            "description": "\n".join(lines)[:5000],
            "categoryId": CATEGORY_SCIENCE_TECH,
        },
        "status": {
            # Private until a human reviews it. The one gate that cannot be automated.
            "privacyStatus": "private",
            # Made for Kids disables personalized ads and memberships - roughly a 10x
            # RPM decision. Never let it default.
            "selfDeclaredMadeForKids": False,
        },
    }


def upload(video_path: Path, metadata: dict, service) -> str:
    """Upload and return the video id. `service` is an authorised YouTube client."""
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = service.videos().insert(
        part="snippet,status", body=metadata, media_body=media
    )
    response = request.execute()
    return response["id"]
```

- [ ] **Step 4: Run tests** — expect 4 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: add YouTube upload with sourced descriptions"`

---

## Definition of done

Three videos published private, each with a script whose every claim resolves to a fetched
source, no verbatim lifts, a different narrative shape, and a description crediting sources
and image creators.

**Then stop and read retention.** Audience retention, traffic source and impressions
click-through are in YouTube Studio for your own videos. That is the variable no research
could supply and the reason this plan is three videos rather than thirty.

Decide video four from that data, not from this plan.

## Deliberately not built

n8n, batching, scheduling, a review UI, thumbnail generation, Shorts cuts, motion graphics,
multi-platform posting. Each is an upgrade to a pipeline that has not yet proven it can
hold an audience for thirty seconds.
