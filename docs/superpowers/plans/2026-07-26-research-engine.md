> **SUPERSEDED.** This plan was implemented and run against live data. It failed its gate:
> the ranking collapsed to an RPM lookup because `competitor_count` and `entrability` were
> bounded by our own sample size. See `2026-07-26-research-engine-v2.md`. Kept for the
> record — its Tasks 1-3 (provenance, quota, YouTube client) survive unchanged in v2.

# Research Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `pipeline research`, which emits a ranked niche report where every number traces to a real YouTube API response, inside the 10,000 units/day free quota.

**Architecture:** A quota-aware YouTube client feeds a discover→metrics→score chain. Every value carries a `Provenance` record, and a validator between stages rejects anything unprovenanced. All data types are frozen dataclasses — nothing mutates in place. Network transport is injected, so tests run against recorded fixtures and never touch a live API.

**Tech Stack:** Python 3.11+, `google-api-python-client`, `pytest`. No other runtime dependencies.

## Global Constraints

- **Provenance or nothing.** Every factual value carries `source_url`, `response_id`, `retrieved_at`. Unprovenanced values raise, never default.
- **Fail loudly, write nothing.** No stage emits partial or synthesised output when an input is missing. There is no fallback-to-hardcoded path anywhere in this codebase.
- **Immutable data.** All dataclasses are `frozen=True`. Functions return new objects; they never mutate arguments.
- **No live APIs in tests.** Transport is injected. CI never makes a network call.
- **Quota ceiling:** 10,000 units/day. `search.list`=100, `videos.list`=1, `channels.list`=1.
- **Zero budget.** No paid dependency may be introduced.
- **No AI attribution** in any commit message or document.

## File Structure

```
pyproject.toml                              packaging + pytest config
src/contentforge/__init__.py
src/contentforge/provenance.py              Provenance, Fact, validator          [Task 1]
src/contentforge/errors.py                  the exception hierarchy              [Task 1]
src/contentforge/providers/__init__.py
src/contentforge/providers/quota.py         QuotaLedger                          [Task 2]
src/contentforge/providers/youtube_api.py   YouTubeClient                        [Task 3]
src/contentforge/research/__init__.py
src/contentforge/research/rpm_table.py      sourced RPM lookup                   [Task 4]
src/contentforge/research/discover.py       niche → candidate channels           [Task 5]
src/contentforge/research/metrics.py        per-niche metrics                    [Task 6]
src/contentforge/research/score.py          ranking formula                      [Task 7]
src/contentforge/research/report.py         json + markdown output               [Task 8]
src/contentforge/cli.py                     `pipeline research`                  [Task 9]
data/rpm_table.csv                          checked-in, one source URL per row   [Task 4]
tests/fixtures/youtube/*.json               recorded API responses               [Task 3]
tests/...                                   mirrors src layout
```

---

### Task 1: Provenance core

**Files:**
- Create: `pyproject.toml`, `src/contentforge/__init__.py`, `src/contentforge/errors.py`, `src/contentforge/provenance.py`
- Test: `tests/test_provenance.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `Provenance(source_url: str, response_id: str, retrieved_at: datetime)`; `Fact(value: Any, provenance: Provenance)`; `require_provenance(obj: Any) -> None` raising `UnprovenancedError`; exceptions `ContentforgeError`, `UnprovenancedError`, `QuotaExceededError`, `MissingDataError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_provenance.py
from datetime import datetime, timezone
import pytest
from contentforge.provenance import Provenance, Fact, require_provenance
from contentforge.errors import UnprovenancedError

PROV = Provenance(
    source_url="https://www.googleapis.com/youtube/v3/channels?id=UC123",
    response_id="resp-abc",
    retrieved_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
)


def test_fact_carries_provenance():
    fact = Fact(value=1234, provenance=PROV)
    assert fact.value == 1234
    assert fact.provenance.response_id == "resp-abc"


def test_fact_is_immutable():
    fact = Fact(value=1, provenance=PROV)
    with pytest.raises(Exception):
        fact.value = 2


def test_provenance_rejects_blank_source_url():
    with pytest.raises(UnprovenancedError):
        Provenance(source_url="", response_id="r", retrieved_at=PROV.retrieved_at)


def test_provenance_rejects_naive_datetime():
    with pytest.raises(UnprovenancedError):
        Provenance(source_url="https://x", response_id="r", retrieved_at=datetime(2026, 7, 26))


def test_require_provenance_accepts_fact():
    require_provenance(Fact(value=1, provenance=PROV))


def test_require_provenance_rejects_bare_value():
    with pytest.raises(UnprovenancedError):
        require_provenance(1234)


def test_require_provenance_recurses_into_containers():
    require_provenance([Fact(value=1, provenance=PROV), Fact(value=2, provenance=PROV)])
    with pytest.raises(UnprovenancedError):
        require_provenance([Fact(value=1, provenance=PROV), 2])


def test_require_provenance_recurses_into_dict_values():
    with pytest.raises(UnprovenancedError):
        require_provenance({"subs": Fact(value=1, provenance=PROV), "views": 99})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_provenance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "contentforge"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["google-api-python-client>=2.0"]

[project.scripts]
pipeline = "contentforge.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# src/contentforge/errors.py
class ContentforgeError(Exception):
    """Base for every error this package raises."""


class UnprovenancedError(ContentforgeError):
    """A value reached a stage boundary without a source."""


class QuotaExceededError(ContentforgeError):
    """The requested call would exceed the daily API budget."""


class MissingDataError(ContentforgeError):
    """Required input is absent. Never substitute a default."""
```

```python
# src/contentforge/provenance.py
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contentforge.errors import UnprovenancedError


@dataclass(frozen=True)
class Provenance:
    source_url: str
    response_id: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.source_url:
            raise UnprovenancedError("source_url must not be empty")
        if not self.response_id:
            raise UnprovenancedError("response_id must not be empty")
        if self.retrieved_at.tzinfo is None:
            raise UnprovenancedError("retrieved_at must be timezone-aware")


@dataclass(frozen=True)
class Fact:
    value: Any
    provenance: Provenance


def require_provenance(obj: Any) -> None:
    """Raise UnprovenancedError unless every leaf value is a Fact."""
    if isinstance(obj, Fact):
        return
    if isinstance(obj, dict):
        for value in obj.values():
            require_provenance(value)
        return
    if isinstance(obj, (list, tuple, set)):
        for item in obj:
            require_provenance(item)
        return
    raise UnprovenancedError(f"value without provenance: {obj!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install -e . && pytest tests/test_provenance.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/contentforge/__init__.py src/contentforge/errors.py src/contentforge/provenance.py tests/test_provenance.py
git commit -m "feat: add provenance core and error hierarchy"
```

---

### Task 2: Quota ledger

**Files:**
- Create: `src/contentforge/providers/__init__.py`, `src/contentforge/providers/quota.py`
- Test: `tests/providers/test_quota.py`

**Interfaces:**
- Consumes: `QuotaExceededError` from `contentforge.errors`
- Produces: `UNIT_COSTS: dict[str, int]`; `QuotaLedger(daily_limit: int = 10000, spent: int = 0)` with `.charge(endpoint: str) -> QuotaLedger` (returns a NEW ledger), `.would_exceed(endpoint: str) -> bool`, `.remaining -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_quota.py
import pytest
from contentforge.providers.quota import QuotaLedger, UNIT_COSTS
from contentforge.errors import QuotaExceededError


def test_known_unit_costs():
    assert UNIT_COSTS["search.list"] == 100
    assert UNIT_COSTS["videos.list"] == 1
    assert UNIT_COSTS["channels.list"] == 1


def test_charge_returns_new_ledger_and_does_not_mutate():
    ledger = QuotaLedger()
    charged = ledger.charge("search.list")
    assert ledger.spent == 0, "original ledger must not mutate"
    assert charged.spent == 100
    assert charged is not ledger


def test_remaining_reflects_spend():
    ledger = QuotaLedger().charge("search.list").charge("videos.list")
    assert ledger.spent == 101
    assert ledger.remaining == 9899


def test_charge_raises_when_budget_would_be_exceeded():
    ledger = QuotaLedger(daily_limit=150).charge("search.list")
    with pytest.raises(QuotaExceededError):
        ledger.charge("search.list")


def test_would_exceed_predicts_without_charging():
    ledger = QuotaLedger(daily_limit=150).charge("search.list")
    assert ledger.would_exceed("search.list") is True
    assert ledger.would_exceed("videos.list") is False
    assert ledger.spent == 100, "would_exceed must not charge"


def test_unknown_endpoint_raises_rather_than_assuming_zero():
    with pytest.raises(KeyError):
        QuotaLedger().charge("mystery.endpoint")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_quota.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.providers'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/providers/quota.py
from dataclasses import dataclass, replace

from contentforge.errors import QuotaExceededError

UNIT_COSTS: dict[str, int] = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "videos.insert": 1600,
}


@dataclass(frozen=True)
class QuotaLedger:
    daily_limit: int = 10_000
    spent: int = 0

    @property
    def remaining(self) -> int:
        return self.daily_limit - self.spent

    def would_exceed(self, endpoint: str) -> bool:
        return self.spent + UNIT_COSTS[endpoint] > self.daily_limit

    def charge(self, endpoint: str) -> "QuotaLedger":
        cost = UNIT_COSTS[endpoint]
        if self.spent + cost > self.daily_limit:
            raise QuotaExceededError(
                f"{endpoint} costs {cost}; only {self.remaining} units remain"
            )
        return replace(self, spent=self.spent + cost)
```

Note: `UNIT_COSTS[endpoint]` raising `KeyError` on an unknown endpoint is deliberate — silently assuming zero cost would let an unbudgeted call slip past the ceiling.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/providers/test_quota.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/providers/ tests/providers/
git commit -m "feat: add immutable quota ledger"
```

---

### Task 3: YouTube client

**Files:**
- Create: `src/contentforge/providers/youtube_api.py`, `tests/fixtures/youtube/search_finance.json`, `tests/fixtures/youtube/channels_batch.json`
- Test: `tests/providers/test_youtube_api.py`

**Interfaces:**
- Consumes: `Provenance`, `Fact` (Task 1); `QuotaLedger` (Task 2)
- Produces: `ChannelRef(channel_id: str, title: str, provenance: Provenance)`; `ChannelStats(channel_id: str, subscribers: Fact, video_count: Fact, view_count: Fact, published_at: Fact)`; `YouTubeClient(api_key: str, transport: Callable[[str, dict], dict])` with `.search_channels(query, ledger, max_results=25) -> tuple[list[ChannelRef], QuotaLedger]` and `.get_channels(channel_ids, ledger) -> tuple[list[ChannelStats], QuotaLedger]`

The `transport` callable takes `(endpoint, params)` and returns the parsed JSON body. Production passes a thin `google-api-python-client` wrapper; tests pass a fixture reader.

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_youtube_api.py
import json
from pathlib import Path
import pytest
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.providers.quota import QuotaLedger
from contentforge.errors import MissingDataError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "youtube"


def fixture_transport(name):
    """Returns a transport that always replies with one recorded response."""
    body = json.loads((FIXTURES / name).read_text())

    def _transport(endpoint, params):
        return body

    return _transport


def test_search_channels_returns_refs_with_provenance():
    client = YouTubeClient(api_key="k", transport=fixture_transport("search_finance.json"))
    refs, ledger = client.search_channels("personal finance", QuotaLedger())
    assert len(refs) == 2
    assert refs[0].channel_id == "UC_finance_a"
    assert refs[0].provenance.source_url.startswith("https://www.googleapis.com/youtube/v3/search")
    assert refs[0].provenance.retrieved_at.tzinfo is not None


def test_search_charges_100_units():
    client = YouTubeClient(api_key="k", transport=fixture_transport("search_finance.json"))
    _, ledger = client.search_channels("personal finance", QuotaLedger())
    assert ledger.spent == 100


def test_get_channels_charges_one_unit_per_batch_not_per_id():
    client = YouTubeClient(api_key="k", transport=fixture_transport("channels_batch.json"))
    stats, ledger = client.get_channels(["UC_finance_a", "UC_finance_b"], QuotaLedger())
    assert ledger.spent == 1, "channels.list is billed per call, not per id"
    assert len(stats) == 2


def test_channel_stats_values_are_facts():
    client = YouTubeClient(api_key="k", transport=fixture_transport("channels_batch.json"))
    stats, _ = client.get_channels(["UC_finance_a"], QuotaLedger())
    assert stats[0].subscribers.value == 120000
    assert stats[0].subscribers.provenance.response_id == "chan-resp-1"


def test_missing_statistics_block_raises_rather_than_defaulting_to_zero():
    def broken_transport(endpoint, params):
        return {"etag": "chan-resp-1", "items": [{"id": "UC_x", "snippet": {"title": "X", "publishedAt": "2020-01-01T00:00:00Z"}}]}

    client = YouTubeClient(api_key="k", transport=broken_transport)
    with pytest.raises(MissingDataError):
        client.get_channels(["UC_x"], QuotaLedger())


def test_empty_search_results_raise_rather_than_returning_empty():
    def empty_transport(endpoint, params):
        return {"etag": "e", "items": []}

    client = YouTubeClient(api_key="k", transport=empty_transport)
    with pytest.raises(MissingDataError):
        client.search_channels("nonsense query", QuotaLedger())
```

Fixture files:

```json
// tests/fixtures/youtube/search_finance.json
{
  "etag": "search-resp-1",
  "items": [
    {"id": {"channelId": "UC_finance_a"}, "snippet": {"title": "Finance A"}},
    {"id": {"channelId": "UC_finance_b"}, "snippet": {"title": "Finance B"}}
  ]
}
```

```json
// tests/fixtures/youtube/channels_batch.json
{
  "etag": "chan-resp-1",
  "items": [
    {"id": "UC_finance_a", "snippet": {"title": "Finance A", "publishedAt": "2024-03-01T00:00:00Z"},
     "statistics": {"subscriberCount": "120000", "videoCount": "210", "viewCount": "18000000"}},
    {"id": "UC_finance_b", "snippet": {"title": "Finance B", "publishedAt": "2025-09-15T00:00:00Z"},
     "statistics": {"subscriberCount": "8000", "videoCount": "44", "viewCount": "900000"}}
  ]
}
```

Strip the `//` comment lines when creating the fixture files — JSON does not permit comments.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_youtube_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.providers.youtube_api'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/providers/youtube_api.py
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.providers.quota import QuotaLedger

API_ROOT = "https://www.googleapis.com/youtube/v3"
Transport = Callable[[str, dict], dict]


@dataclass(frozen=True)
class ChannelRef:
    channel_id: str
    title: str
    provenance: Provenance


@dataclass(frozen=True)
class ChannelStats:
    channel_id: str
    title: str
    subscribers: Fact
    video_count: Fact
    view_count: Fact
    published_at: Fact


def _provenance(endpoint: str, params: dict, body: dict) -> Provenance:
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    response_id = body.get("etag")
    if not response_id:
        raise MissingDataError(f"{endpoint} response carried no etag; cannot establish provenance")
    return Provenance(
        source_url=f"{API_ROOT}/{endpoint.split('.')[0]}?{query}",
        response_id=response_id,
        retrieved_at=datetime.now(timezone.utc),
    )


def _require(mapping: dict, key: str, context: str):
    if key not in mapping:
        raise MissingDataError(f"{context} missing required field {key!r}")
    return mapping[key]


class YouTubeClient:
    def __init__(self, api_key: str, transport: Transport) -> None:
        self._api_key = api_key
        self._transport = transport

    def search_channels(
        self, query: str, ledger: QuotaLedger, max_results: int = 25
    ) -> tuple[list[ChannelRef], QuotaLedger]:
        params = {"q": query, "type": "channel", "part": "snippet", "maxResults": max_results}
        charged = ledger.charge("search.list")
        body = self._transport("search.list", params)
        prov = _provenance("search.list", params, body)
        items = body.get("items") or []
        if not items:
            raise MissingDataError(f"search returned no channels for {query!r}")
        refs = [
            ChannelRef(
                channel_id=_require(_require(item, "id", "search item"), "channelId", "search id"),
                title=_require(_require(item, "snippet", "search item"), "title", "search snippet"),
                provenance=prov,
            )
            for item in items
        ]
        return refs, charged

    def get_channels(
        self, channel_ids: list[str], ledger: QuotaLedger
    ) -> tuple[list[ChannelStats], QuotaLedger]:
        params = {"id": ",".join(channel_ids), "part": "snippet,statistics"}
        charged = ledger.charge("channels.list")
        body = self._transport("channels.list", params)
        prov = _provenance("channels.list", params, body)
        items = body.get("items") or []
        if not items:
            raise MissingDataError(f"channels.list returned nothing for {channel_ids!r}")
        out = []
        for item in items:
            stats = _require(item, "statistics", f"channel {item.get('id')}")
            snippet = _require(item, "snippet", f"channel {item.get('id')}")
            out.append(
                ChannelStats(
                    channel_id=_require(item, "id", "channel item"),
                    title=_require(snippet, "title", "channel snippet"),
                    subscribers=Fact(int(_require(stats, "subscriberCount", "statistics")), prov),
                    video_count=Fact(int(_require(stats, "videoCount", "statistics")), prov),
                    view_count=Fact(int(_require(stats, "viewCount", "statistics")), prov),
                    published_at=Fact(
                        datetime.fromisoformat(
                            _require(snippet, "publishedAt", "snippet").replace("Z", "+00:00")
                        ),
                        prov,
                    ),
                )
            )
        return out, charged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/providers/test_youtube_api.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/providers/youtube_api.py tests/providers/test_youtube_api.py tests/fixtures/
git commit -m "feat: add quota-aware YouTube client with fixture transport"
```

---

### Task 4: RPM table

**Files:**
- Create: `data/rpm_table.csv`, `src/contentforge/research/__init__.py`, `src/contentforge/research/rpm_table.py`
- Test: `tests/research/test_rpm_table.py`

**Interfaces:**
- Consumes: `Provenance`, `Fact` (Task 1); `MissingDataError` (Task 1)
- Produces: `RpmRow(niche: str, geography: str, rpm_low: float, rpm_high: float, currency: str, provenance: Provenance)`; `load_rpm_table(path: Path) -> dict[tuple[str, str], RpmRow]`; `rpm_midpoint_usd(table, niche, geography) -> Fact`

Currency normalisation uses a fixed `INR_PER_USD` constant, documented as an assumption rather than fetched — an exchange-rate API is out of scope and the ranking is comparative, not absolute.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_rpm_table.py
from pathlib import Path
import pytest
from contentforge.research.rpm_table import load_rpm_table, rpm_midpoint_usd
from contentforge.errors import MissingDataError

TABLE = Path(__file__).parent.parent.parent / "data" / "rpm_table.csv"


def test_every_row_has_a_source_url_and_date():
    table = load_rpm_table(TABLE)
    assert table, "rpm table must not be empty"
    for row in table.values():
        assert row.provenance.source_url.startswith("http")
        assert row.provenance.retrieved_at.tzinfo is not None


def test_lookup_returns_midpoint_as_fact():
    table = load_rpm_table(TABLE)
    fact = rpm_midpoint_usd(table, "finance", "IN")
    assert fact.value > 0
    assert fact.provenance.source_url.startswith("http")


def test_missing_combination_raises_rather_than_defaulting():
    table = load_rpm_table(TABLE)
    with pytest.raises(MissingDataError):
        rpm_midpoint_usd(table, "underwater basket weaving", "IN")


def test_inr_rows_are_converted_to_usd():
    table = load_rpm_table(TABLE)
    india = rpm_midpoint_usd(table, "finance", "IN")
    usa = rpm_midpoint_usd(table, "finance", "US")
    assert usa.value > india.value, "US finance RPM must exceed India after conversion"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/test_rpm_table.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research'`

- [ ] **Step 3: Write minimal implementation**

```csv
# data/rpm_table.csv
niche,geography,rpm_low,rpm_high,currency,source_url,retrieved_at
finance,IN,80,250,INR,https://www.identitykit.in/blog/youtube-rpm-india-niche-2026,2026-07-26
tech,IN,60,180,INR,https://www.identitykit.in/blog/youtube-rpm-india-niche-2026,2026-07-26
education,IN,100,150,INR,https://www.identitykit.in/blog/youtube-rpm-india-niche-2026,2026-07-26
finance,US,10,25,USD,https://outlierkit.com/blog/youtube-rpm-finance-niche,2026-07-26
tech,US,8,20,USD,https://outlierkit.com/blog/youtube-rpm-finance-niche,2026-07-26
education,US,6,15,USD,https://outlierkit.com/blog/youtube-rpm-finance-niche,2026-07-26
```

Remove the `# data/rpm_table.csv` comment line when creating the file; the header row must be first.

```python
# src/contentforge/research/rpm_table.py
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance

# Assumption, not a live rate. The ranking is comparative, so a stale rate
# shifts all INR rows equally and does not reorder results.
INR_PER_USD = 88.0


@dataclass(frozen=True)
class RpmRow:
    niche: str
    geography: str
    rpm_low: float
    rpm_high: float
    currency: str
    provenance: Provenance


def load_rpm_table(path: Path) -> dict[tuple[str, str], RpmRow]:
    table: dict[tuple[str, str], RpmRow] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            prov = Provenance(
                source_url=record["source_url"],
                response_id=f"rpm_table:{record['niche']}:{record['geography']}",
                retrieved_at=datetime.fromisoformat(record["retrieved_at"]).replace(
                    tzinfo=timezone.utc
                ),
            )
            row = RpmRow(
                niche=record["niche"],
                geography=record["geography"],
                rpm_low=float(record["rpm_low"]),
                rpm_high=float(record["rpm_high"]),
                currency=record["currency"],
                provenance=prov,
            )
            table[(row.niche, row.geography)] = row
    return table


def rpm_midpoint_usd(
    table: dict[tuple[str, str], RpmRow], niche: str, geography: str
) -> Fact:
    row = table.get((niche, geography))
    if row is None:
        raise MissingDataError(
            f"no RPM row for ({niche!r}, {geography!r}); add a sourced row to data/rpm_table.csv"
        )
    midpoint = (row.rpm_low + row.rpm_high) / 2
    if row.currency == "INR":
        midpoint = midpoint / INR_PER_USD
    elif row.currency != "USD":
        raise MissingDataError(f"unsupported currency {row.currency!r}")
    return Fact(value=midpoint, provenance=row.provenance)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/research/test_rpm_table.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add data/rpm_table.csv src/contentforge/research/ tests/research/
git commit -m "feat: add sourced RPM lookup table"
```

---

### Task 5: Discover

**Files:**
- Create: `src/contentforge/research/discover.py`
- Test: `tests/research/test_discover.py`

**Interfaces:**
- Consumes: `YouTubeClient`, `ChannelRef` (Task 3); `QuotaLedger` (Task 2)
- Produces: `NicheCandidate(niche: str, queries: tuple[str, ...], channel_ids: tuple[str, ...], provenance: Provenance)`; `discover_niche(client, niche, queries, ledger) -> tuple[NicheCandidate, QuotaLedger]`

Deduplicates channel ids across queries so a channel ranking for three queries is counted once.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_discover.py
import pytest
from contentforge.research.discover import discover_niche
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.providers.quota import QuotaLedger
from contentforge.errors import QuotaExceededError

RESPONSES = {
    "index funds": {"etag": "e1", "items": [
        {"id": {"channelId": "UC_a"}, "snippet": {"title": "A"}},
        {"id": {"channelId": "UC_b"}, "snippet": {"title": "B"}}]},
    "etf investing": {"etag": "e2", "items": [
        {"id": {"channelId": "UC_b"}, "snippet": {"title": "B"}},
        {"id": {"channelId": "UC_c"}, "snippet": {"title": "C"}}]},
}


def routing_transport(endpoint, params):
    return RESPONSES[params["q"]]


def test_discover_dedupes_channels_across_queries():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    candidate, ledger = discover_niche(
        client, "finance", ["index funds", "etf investing"], QuotaLedger()
    )
    assert set(candidate.channel_ids) == {"UC_a", "UC_b", "UC_c"}
    assert candidate.niche == "finance"


def test_discover_charges_100_units_per_query():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    _, ledger = discover_niche(
        client, "finance", ["index funds", "etf investing"], QuotaLedger()
    )
    assert ledger.spent == 200


def test_discover_stops_cleanly_when_quota_runs_out():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    with pytest.raises(QuotaExceededError):
        discover_niche(
            client, "finance", ["index funds", "etf investing"], QuotaLedger(daily_limit=150)
        )


def test_empty_query_list_raises_rather_than_returning_provenanceless_candidate():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    with pytest.raises(MissingDataError):
        discover_niche(client, "finance", [], QuotaLedger())
```

Add `MissingDataError` to the imports at the top of this test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/test_discover.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.discover'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/discover.py
from dataclasses import dataclass

from contentforge.errors import MissingDataError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.provenance import Provenance


@dataclass(frozen=True)
class NicheCandidate:
    niche: str
    queries: tuple[str, ...]
    channel_ids: tuple[str, ...]
    provenance: Provenance


def discover_niche(
    client: YouTubeClient, niche: str, queries: list[str], ledger: QuotaLedger
) -> tuple[NicheCandidate, QuotaLedger]:
    if not queries:
        raise MissingDataError(f"no seed queries for niche {niche!r}")
    seen: list[str] = []
    current = ledger
    first_provenance: Provenance | None = None
    for query in queries:
        refs, current = client.search_channels(query, current)
        if first_provenance is None:
            first_provenance = refs[0].provenance
        for ref in refs:
            if ref.channel_id not in seen:
                seen.append(ref.channel_id)
    candidate = NicheCandidate(
        niche=niche,
        queries=tuple(queries),
        channel_ids=tuple(seen),
        provenance=first_provenance,
    )
    return candidate, current
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/research/test_discover.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/discover.py tests/research/test_discover.py
git commit -m "feat: add niche discovery with cross-query dedupe"
```

---

### Task 6: Metrics

**Files:**
- Create: `src/contentforge/research/metrics.py`
- Test: `tests/research/test_metrics.py`

**Interfaces:**
- Consumes: `ChannelStats` (Task 3); `NicheCandidate` (Task 5); `Fact`, `Provenance` (Task 1)
- Produces: `NicheMetrics(niche: str, competitor_count: Fact, median_views_per_day: Fact, entrability: Fact)`; `compute_metrics(candidate, channel_stats, now) -> NicheMetrics`

Definitions, fixed here so scoring is reproducible:
- **competitor_count** — channels in the candidate set with ≥10,000 subscribers.
- **median_views_per_day** — median of `view_count / channel_age_days` across the candidate set.
- **entrability** — fraction of the candidate set younger than 18 months. High means newcomers are still gaining traction.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_metrics.py
from datetime import datetime, timezone
import pytest
from contentforge.research.metrics import compute_metrics
from contentforge.research.discover import NicheCandidate
from contentforge.providers.youtube_api import ChannelStats
from contentforge.provenance import Fact, Provenance
from contentforge.errors import MissingDataError

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def stats(cid, subs, views, published):
    return ChannelStats(
        channel_id=cid, title=cid,
        subscribers=Fact(subs, PROV), video_count=Fact(10, PROV),
        view_count=Fact(views, PROV), published_at=Fact(published, PROV),
    )


CANDIDATE = NicheCandidate(
    niche="finance", queries=("q",), channel_ids=("UC_a", "UC_b"), provenance=PROV
)


def test_competitor_count_uses_10k_subscriber_threshold():
    rows = [
        stats("UC_a", 120000, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc)),
        stats("UC_b", 500, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc)),
    ]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.competitor_count.value == 1


def test_median_views_per_day_is_hand_computable():
    # UC_a: 3650 views over 365 days = 10.0/day
    # UC_b: 7300 views over 365 days = 20.0/day
    # median of [10.0, 20.0] = 15.0
    rows = [
        stats("UC_a", 20000, 3650, datetime(2025, 7, 26, tzinfo=timezone.utc)),
        stats("UC_b", 20000, 7300, datetime(2025, 7, 26, tzinfo=timezone.utc)),
    ]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.median_views_per_day.value == pytest.approx(15.0)


def test_entrability_is_fraction_younger_than_18_months():
    rows = [
        stats("UC_a", 20000, 1000, datetime(2026, 3, 1, tzinfo=timezone.utc)),   # young
        stats("UC_b", 20000, 1000, datetime(2019, 1, 1, tzinfo=timezone.utc)),   # old
    ]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.entrability.value == pytest.approx(0.5)


def test_empty_channel_set_raises_rather_than_scoring_zero():
    with pytest.raises(MissingDataError):
        compute_metrics(CANDIDATE, [], NOW)


def test_channel_published_today_does_not_divide_by_zero():
    rows = [stats("UC_a", 20000, 100, NOW)]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.median_views_per_day.value == pytest.approx(100.0)


def test_metrics_carry_provenance():
    rows = [stats("UC_a", 20000, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc))]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.competitor_count.provenance.response_id == "r"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.metrics'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/metrics.py
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.research.discover import NicheCandidate

SUBSCRIBER_THRESHOLD = 10_000
YOUNG_CHANNEL_DAYS = 548  # 18 months


@dataclass(frozen=True)
class NicheMetrics:
    niche: str
    competitor_count: Fact
    median_views_per_day: Fact
    entrability: Fact


def compute_metrics(
    candidate: NicheCandidate, channel_stats: list, now: datetime
) -> NicheMetrics:
    if not channel_stats:
        raise MissingDataError(
            f"no channel statistics for niche {candidate.niche!r}; refusing to score an empty set"
        )
    prov = channel_stats[0].subscribers.provenance

    competitors = sum(
        1 for row in channel_stats if row.subscribers.value >= SUBSCRIBER_THRESHOLD
    )

    per_day = []
    young = 0
    for row in channel_stats:
        age_days = max((now - row.published_at.value).days, 1)
        per_day.append(row.view_count.value / age_days)
        if age_days <= YOUNG_CHANNEL_DAYS:
            young += 1

    return NicheMetrics(
        niche=candidate.niche,
        competitor_count=Fact(competitors, prov),
        median_views_per_day=Fact(median(per_day), prov),
        entrability=Fact(young / len(channel_stats), prov),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/research/test_metrics.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/metrics.py tests/research/test_metrics.py
git commit -m "feat: add niche metrics with fixed thresholds"
```

---

### Task 7: Score

**Files:**
- Create: `src/contentforge/research/score.py`
- Test: `tests/research/test_score.py`

**Interfaces:**
- Consumes: `NicheMetrics` (Task 6); `rpm_midpoint_usd` (Task 4); `Fact` (Task 1)
- Produces: `NicheScore(niche: str, geography: str, score: float, rpm_usd: Fact, metrics: NicheMetrics)`; `score_niche(metrics, rpm_fact, geography) -> NicheScore`; `rank(scores) -> list[NicheScore]`

Formula, fixed so results are reproducible and hand-checkable:

```
score = rpm_usd × log1p(median_views_per_day) × (0.5 + entrability) / (1 + log1p(competitor_count))
```

RPM sets the ceiling; view velocity rewards demand; entrability rewards niches newcomers still break into; competitor count damps saturation. The `0.5 +` floor stops a mature niche scoring zero outright.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_score.py
import math
from datetime import datetime, timezone
import pytest
from contentforge.research.score import score_niche, rank
from contentforge.research.metrics import NicheMetrics
from contentforge.provenance import Fact, Provenance

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def metrics(niche, competitors, vpd, entrability):
    return NicheMetrics(
        niche=niche,
        competitor_count=Fact(competitors, PROV),
        median_views_per_day=Fact(vpd, PROV),
        entrability=Fact(entrability, PROV),
    )


def test_score_matches_hand_computed_value():
    m = metrics("finance", competitors=4, vpd=100.0, entrability=0.5)
    result = score_niche(m, Fact(2.0, PROV), "US")
    expected = 2.0 * math.log1p(100.0) * (0.5 + 0.5) / (1 + math.log1p(4))
    assert result.score == pytest.approx(expected)


def test_higher_rpm_scores_higher_all_else_equal():
    m = metrics("finance", 4, 100.0, 0.5)
    low = score_niche(m, Fact(1.0, PROV), "IN")
    high = score_niche(m, Fact(4.0, PROV), "US")
    assert high.score > low.score


def test_more_competitors_scores_lower_all_else_equal():
    few = score_niche(metrics("a", 2, 100.0, 0.5), Fact(2.0, PROV), "US")
    many = score_niche(metrics("a", 200, 100.0, 0.5), Fact(2.0, PROV), "US")
    assert few.score > many.score


def test_zero_competitors_does_not_divide_by_zero():
    result = score_niche(metrics("a", 0, 100.0, 1.0), Fact(2.0, PROV), "US")
    assert result.score > 0


def test_rank_orders_descending():
    a = score_niche(metrics("a", 100, 10.0, 0.1), Fact(1.0, PROV), "IN")
    b = score_niche(metrics("b", 2, 500.0, 0.9), Fact(5.0, PROV), "US")
    assert [s.niche for s in rank([a, b])] == ["b", "a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/test_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.score'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/score.py
import math
from dataclasses import dataclass

from contentforge.provenance import Fact
from contentforge.research.metrics import NicheMetrics


@dataclass(frozen=True)
class NicheScore:
    niche: str
    geography: str
    score: float
    rpm_usd: Fact
    metrics: NicheMetrics


def score_niche(metrics: NicheMetrics, rpm_usd: Fact, geography: str) -> NicheScore:
    demand = math.log1p(metrics.median_views_per_day.value)
    openness = 0.5 + metrics.entrability.value
    saturation = 1 + math.log1p(metrics.competitor_count.value)
    return NicheScore(
        niche=metrics.niche,
        geography=geography,
        score=rpm_usd.value * demand * openness / saturation,
        rpm_usd=rpm_usd,
        metrics=metrics,
    )


def rank(scores: list[NicheScore]) -> list[NicheScore]:
    return sorted(scores, key=lambda s: s.score, reverse=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/research/test_score.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/score.py tests/research/test_score.py
git commit -m "feat: add niche scoring formula"
```

---

### Task 8: Report writer

**Files:**
- Create: `src/contentforge/research/report.py`
- Test: `tests/research/test_report.py`

**Interfaces:**
- Consumes: `NicheScore` (Task 7); `require_provenance` (Task 1)
- Produces: `write_report(scores, out_dir, generated_at) -> tuple[Path, Path]` returning `(json_path, md_path)`

Every number in the markdown carries its source URL inline. The JSON is the machine-readable form consumed by later plans.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_report.py
import json
from datetime import datetime, timezone
import pytest
from contentforge.research.report import write_report
from contentforge.research.score import score_niche
from contentforge.research.metrics import NicheMetrics
from contentforge.provenance import Fact, Provenance

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://src.example/rpm", response_id="r", retrieved_at=NOW)


def a_score(niche="finance"):
    m = NicheMetrics(
        niche=niche,
        competitor_count=Fact(4, PROV),
        median_views_per_day=Fact(100.0, PROV),
        entrability=Fact(0.5, PROV),
    )
    return score_niche(m, Fact(2.0, PROV), "US")


def test_writes_both_files(tmp_path):
    json_path, md_path = write_report([a_score()], tmp_path, NOW)
    assert json_path.exists() and md_path.exists()


def test_json_records_every_source_url(tmp_path):
    json_path, _ = write_report([a_score()], tmp_path, NOW)
    payload = json.loads(json_path.read_text())
    entry = payload["niches"][0]
    assert entry["rpm_usd"]["source_url"] == "https://src.example/rpm"
    assert entry["metrics"]["competitor_count"]["source_url"] == "https://src.example/rpm"


def test_markdown_includes_source_links(tmp_path):
    _, md_path = write_report([a_score()], tmp_path, NOW)
    assert "https://src.example/rpm" in md_path.read_text()


def test_empty_score_list_raises_rather_than_writing_empty_report(tmp_path):
    with pytest.raises(Exception):
        write_report([], tmp_path, NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/research/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.report'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/report.py
import json
from datetime import datetime
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.research.score import NicheScore


def _fact_json(fact: Fact) -> dict:
    return {
        "value": fact.value,
        "source_url": fact.provenance.source_url,
        "response_id": fact.provenance.response_id,
        "retrieved_at": fact.provenance.retrieved_at.isoformat(),
    }


def write_report(
    scores: list[NicheScore], out_dir: Path, generated_at: datetime
) -> tuple[Path, Path]:
    if not scores:
        raise MissingDataError("refusing to write an empty research report")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": generated_at.isoformat(),
        "niches": [
            {
                "niche": s.niche,
                "geography": s.geography,
                "score": s.score,
                "rpm_usd": _fact_json(s.rpm_usd),
                "metrics": {
                    "competitor_count": _fact_json(s.metrics.competitor_count),
                    "median_views_per_day": _fact_json(s.metrics.median_views_per_day),
                    "entrability": _fact_json(s.metrics.entrability),
                },
            }
            for s in scores
        ],
    }
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(payload, indent=2))

    lines = [f"# Niche research — {generated_at.date().isoformat()}", ""]
    for rank_index, s in enumerate(scores, start=1):
        lines += [
            f"## {rank_index}. {s.niche} ({s.geography}) — score {s.score:.2f}",
            "",
            f"- RPM (USD): {s.rpm_usd.value:.2f} — [source]({s.rpm_usd.provenance.source_url})",
            f"- Competitors ≥10k subs: {s.metrics.competitor_count.value} "
            f"— [source]({s.metrics.competitor_count.provenance.source_url})",
            f"- Median views/day: {s.metrics.median_views_per_day.value:.1f} "
            f"— [source]({s.metrics.median_views_per_day.provenance.source_url})",
            f"- Entrability: {s.metrics.entrability.value:.2f} "
            f"— [source]({s.metrics.entrability.provenance.source_url})",
            "",
        ]
    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(lines))
    return json_path, md_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/research/test_report.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/report.py tests/research/test_report.py
git commit -m "feat: add research report writer with inline sources"
```

---

### Task 9: CLI and end-to-end smoke test

**Files:**
- Create: `src/contentforge/cli.py`, `src/contentforge/config.py`, `.env.example`
- Test: `tests/test_cli_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8
- Produces: `main(argv: list[str] | None = None) -> int`; `run_research(client, niches, geography, table_path, out_dir, now, ledger) -> tuple[list[NicheScore], QuotaLedger]`

`run_research` returns the final ledger as well as the ranked scores, so callers and tests can assert on actual quota consumed rather than trusting it.

Niche seed queries live in `config.py` as a module constant so Plan 3 can move them to a file without changing the call signature.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_end_to_end.py
import json
from datetime import datetime, timezone
from pathlib import Path
from contentforge.cli import run_research
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.providers.quota import QuotaLedger

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
TABLE = Path(__file__).parent.parent / "data" / "rpm_table.csv"

SEARCH = {"etag": "s1", "items": [
    {"id": {"channelId": "UC_a"}, "snippet": {"title": "A"}},
    {"id": {"channelId": "UC_b"}, "snippet": {"title": "B"}}]}
CHANNELS = {"etag": "c1", "items": [
    {"id": "UC_a", "snippet": {"title": "A", "publishedAt": "2025-01-01T00:00:00Z"},
     "statistics": {"subscriberCount": "50000", "videoCount": "80", "viewCount": "5000000"}},
    {"id": "UC_b", "snippet": {"title": "B", "publishedAt": "2026-01-01T00:00:00Z"},
     "statistics": {"subscriberCount": "3000", "videoCount": "20", "viewCount": "200000"}}]}


def transport(endpoint, params):
    return SEARCH if endpoint == "search.list" else CHANNELS


def test_run_research_produces_ranked_provenanced_report(tmp_path):
    client = YouTubeClient(api_key="k", transport=transport)
    scores, _ledger = run_research(
        client=client,
        niches={"finance": ["index funds"], "tech": ["ai tools"]},
        geography="US",
        table_path=TABLE,
        out_dir=tmp_path,
        now=NOW,
        ledger=QuotaLedger(),
    )
    assert len(scores) == 2
    assert scores[0].score >= scores[1].score, "results must be ranked"

    payload = json.loads((tmp_path / "report.json").read_text())
    for entry in payload["niches"]:
        assert entry["rpm_usd"]["source_url"].startswith("http")
        assert entry["metrics"]["competitor_count"]["source_url"].startswith("http")


def test_run_research_reports_actual_quota_spent(tmp_path):
    client = YouTubeClient(api_key="k", transport=transport)
    _scores, ledger = run_research(
        client=client, niches={"finance": ["index funds"]}, geography="US",
        table_path=TABLE, out_dir=tmp_path, now=NOW, ledger=QuotaLedger(),
    )
    # 1 search.list (100) + 1 channels.list (1) = 101 for a single one-query niche
    assert ledger.spent == 101


def test_full_config_run_stays_within_daily_quota(tmp_path):
    from contentforge.config import NICHE_QUERIES

    client = YouTubeClient(api_key="k", transport=transport)
    _scores, ledger = run_research(
        client=client, niches=NICHE_QUERIES, geography="US",
        table_path=TABLE, out_dir=tmp_path, now=NOW, ledger=QuotaLedger(),
    )
    assert ledger.spent < 10_000, f"default config burns {ledger.spent} units/run"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_end_to_end.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/config.py
NICHE_QUERIES: dict[str, list[str]] = {
    "finance": ["index funds", "personal finance tips", "etf investing"],
    "tech": ["ai tools", "coding tutorial", "software review"],
    "education": ["study techniques", "online courses", "skill building"],
}

DEFAULT_GEOGRAPHY = "US"
```

```python
# src/contentforge/cli.py
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from contentforge.config import DEFAULT_GEOGRAPHY, NICHE_QUERIES
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.discover import discover_niche
from contentforge.research.metrics import compute_metrics
from contentforge.research.report import write_report
from contentforge.research.rpm_table import load_rpm_table, rpm_midpoint_usd
from contentforge.research.score import rank, score_niche


def run_research(client, niches, geography, table_path, out_dir, now, ledger):
    table = load_rpm_table(table_path)
    current = ledger
    scores = []
    for niche, queries in niches.items():
        candidate, current = discover_niche(client, niche, queries, current)
        stats, current = client.get_channels(list(candidate.channel_ids), current)
        metrics = compute_metrics(candidate, stats, now)
        rpm = rpm_midpoint_usd(table, niche, geography)
        scores.append(score_niche(metrics, rpm, geography))
    ranked = rank(scores)
    write_report(ranked, out_dir, now)
    return ranked, current


def _live_transport(api_key: str):
    from googleapiclient.discovery import build

    service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def _transport(endpoint, params):
        resource, method = endpoint.split(".")
        return getattr(getattr(service, resource)(), method)(**params).execute()

    return _transport


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research", help="rank niches from live YouTube data")
    research.add_argument("--geography", default=DEFAULT_GEOGRAPHY)
    research.add_argument("--out", type=Path, default=Path("data/research"))
    args = parser.parse_args(argv)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("YOUTUBE_API_KEY is not set")

    now = datetime.now(timezone.utc)
    out_dir = args.out / now.date().isoformat()
    client = YouTubeClient(api_key=api_key, transport=_live_transport(api_key))
    ranked, ledger = run_research(
        client=client, niches=NICHE_QUERIES, geography=args.geography,
        table_path=Path("data/rpm_table.csv"), out_dir=out_dir,
        now=now, ledger=QuotaLedger(),
    )
    print(f"Wrote {len(ranked)} ranked niches to {out_dir} ({ledger.spent} quota units used)")
    return 0
```

```bash
# .env.example
YOUTUBE_API_KEY=your_key_here
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: all tests pass (42 total across Tasks 1–9)

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/cli.py src/contentforge/config.py .env.example tests/test_cli_end_to_end.py
git commit -m "feat: add research CLI and end-to-end smoke test"
```

---

## Definition of done

`pipeline research` runs against a real `YOUTUBE_API_KEY` and writes `data/research/<date>/report.{json,md}` where every number carries a source URL, and the run consumes well under 10,000 quota units. Three niches at three queries each costs 3 × (3×100 + 1) = 903 units, leaving headroom for reruns.

The gate for starting Plan 2 is human: read `report.md` and decide whether it is believable enough to pick a niche from. If it is not, the fix belongs in this plan, not downstream.
