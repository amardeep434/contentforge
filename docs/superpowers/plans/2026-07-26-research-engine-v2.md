> **SUPERSEDED — implemented, run against live data, failed its gate.** Breakout rate
> came out at 0.38-0.71 and median lift at 4.8-9.9 across all fifteen niches, and the
> ranking reverted to RPM order. Root cause: `views / days_since_publish` is confounded
> by view front-loading, so recent videos always score higher velocity regardless of
> real performance. See `docs/findings/2026-07-26-research-engine-negative-result.md`.
> Tasks 1 and 4 (video fetching, niche table) remain in use; the trajectory and scoring
> tasks are dead code pending a fix that the API may not permit.

# Research Engine (revision 2 — trajectory) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace state-based niche metrics with trajectory analysis — detect which channels broke out, when, and what changed at the inflection — across a much wider sample.

**Architecture:** Revision 1's provenance core, quota ledger and YouTube client are kept unchanged. `rpm_table.py`, `metrics.py`, `score.py` and `report.py` are replaced. New: `trajectory.py` (velocity + inflection detection) and `changes.py` (within-channel pre/post diff).

**Tech Stack:** Python 3.11+, `google-api-python-client`, `pytest`. No new dependencies.

## Why this revision exists

Revision 1 was built, run against live data, and failed its gate. It ranked finance first — the answer anyone would guess. Root cause: `competitor_count` and `entrability` were bounded by our own sample size. Search returns incumbents for every query, so those metrics were near-identical across niches (39/38/30 competitors, 0.19–0.23 entrability) and the score collapsed to an RPM lookup.

## Global Constraints

- **Provenance or nothing.** Every factual value carries `source_url`, `response_id`, `retrieved_at`.
- **Fail loudly, write nothing.** No fallback-to-hardcoded path anywhere.
- **Immutable data.** All dataclasses `frozen=True`.
- **No live APIs in tests.** Transport injected; CI makes no network call.
- **Velocity, never raw views.** All comparisons use views-per-day-since-publish. Raw counts make every old video look successful.
- **Quota:** `search.list`=100, everything else=1. `channels.list`/`videos.list` cap at **50 ids** per call.
- **No AI attribution** in any commit message or document.

## File Structure

```
KEPT UNCHANGED from revision 1:
  src/contentforge/provenance.py
  src/contentforge/errors.py
  src/contentforge/providers/quota.py

EXTENDED:
  src/contentforge/providers/youtube_api.py     + uploads playlist, video fetch   [Task 1]

NEW:
  src/contentforge/research/trajectory.py       velocity + inflection             [Task 2]
  src/contentforge/research/changes.py          within-channel pre/post diff      [Task 3]
  src/contentforge/research/niches.py           niche table w/ restrictions       [Task 4]
  data/niches.csv                               12-15 hand-sourced rows           [Task 4]

REPLACED:
  src/contentforge/research/score.py            trajectory-based ranking          [Task 5]
  src/contentforge/research/report.py           etag citations + raw storage      [Task 6]
  src/contentforge/cli.py                       wider sampling loop               [Task 7]

DELETED:
  src/contentforge/research/rpm_table.py        superseded by niches.py           [Task 4]
  src/contentforge/research/metrics.py          superseded by trajectory.py       [Task 5]
  data/rpm_table.csv                            superseded by niches.csv          [Task 4]
```

---

### Task 1: Video history fetching

**Files:**
- Modify: `src/contentforge/providers/youtube_api.py`
- Test: `tests/providers/test_youtube_api.py` (append)

**Interfaces:**
- Consumes: `Fact`, `Provenance`, `QuotaLedger`, `_require`, `_provenance`, `MAX_IDS_PER_CHANNELS_CALL`
- Produces: `VideoRecord(video_id, channel_id, title, published_at, view_count, duration_seconds, provenance)`; `YouTubeClient.get_uploads_playlists(channel_ids, ledger) -> tuple[dict[str, str], QuotaLedger]`; `YouTubeClient.get_playlist_video_ids(playlist_id, ledger, max_videos=50) -> tuple[list[str], QuotaLedger]`; `YouTubeClient.get_videos(video_ids, ledger) -> tuple[list[VideoRecord], QuotaLedger]`; `parse_iso8601_duration(text: str) -> int`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/providers/test_youtube_api.py
from contentforge.providers.youtube_api import VideoRecord, parse_iso8601_duration


def test_parse_iso8601_duration_handles_all_components():
    assert parse_iso8601_duration("PT5M30S") == 330
    assert parse_iso8601_duration("PT1M21S") == 81
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT2H") == 7200


def test_parse_iso8601_duration_rejects_garbage():
    with pytest.raises(MissingDataError):
        parse_iso8601_duration("banana")


def test_get_uploads_playlists_maps_channel_to_playlist():
    def transport(endpoint, params):
        return {
            "etag": "cd-1",
            "items": [
                {"id": "UC_a", "contentDetails": {"relatedPlaylists": {"uploads": "UU_a"}}},
                {"id": "UC_b", "contentDetails": {"relatedPlaylists": {"uploads": "UU_b"}}},
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    mapping, ledger = client.get_uploads_playlists(["UC_a", "UC_b"], QuotaLedger())
    assert mapping == {"UC_a": "UU_a", "UC_b": "UU_b"}
    assert ledger.spent == 1


def test_get_uploads_playlists_batches_in_fifties():
    calls = []

    def transport(endpoint, params):
        ids = params["id"].split(",")
        calls.append(len(ids))
        return {
            "etag": "cd",
            "items": [
                {"id": cid, "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid}}}
                for cid in ids
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    mapping, ledger = client.get_uploads_playlists([f"UC_{n}" for n in range(120)], QuotaLedger())
    assert calls == [50, 50, 20]
    assert len(mapping) == 120
    assert ledger.spent == 3


def test_get_playlist_video_ids_returns_ids():
    def transport(endpoint, params):
        return {
            "etag": "pl-1",
            "items": [{"contentDetails": {"videoId": f"v{n}"}} for n in range(47)],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    ids, ledger = client.get_playlist_video_ids("UU_a", QuotaLedger())
    assert len(ids) == 47
    assert ids[0] == "v0"
    assert ledger.spent == 1


def test_get_videos_returns_records_with_velocity_inputs():
    def transport(endpoint, params):
        return {
            "etag": "vid-1",
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "channelId": "UC_a",
                        "title": "How index funds work",
                        "publishedAt": "2025-01-01T00:00:00Z",
                    },
                    "statistics": {"viewCount": "5000"},
                    "contentDetails": {"duration": "PT8M12S"},
                }
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    videos, ledger = client.get_videos(["v1"], QuotaLedger())
    assert len(videos) == 1
    assert videos[0].view_count.value == 5000
    assert videos[0].duration_seconds.value == 492
    assert videos[0].title == "How index funds work"
    assert videos[0].published_at.value.tzinfo is not None
    assert ledger.spent == 1


def test_get_videos_tolerates_missing_view_count_as_zero_not_error():
    """Brand-new videos legitimately report no viewCount. That is a real zero,
    not missing data, so it must not raise."""

    def transport(endpoint, params):
        return {
            "etag": "vid-2",
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "channelId": "UC_a",
                        "title": "t",
                        "publishedAt": "2026-07-26T00:00:00Z",
                    },
                    "statistics": {},
                    "contentDetails": {"duration": "PT30S"},
                }
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    videos, _ = client.get_videos(["v1"], QuotaLedger())
    assert videos[0].view_count.value == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/providers/test_youtube_api.py -q`
Expected: FAIL — `ImportError: cannot import name 'VideoRecord'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/contentforge/providers/youtube_api.py

import re

_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def parse_iso8601_duration(text: str) -> int:
    """YouTube returns durations as ISO 8601 (PT5M30S). Returns whole seconds."""
    match = _DURATION.match(text or "")
    if not match:
        raise MissingDataError(f"unparseable duration {text!r}")
    parts = {key: int(value or 0) for key, value in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


@dataclass(frozen=True)
class VideoRecord:
    video_id: str
    channel_id: str
    title: str
    published_at: Fact
    view_count: Fact
    duration_seconds: Fact
    provenance: Provenance


# methods on YouTubeClient:

    def get_uploads_playlists(
        self, channel_ids: list[str], ledger: QuotaLedger
    ) -> tuple[dict[str, str], QuotaLedger]:
        if not channel_ids:
            raise MissingDataError("get_uploads_playlists called with no ids")
        current = ledger
        mapping: dict[str, str] = {}
        for start in range(0, len(channel_ids), MAX_IDS_PER_CHANNELS_CALL):
            batch = channel_ids[start : start + MAX_IDS_PER_CHANNELS_CALL]
            params = {"id": ",".join(batch), "part": "contentDetails"}
            current = current.charge("channels.list")
            body = self._transport("channels.list", params)
            for item in body.get("items") or []:
                details = _require(item, "contentDetails", "channel")
                related = _require(details, "relatedPlaylists", "contentDetails")
                mapping[_require(item, "id", "channel")] = _require(
                    related, "uploads", "relatedPlaylists"
                )
        if not mapping:
            raise MissingDataError(f"no uploads playlists for {channel_ids!r}")
        return mapping, current

    def get_playlist_video_ids(
        self, playlist_id: str, ledger: QuotaLedger, max_videos: int = 50
    ) -> tuple[list[str], QuotaLedger]:
        params = {
            "playlistId": playlist_id,
            "part": "contentDetails",
            "maxResults": min(max_videos, 50),
        }
        charged = ledger.charge("playlistItems.list")
        body = self._transport("playlistItems.list", params)
        items = body.get("items") or []
        ids = [
            _require(_require(item, "contentDetails", "playlist item"), "videoId", "contentDetails")
            for item in items
        ]
        return ids, charged

    def get_videos(
        self, video_ids: list[str], ledger: QuotaLedger
    ) -> tuple[list[VideoRecord], QuotaLedger]:
        if not video_ids:
            raise MissingDataError("get_videos called with no ids")
        current = ledger
        records: list[VideoRecord] = []
        for start in range(0, len(video_ids), MAX_IDS_PER_CHANNELS_CALL):
            batch = video_ids[start : start + MAX_IDS_PER_CHANNELS_CALL]
            params = {"id": ",".join(batch), "part": "snippet,statistics,contentDetails"}
            current = current.charge("videos.list")
            body = self._transport("videos.list", params)
            prov = _provenance("videos.list", params, body)
            for item in body.get("items") or []:
                snippet = _require(item, "snippet", "video")
                details = _require(item, "contentDetails", "video")
                # statistics.viewCount is absent on brand-new videos. That is a
                # genuine zero, not missing data, so it does not raise.
                stats = item.get("statistics") or {}
                published = _require(snippet, "publishedAt", "video snippet")
                records.append(
                    VideoRecord(
                        video_id=_require(item, "id", "video"),
                        channel_id=_require(snippet, "channelId", "video snippet"),
                        title=_require(snippet, "title", "video snippet"),
                        published_at=Fact(
                            datetime.fromisoformat(published.replace("Z", "+00:00")), prov
                        ),
                        view_count=Fact(int(stats.get("viewCount", 0)), prov),
                        duration_seconds=Fact(
                            parse_iso8601_duration(_require(details, "duration", "contentDetails")),
                            prov,
                        ),
                        provenance=prov,
                    )
                )
        return records, current
```

Also add `"playlistItems.list": 1` to `UNIT_COSTS` in `src/contentforge/providers/quota.py`, and a test asserting it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/providers -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/providers/ tests/providers/
git commit -m "feat: add video history fetching for trajectory analysis"
```

---

### Task 2: Trajectory and inflection detection

**Files:**
- Create: `src/contentforge/research/trajectory.py`
- Test: `tests/research/test_trajectory.py`

**Interfaces:**
- Consumes: `VideoRecord` (Task 1); `Fact`; `MissingDataError`
- Produces: `VideoPoint(video_id, published_at, velocity, duration_seconds, title)`; `Inflection(index, published_at, before_median, after_median, lift)`; `ChannelTrajectory(channel_id, points, inflection)`; `velocity(view_count, published_at, now) -> float`; `build_trajectory(channel_id, videos, now) -> ChannelTrajectory`; `MIN_SIDE_VIDEOS = 5`; `MIN_LIFT = 3.0`

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_trajectory.py
from datetime import datetime, timedelta, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.youtube_api import VideoRecord
from contentforge.provenance import Fact, Provenance
from contentforge.research.trajectory import (
    MIN_LIFT,
    build_trajectory,
    velocity,
)

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def video(vid, days_ago, views, duration=600, title="t"):
    published = NOW - timedelta(days=days_ago)
    return VideoRecord(
        video_id=vid,
        channel_id="UC_a",
        title=title,
        published_at=Fact(published, PROV),
        view_count=Fact(views, PROV),
        duration_seconds=Fact(duration, PROV),
        provenance=PROV,
    )


def test_velocity_is_views_per_day():
    published = NOW - timedelta(days=100)
    assert velocity(1000, published, NOW) == pytest.approx(10.0)


def test_velocity_clamps_age_to_one_day_minimum():
    """A video published today must not divide by zero."""
    assert velocity(50, NOW, NOW) == pytest.approx(50.0)


def test_velocity_treats_future_dates_as_one_day_old():
    future = NOW + timedelta(days=5)
    assert velocity(50, future, NOW) == pytest.approx(50.0)


def test_trajectory_orders_points_oldest_first():
    videos = [video("v2", 10, 100), video("v1", 200, 100)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert [p.video_id for p in traj.points] == ["v1", "v2"]


def test_detects_inflection_when_velocity_jumps():
    # 6 old videos at ~1 view/day, then 6 recent at ~100 views/day
    videos = [video(f"old{n}", 400 - n, 400 - n) for n in range(6)]
    videos += [video(f"new{n}", 50 - n, (50 - n) * 100) for n in range(6)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is not None
    assert traj.inflection.lift >= MIN_LIFT
    assert traj.inflection.after_median > traj.inflection.before_median


def test_no_inflection_on_a_flat_channel():
    videos = [video(f"v{n}", 400 - n * 20, (400 - n * 20) * 10) for n in range(12)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is None, "steady channel must not report a breakout"


def test_no_inflection_when_too_few_videos_either_side():
    # 12 videos but the jump is at position 2, leaving fewer than MIN_SIDE before it
    videos = [video(f"v{n}", 400 - n * 20, 10) for n in range(2)]
    videos += [video(f"w{n}", 300 - n * 20, 100000) for n in range(10)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is None


def test_declining_channel_reports_no_inflection():
    # high early velocity, collapse later - a real pattern, must not read as breakout
    videos = [video(f"old{n}", 700 - n * 10, (700 - n * 10) * 50) for n in range(6)]
    videos += [video(f"new{n}", 60 - n * 5, 40) for n in range(6)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is None


def test_too_few_videos_raises():
    with pytest.raises(MissingDataError):
        build_trajectory("UC_a", [video("v1", 10, 10)], NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/research/test_trajectory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.trajectory'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/trajectory.py
"""Per-channel view trajectories and breakout detection.

The API exposes no historical channel data, so the climb is reconstructed from
per-video observations. Every comparison uses views-per-day-since-publish:
raw view counts are confounded by age, and comparing them makes every old
video look successful.
"""

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from contentforge.errors import MissingDataError

MIN_SIDE_VIDEOS = 5
MIN_LIFT = 3.0


@dataclass(frozen=True)
class VideoPoint:
    video_id: str
    published_at: datetime
    velocity: float
    duration_seconds: int
    title: str


@dataclass(frozen=True)
class Inflection:
    index: int
    published_at: datetime
    before_median: float
    after_median: float
    lift: float


@dataclass(frozen=True)
class ChannelTrajectory:
    channel_id: str
    points: tuple[VideoPoint, ...]
    inflection: Inflection | None


def velocity(view_count: int, published_at: datetime, now: datetime) -> float:
    """Views per day since publish. Age clamps to >=1 day."""
    age_days = max((now - published_at).days, 1)
    return view_count / age_days


def build_trajectory(
    channel_id: str, videos: list, now: datetime
) -> ChannelTrajectory:
    required = MIN_SIDE_VIDEOS * 2
    if len(videos) < required:
        raise MissingDataError(
            f"channel {channel_id!r} has {len(videos)} videos; "
            f"need at least {required} to detect an inflection"
        )

    points = tuple(
        sorted(
            (
                VideoPoint(
                    video_id=v.video_id,
                    published_at=v.published_at.value,
                    velocity=velocity(v.view_count.value, v.published_at.value, now),
                    duration_seconds=v.duration_seconds.value,
                    title=v.title,
                )
                for v in videos
            ),
            key=lambda p: p.published_at,
        )
    )

    best: Inflection | None = None
    for index in range(MIN_SIDE_VIDEOS, len(points) - MIN_SIDE_VIDEOS + 1):
        before = median(p.velocity for p in points[:index])
        after = median(p.velocity for p in points[index:])
        if before <= 0:
            continue
        lift = after / before
        if best is None or lift > best.lift:
            best = Inflection(
                index=index,
                published_at=points[index].published_at,
                before_median=before,
                after_median=after,
                lift=lift,
            )

    if best is not None and best.lift < MIN_LIFT:
        best = None

    return ChannelTrajectory(channel_id=channel_id, points=points, inflection=best)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/research/test_trajectory.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/trajectory.py tests/research/test_trajectory.py
git commit -m "feat: add trajectory building and breakout detection"
```

---

### Task 3: Within-channel change attribution

**Files:**
- Create: `src/contentforge/research/changes.py`
- Test: `tests/research/test_changes.py`

**Interfaces:**
- Consumes: `ChannelTrajectory`, `VideoPoint`, `Inflection` (Task 2)
- Produces: `ChangeProfile(duration_before, duration_after, cadence_days_before, cadence_days_after, title_words_before, title_words_after)`; `describe_change(trajectory) -> ChangeProfile | None`

Comparison is within-channel — same creator, same baseline — so channel-level confounds cancel. Cross-channel comparison would invite survivorship bias.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_changes.py
from datetime import datetime, timedelta, timezone

from contentforge.research.changes import describe_change
from contentforge.research.trajectory import (
    ChannelTrajectory,
    Inflection,
    VideoPoint,
)

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


def point(days_ago, vel, duration, title):
    return VideoPoint(
        video_id=f"v{days_ago}",
        published_at=NOW - timedelta(days=days_ago),
        velocity=vel,
        duration_seconds=duration,
        title=title,
    )


def trajectory_with_inflection():
    before = [point(400 - n * 10, 1.0, 600, "short title") for n in range(5)]
    after = [point(200 - n * 5, 50.0, 60, "a much longer clickable title here") for n in range(5)]
    points = tuple(sorted(before + after, key=lambda p: p.published_at))
    return ChannelTrajectory(
        channel_id="UC_a",
        points=points,
        inflection=Inflection(
            index=5,
            published_at=points[5].published_at,
            before_median=1.0,
            after_median=50.0,
            lift=50.0,
        ),
    )


def test_detects_duration_shift():
    profile = describe_change(trajectory_with_inflection())
    assert profile.duration_before == 600
    assert profile.duration_after == 60


def test_detects_title_length_shift():
    profile = describe_change(trajectory_with_inflection())
    assert profile.title_words_after > profile.title_words_before


def test_detects_cadence_shift():
    profile = describe_change(trajectory_with_inflection())
    # before: 10 day gaps; after: 5 day gaps
    assert profile.cadence_days_before == 10
    assert profile.cadence_days_after == 5


def test_returns_none_without_an_inflection():
    points = tuple(point(100 - n, 1.0, 600, "t") for n in range(10))
    traj = ChannelTrajectory(channel_id="UC_a", points=points, inflection=None)
    assert describe_change(traj) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/research/test_changes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.changes'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/changes.py
"""What differed before and after a channel's inflection.

Within-channel comparison only. Comparing breakout channels to each other
invites survivorship bias: "posted consistently then went viral" describes the
winners and equally describes the many who did the same and sank. Holding the
creator fixed cancels channel-level confounds.

This describes what changed and that it coincided with the inflection. It never
claims causation — retention, traffic source and thumbnail CTR are not exposed
for other people's channels.
"""

from dataclasses import dataclass
from statistics import median

from contentforge.research.trajectory import ChannelTrajectory, VideoPoint


@dataclass(frozen=True)
class ChangeProfile:
    duration_before: int
    duration_after: int
    cadence_days_before: int
    cadence_days_after: int
    title_words_before: float
    title_words_after: float


def _median_gap_days(points: tuple[VideoPoint, ...]) -> int:
    if len(points) < 2:
        return 0
    ordered = sorted(points, key=lambda p: p.published_at)
    gaps = [
        (later.published_at - earlier.published_at).days
        for earlier, later in zip(ordered, ordered[1:])
    ]
    return int(median(gaps))


def describe_change(trajectory: ChannelTrajectory) -> ChangeProfile | None:
    if trajectory.inflection is None:
        return None

    before = trajectory.points[: trajectory.inflection.index]
    after = trajectory.points[trajectory.inflection.index :]

    return ChangeProfile(
        duration_before=int(median(p.duration_seconds for p in before)),
        duration_after=int(median(p.duration_seconds for p in after)),
        cadence_days_before=_median_gap_days(before),
        cadence_days_after=_median_gap_days(after),
        title_words_before=median(len(p.title.split()) for p in before),
        title_words_after=median(len(p.title.split()) for p in after),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/research/test_changes.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/changes.py tests/research/test_changes.py
git commit -m "feat: add within-channel change attribution"
```

---

### Task 4: Niche table

**Files:**
- Create: `src/contentforge/research/niches.py`, `data/niches.csv`
- Delete: `src/contentforge/research/rpm_table.py`, `data/rpm_table.csv`, `tests/research/test_rpm_table.py`
- Test: `tests/research/test_niches.py`
- Modify: `.gitignore` — replace `!data/rpm_table.csv` with `!data/niches.csv`

**Interfaces:**
- Consumes: `Fact`, `Provenance`, `MissingDataError`
- Produces: `Niche(name, geography, rpm_low, rpm_high, currency, memberships_available, seed_queries, provenance)`; `load_niches(path) -> dict[tuple[str, str], Niche]`; `rpm_midpoint_usd(niche) -> Fact`; `INR_PER_USD = 88.0`

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_niches.py
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.research.niches import load_niches, rpm_midpoint_usd

TABLE = Path(__file__).parent.parent.parent / "data" / "niches.csv"


def test_table_covers_at_least_twelve_niches():
    niches = load_niches(TABLE)
    names = {key[0] for key in niches}
    assert len(names) >= 12, f"only {len(names)} niches; the point of v2 is breadth"


def test_every_row_is_sourced():
    for niche in load_niches(TABLE).values():
        assert niche.provenance.source_url.startswith("http")
        assert niche.provenance.retrieved_at.tzinfo is not None


def test_every_row_has_seed_queries():
    for key, niche in load_niches(TABLE).items():
        assert len(niche.seed_queries) >= 3, f"{key} has too few seed queries"


def test_seed_queries_are_long_tail_not_head_terms():
    """Head terms return the same incumbents for every niche, which is what
    defeated revision 1. Multi-word queries are the crude proxy for long-tail."""
    for key, niche in load_niches(TABLE).items():
        for query in niche.seed_queries:
            assert len(query.split()) >= 3, f"{key}: {query!r} is a head term"


def test_kids_niche_is_flagged_as_membership_restricted():
    niches = load_niches(TABLE)
    kids = niches[("kids", "US")]
    assert kids.memberships_available is False
    assert kids.rpm_high <= 5, "Made for Kids RPM is contextual-ads only"


def test_finance_allows_memberships():
    assert load_niches(TABLE)[("finance", "US")].memberships_available is True


def test_rpm_midpoint_converts_inr():
    niches = load_niches(TABLE)
    india = niches[("finance", "IN")]
    assert rpm_midpoint_usd(india).value == pytest.approx(
        (india.rpm_low + india.rpm_high) / 2 / 88.0
    )


def test_unsupported_currency_raises():
    from contentforge.research.niches import Niche
    from contentforge.provenance import Provenance
    from datetime import datetime, timezone

    bogus = Niche(
        name="x", geography="EU", rpm_low=1, rpm_high=2, currency="EUR",
        memberships_available=True, seed_queries=("a b c",),
        provenance=Provenance("https://x", "r", datetime.now(timezone.utc)),
    )
    with pytest.raises(MissingDataError):
        rpm_midpoint_usd(bogus)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/research/test_niches.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'contentforge.research.niches'`

- [ ] **Step 3: Write the data file and implementation**

`data/niches.csv` — header plus at least 12 niches. Every row needs a real source URL. Seed queries are pipe-separated and must be three words or more. Starting rows (extend to 12–15; US rows first, add IN rows where you have sourced figures):

```csv
niche,geography,rpm_low,rpm_high,currency,memberships_available,seed_queries,source_url,retrieved_at
finance,US,10,25,USD,true,how to build an emergency fund|index fund vs mutual fund|roth ira explained simply,https://outlierkit.com/blog/youtube-rpm-finance-niche,2026-07-26
finance,IN,80,250,INR,true,best index funds in india|nps vs ppf comparison|how to file itr online,https://www.identitykit.in/blog/youtube-rpm-india-niche-2026,2026-07-26
kids,US,1,3,USD,false,animated stories for toddlers|learn colors with animals|nursery rhymes for babies,https://www.techtimes.com/articles/320340/20260713/ai-kids-cartoon-gold-rush-has-hidden-tax-coppa-cuts-revenue-80.htm,2026-07-26
```

Remaining niches to add with sourced rows: tech, education, health, gaming, true crime, history, DIY, food, travel, self-improvement, business, science, entertainment.

```python
# src/contentforge/research/niches.py
"""Niche table: revenue and monetization constraints, hand-sourced.

RPM drives every ranking decision and an LLM will invent plausible figures, so
each row carries a source URL and retrieval date and is updated deliberately.

memberships_available exists because of Made for Kids. COPPA bars behavioural
tracking on under-13 content, so only contextual ads serve, and Super Thanks
and Channel Memberships are disabled at platform level — removing the Tier 1
revenue path (500 subs) entirely. The scorer penalises restricted niches rather
than the operator arguing about it.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance

INR_PER_USD = 88.0


@dataclass(frozen=True)
class Niche:
    name: str
    geography: str
    rpm_low: float
    rpm_high: float
    currency: str
    memberships_available: bool
    seed_queries: tuple[str, ...]
    provenance: Provenance


def load_niches(path: Path) -> dict[tuple[str, str], Niche]:
    table: dict[tuple[str, str], Niche] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            provenance = Provenance(
                source_url=record["source_url"],
                response_id=f"niches:{record['niche']}:{record['geography']}",
                retrieved_at=datetime.fromisoformat(record["retrieved_at"]).replace(
                    tzinfo=timezone.utc
                ),
            )
            niche = Niche(
                name=record["niche"],
                geography=record["geography"],
                rpm_low=float(record["rpm_low"]),
                rpm_high=float(record["rpm_high"]),
                currency=record["currency"],
                memberships_available=record["memberships_available"].strip().lower() == "true",
                seed_queries=tuple(
                    q.strip() for q in record["seed_queries"].split("|") if q.strip()
                ),
                provenance=provenance,
            )
            table[(niche.name, niche.geography)] = niche
    if not table:
        raise MissingDataError(f"niche table at {path} is empty")
    return table


def rpm_midpoint_usd(niche: Niche) -> Fact:
    midpoint = (niche.rpm_low + niche.rpm_high) / 2
    if niche.currency == "INR":
        return Fact(value=midpoint / INR_PER_USD, provenance=niche.provenance)
    if niche.currency == "USD":
        return Fact(value=midpoint, provenance=niche.provenance)
    raise MissingDataError(
        f"unsupported currency {niche.currency!r} for {niche.name!r}/{niche.geography!r}"
    )
```

- [ ] **Step 4: Run tests, then delete the superseded module**

Run: `.venv/bin/pytest tests/research/test_niches.py -q`
Expected: 8 passed

```bash
git rm src/contentforge/research/rpm_table.py data/rpm_table.csv tests/research/test_rpm_table.py
sed -i 's|!data/rpm_table.csv|!data/niches.csv|' .gitignore
git add data/niches.csv .gitignore
```

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/niches.py tests/research/test_niches.py
git commit -m "feat: replace rpm table with niche table carrying monetization restrictions"
```

---

### Task 5: Trajectory-based scoring

**Files:**
- Create: `src/contentforge/research/score.py` (replacing revision 1's)
- Delete: `src/contentforge/research/metrics.py`, `tests/research/test_metrics.py`
- Test: `tests/research/test_score.py` (replacing revision 1's)

**Interfaces:**
- Consumes: `ChannelTrajectory` (Task 2); `Niche`, `rpm_midpoint_usd` (Task 4); `Fact`
- Produces: `NicheScore(niche, geography, score, rpm_usd, sampled_channels, breakout_count, breakout_rate, median_lift, membership_factor)`; `score_niche(niche, trajectories, rpm_usd) -> NicheScore`; `rank(scores) -> list[NicheScore]`; `MEMBERSHIP_PENALTY = 0.5`

Formula:

```
score = rpm_usd * breakout_rate * median_lift * membership_factor
```

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_score.py  (replace the whole file)
from datetime import datetime, timedelta, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.research.niches import Niche
from contentforge.research.score import MEMBERSHIP_PENALTY, rank, score_niche
from contentforge.research.trajectory import ChannelTrajectory, Inflection, VideoPoint

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def a_niche(name="finance", memberships=True):
    return Niche(
        name=name, geography="US", rpm_low=10, rpm_high=20, currency="USD",
        memberships_available=memberships, seed_queries=("a b c",), provenance=PROV,
    )


def traj(channel_id, lift=None):
    points = tuple(
        VideoPoint(f"v{n}", NOW - timedelta(days=100 - n), 1.0, 600, "t") for n in range(10)
    )
    inflection = (
        None
        if lift is None
        else Inflection(index=5, published_at=points[5].published_at,
                        before_median=1.0, after_median=lift, lift=lift)
    )
    return ChannelTrajectory(channel_id=channel_id, points=points, inflection=inflection)


def test_breakout_rate_is_fraction_with_inflection():
    result = score_niche(a_niche(), [traj("a", 5.0), traj("b"), traj("c"), traj("d")], Fact(15.0, PROV))
    assert result.breakout_rate == pytest.approx(0.25)
    assert result.breakout_count == 1
    assert result.sampled_channels == 4


def test_median_lift_uses_only_breakout_channels():
    result = score_niche(a_niche(), [traj("a", 4.0), traj("b", 10.0), traj("c")], Fact(15.0, PROV))
    assert result.median_lift == pytest.approx(7.0)


def test_score_is_hand_computable():
    result = score_niche(a_niche(), [traj("a", 4.0), traj("b")], Fact(15.0, PROV))
    # rpm 15 * breakout_rate 0.5 * median_lift 4.0 * membership 1.0
    assert result.score == pytest.approx(30.0)


def test_membership_restriction_penalises_score():
    trajectories = [traj("a", 4.0), traj("b")]
    allowed = score_niche(a_niche(memberships=True), trajectories, Fact(15.0, PROV))
    blocked = score_niche(a_niche("kids", memberships=False), trajectories, Fact(15.0, PROV))
    assert blocked.score == pytest.approx(allowed.score * MEMBERSHIP_PENALTY)


def test_niche_with_no_breakouts_scores_zero_not_error():
    result = score_niche(a_niche(), [traj("a"), traj("b")], Fact(15.0, PROV))
    assert result.score == 0.0
    assert result.median_lift == 0.0


def test_empty_trajectory_list_raises():
    with pytest.raises(MissingDataError):
        score_niche(a_niche(), [], Fact(15.0, PROV))


def test_rank_orders_descending_without_mutating():
    a = score_niche(a_niche("a"), [traj("x", 2.0), traj("y")], Fact(5.0, PROV))
    b = score_niche(a_niche("b"), [traj("x", 20.0), traj("y", 20.0)], Fact(25.0, PROV))
    original = [a, b]
    assert [s.niche for s in rank(original)] == ["b", "a"]
    assert original == [a, b]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/research/test_score.py -q`
Expected: FAIL — `ImportError: cannot import name 'MEMBERSHIP_PENALTY'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/score.py  (replace the whole file)
"""Trajectory-based niche ranking.

    score = rpm_usd * breakout_rate * median_lift * membership_factor

RPM sets the revenue ceiling. Breakout rate answers "do newcomers here actually
break through" — the question revision 1's competitor count was trying and
failing to ask, because that metric was bounded by our own sample size. Median
lift answers "when they do, how big is the jump". Membership factor encodes
whether first revenue is reachable at 500 subscribers or only at 1,000.

These weights are a hypothesis. If a run ranks something obviously wrong,
suspect this formula before the data.
"""

from dataclasses import dataclass
from statistics import median

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.research.niches import Niche

# Made for Kids removes Super Thanks and Memberships, so the Tier 1 revenue
# path (500 subs) does not exist. Halving is a judgement call, not a measurement.
MEMBERSHIP_PENALTY = 0.5


@dataclass(frozen=True)
class NicheScore:
    niche: str
    geography: str
    score: float
    rpm_usd: Fact
    sampled_channels: int
    breakout_count: int
    breakout_rate: float
    median_lift: float
    membership_factor: float


def score_niche(niche: Niche, trajectories: list, rpm_usd: Fact) -> NicheScore:
    if not trajectories:
        raise MissingDataError(
            f"no trajectories for niche {niche.name!r}; refusing to score an empty sample"
        )

    lifts = [t.inflection.lift for t in trajectories if t.inflection is not None]
    breakout_rate = len(lifts) / len(trajectories)
    median_lift = median(lifts) if lifts else 0.0
    membership_factor = 1.0 if niche.memberships_available else MEMBERSHIP_PENALTY

    return NicheScore(
        niche=niche.name,
        geography=niche.geography,
        score=rpm_usd.value * breakout_rate * median_lift * membership_factor,
        rpm_usd=rpm_usd,
        sampled_channels=len(trajectories),
        breakout_count=len(lifts),
        breakout_rate=breakout_rate,
        median_lift=median_lift,
        membership_factor=membership_factor,
    )


def rank(scores: list[NicheScore]) -> list[NicheScore]:
    """Return a new list ordered best-first. Does not mutate the input."""
    return sorted(scores, key=lambda score: score.score, reverse=True)
```

- [ ] **Step 4: Run tests and remove the superseded module**

Run: `.venv/bin/pytest tests/research/test_score.py -q`
Expected: 7 passed

```bash
git rm src/contentforge/research/metrics.py tests/research/test_metrics.py
```

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/score.py tests/research/test_score.py
git commit -m "feat: replace state metrics with trajectory-based scoring"
```

---

### Task 6: Report with readable provenance

**Files:**
- Modify: `src/contentforge/research/report.py`
- Test: `tests/research/test_report.py` (replace)

**Interfaces:**
- Consumes: `NicheScore` (Task 5); `ChangeProfile` (Task 3)
- Produces: `write_report(scores, change_profiles, raw_responses, out_dir, generated_at) -> tuple[Path, Path]` where `change_profiles: dict[str, list[ChangeProfile]]` keyed by niche name and `raw_responses: dict[str, dict]` keyed by etag

Revision 1 embedded all 50 channel ids in every provenance URL, producing ~3,000-character source links and an unreadable report. Now the markdown cites the etag and links to `raw/<etag>.json`.

- [ ] **Step 1: Write the failing test**

```python
# tests/research/test_report.py  (replace the whole file)
import json
from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.research.report import write_report
from contentforge.research.score import NicheScore

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
LONG_URL = "https://www.googleapis.com/youtube/v3/channels?id=" + ",".join(
    f"UC_{n}" for n in range(50)
)
PROV = Provenance(source_url=LONG_URL, response_id="etag-abc", retrieved_at=NOW)


def a_score(niche="finance"):
    return NicheScore(
        niche=niche, geography="US", score=42.0, rpm_usd=Fact(15.0, PROV),
        sampled_channels=100, breakout_count=12, breakout_rate=0.12,
        median_lift=7.5, membership_factor=1.0,
    )


def test_markdown_cites_etag_not_the_giant_url(tmp_path):
    _, md_path = write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    text = md_path.read_text()
    assert "etag-abc" in text
    assert LONG_URL not in text, "the 3000-char URL must not appear in the markdown"


def test_markdown_stays_readable(tmp_path):
    _, md_path = write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    longest = max(len(line) for line in md_path.read_text().split("\n"))
    assert longest < 300, f"longest line is {longest} chars"


def test_raw_responses_are_written_for_audit(tmp_path):
    write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    raw = tmp_path / "raw" / "etag-abc.json"
    assert raw.exists()
    assert json.loads(raw.read_text()) == {"ok": True}


def test_json_retains_full_source_url(tmp_path):
    """The markdown is for reading; the JSON keeps everything."""
    json_path, _ = write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    payload = json.loads(json_path.read_text())
    assert payload["niches"][0]["rpm_usd"]["source_url"] == LONG_URL


def test_report_records_sample_size_and_breakout_stats(tmp_path):
    json_path, _ = write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    entry = json.loads(json_path.read_text())["niches"][0]
    assert entry["sampled_channels"] == 100
    assert entry["breakout_count"] == 12
    assert entry["breakout_rate"] == pytest.approx(0.12)
    assert entry["median_lift"] == pytest.approx(7.5)


def test_empty_scores_raise(tmp_path):
    with pytest.raises(MissingDataError):
        write_report([], {}, {}, tmp_path, NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/research/test_report.py -q`
Expected: FAIL — `TypeError: write_report() takes 3 positional arguments but 5 were given`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/research/report.py  (replace the whole file)
"""Research report output.

report.json is the machine-readable artifact and keeps every full source URL.
report.md is for the human gate and cites response etags instead, linking to
raw/<etag>.json — revision 1 inlined all 50 channel ids per citation and
produced ~3,000-character links that made the report unreadable.
"""

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
    scores: list[NicheScore],
    change_profiles: dict,
    raw_responses: dict,
    out_dir: Path,
    generated_at: datetime,
) -> tuple[Path, Path]:
    if not scores:
        raise MissingDataError("refusing to write an empty research report")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for etag, body in raw_responses.items():
        (raw_dir / f"{etag}.json").write_text(json.dumps(body, indent=2))

    payload = {
        "generated_at": generated_at.isoformat(),
        "niches": [
            {
                "niche": s.niche,
                "geography": s.geography,
                "score": s.score,
                "rpm_usd": _fact_json(s.rpm_usd),
                "sampled_channels": s.sampled_channels,
                "breakout_count": s.breakout_count,
                "breakout_rate": s.breakout_rate,
                "median_lift": s.median_lift,
                "membership_factor": s.membership_factor,
            }
            for s in scores
        ],
    }
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(payload, indent=2))

    lines = [
        f"# Niche research — {generated_at.date().isoformat()}",
        "",
        "Figures cite the API response etag; raw bodies are in `raw/`.",
        "",
        "| # | niche | geo | score | RPM $ | channels | breakouts | rate | median lift |",
        "|---|-------|-----|-------|-------|----------|-----------|------|-------------|",
    ]
    for position, s in enumerate(scores, start=1):
        lines.append(
            f"| {position} | {s.niche} | {s.geography} | {s.score:.2f} | "
            f"{s.rpm_usd.value:.2f} | {s.sampled_channels} | {s.breakout_count} | "
            f"{s.breakout_rate:.2f} | {s.median_lift:.1f} |"
        )
    lines += ["", f"RPM source etag: `{scores[0].rpm_usd.provenance.response_id}`", ""]

    for s in scores:
        profiles = change_profiles.get(s.niche) or []
        if not profiles:
            continue
        lines += [f"## What changed at breakout — {s.niche}", ""]
        for profile in profiles[:10]:
            lines.append(
                f"- duration {profile.duration_before}s → {profile.duration_after}s; "
                f"cadence {profile.cadence_days_before}d → {profile.cadence_days_after}d; "
                f"title {profile.title_words_before:.0f} → {profile.title_words_after:.0f} words"
            )
        lines += [
            "",
            "_These changes coincided with the inflection. Retention, traffic source "
            "and thumbnail CTR are not available for other channels, so this is "
            "association, not cause._",
            "",
        ]

    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(lines))
    return json_path, md_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/research/test_report.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/research/report.py tests/research/test_report.py
git commit -m "feat: cite response etags in markdown and store raw bodies"
```

---

### Task 7: Wide-sampling CLI

**Files:**
- Modify: `src/contentforge/cli.py`
- Delete: `src/contentforge/config.py` (seed queries now live in `data/niches.csv`)
- Test: `tests/test_cli_end_to_end.py` (replace)

**Interfaces:**
- Consumes: everything from Tasks 1–6
- Produces: `run_research(client, niches, table_path, out_dir, now, ledger, channels_per_niche=100, videos_per_channel=50) -> tuple[list[NicheScore], QuotaLedger]`; `main(argv) -> int`

Per niche: N searches (100 units each) → channel ids; uploads playlists (1 unit per 50 channels); per channel one `playlistItems.list` (1) plus `videos.list` batches (1 per 50 videos). Channels with fewer than 10 videos are skipped, not failed — a new channel has no trajectory to read.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_end_to_end.py  (replace the whole file)
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contentforge.cli import run_research
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
TABLE = Path(__file__).parent.parent / "data" / "niches.csv"


def make_transport(channels_per_search=4, videos_per_channel=12):
    """Fake YouTube: every channel has a clean breakout halfway through."""

    def transport(endpoint, params):
        if endpoint == "search.list":
            return {
                "etag": "search-etag",
                "items": [
                    {"id": {"channelId": f"UC_{n}"}, "snippet": {"title": f"C{n}"}}
                    for n in range(channels_per_search)
                ],
            }
        if endpoint == "channels.list":
            ids = params["id"].split(",")
            return {
                "etag": "chan-etag",
                "items": [
                    {"id": cid, "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid}}}
                    for cid in ids
                ],
            }
        if endpoint == "playlistItems.list":
            pl = params["playlistId"]
            return {
                "etag": "pl-etag",
                "items": [
                    {"contentDetails": {"videoId": f"{pl}_v{n}"}}
                    for n in range(videos_per_channel)
                ],
            }
        if endpoint == "videos.list":
            items = []
            for vid in params["id"].split(","):
                index = int(vid.rsplit("_v", 1)[1])
                published = NOW - timedelta(days=400 - index * 20)
                views = 100 if index < videos_per_channel // 2 else 200_000
                items.append(
                    {
                        "id": vid,
                        "snippet": {
                            "channelId": vid.split("_v")[0].replace("UUUC", "UC"),
                            "title": "a reasonably long video title",
                            "publishedAt": published.isoformat().replace("+00:00", "Z"),
                        },
                        "statistics": {"viewCount": str(views)},
                        "contentDetails": {"duration": "PT10M"},
                    }
                )
            return {"etag": "vid-etag", "items": items}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return transport


def test_run_research_ranks_niches_by_trajectory(tmp_path):
    client = YouTubeClient(api_key="k", transport=make_transport())
    scores, ledger = run_research(
        client=client, niches=None, table_path=TABLE, out_dir=tmp_path,
        now=NOW, ledger=QuotaLedger(daily_limit=10_000_000),
        channels_per_niche=4, videos_per_channel=12,
    )
    assert scores, "expected at least one scored niche"
    assert scores[0].score >= scores[-1].score
    assert scores[0].sampled_channels > 0
    assert scores[0].breakout_count > 0, "the fake data has a clean breakout"


def test_kids_is_penalised_relative_to_its_raw_numbers(tmp_path):
    client = YouTubeClient(api_key="k", transport=make_transport())
    scores, _ = run_research(
        client=client, niches=None, table_path=TABLE, out_dir=tmp_path,
        now=NOW, ledger=QuotaLedger(daily_limit=10_000_000),
        channels_per_niche=4, videos_per_channel=12,
    )
    kids = next(s for s in scores if s.niche == "kids")
    assert kids.membership_factor == 0.5


def test_report_files_are_written(tmp_path):
    client = YouTubeClient(api_key="k", transport=make_transport())
    run_research(
        client=client, niches=None, table_path=TABLE, out_dir=tmp_path,
        now=NOW, ledger=QuotaLedger(daily_limit=10_000_000),
        channels_per_niche=4, videos_per_channel=12,
    )
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "raw").is_dir()


def test_run_stops_cleanly_when_quota_exhausted(tmp_path):
    import pytest
    from contentforge.errors import QuotaExceededError

    client = YouTubeClient(api_key="k", transport=make_transport())
    with pytest.raises(QuotaExceededError):
        run_research(
            client=client, niches=None, table_path=TABLE, out_dir=tmp_path,
            now=NOW, ledger=QuotaLedger(daily_limit=150),
            channels_per_niche=4, videos_per_channel=12,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_end_to_end.py -q`
Expected: FAIL — `TypeError: run_research() got an unexpected keyword argument 'channels_per_niche'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contentforge/cli.py  (replace the whole file)
"""Command line entry point.

    pipeline research [--geography US] [--out data/research]
                      [--channels-per-niche 100] [--videos-per-channel 50]

Reads YOUTUBE_API_KEY from the environment and fails loudly if absent.
Credentials come only from the environment and are never logged.
"""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.changes import describe_change
from contentforge.research.niches import load_niches, rpm_midpoint_usd
from contentforge.research.report import write_report
from contentforge.research.score import NicheScore, rank, score_niche
from contentforge.research.trajectory import MIN_SIDE_VIDEOS, build_trajectory

MIN_VIDEOS_FOR_TRAJECTORY = MIN_SIDE_VIDEOS * 2


def run_research(
    client: YouTubeClient,
    niches,
    table_path: Path,
    out_dir: Path,
    now: datetime,
    ledger: QuotaLedger,
    channels_per_niche: int = 100,
    videos_per_channel: int = 50,
    geography: str | None = None,
) -> tuple[list[NicheScore], QuotaLedger]:
    table = niches if niches is not None else load_niches(table_path)
    current = ledger
    scores: list[NicheScore] = []
    change_profiles: dict[str, list] = {}
    raw_responses: dict[str, dict] = {}

    for (name, geo), niche in table.items():
        if geography is not None and geo != geography:
            continue

        channel_ids: list[str] = []
        for query in niche.seed_queries:
            if len(channel_ids) >= channels_per_niche:
                break
            refs, current = client.search_channels(query, current)
            for ref in refs:
                if ref.channel_id not in channel_ids:
                    channel_ids.append(ref.channel_id)
        channel_ids = channel_ids[:channels_per_niche]
        if not channel_ids:
            continue

        playlists, current = client.get_uploads_playlists(channel_ids, current)

        trajectories = []
        profiles = []
        for channel_id, playlist_id in playlists.items():
            video_ids, current = client.get_playlist_video_ids(
                playlist_id, current, max_videos=videos_per_channel
            )
            if len(video_ids) < MIN_VIDEOS_FOR_TRAJECTORY:
                # A young channel has no trajectory to read. Skipping is not a
                # failure; it is the honest answer for that channel.
                continue
            videos, current = client.get_videos(video_ids, current)
            if len(videos) < MIN_VIDEOS_FOR_TRAJECTORY:
                continue
            trajectory = build_trajectory(channel_id, videos, now)
            trajectories.append(trajectory)
            profile = describe_change(trajectory)
            if profile is not None:
                profiles.append(profile)

        if not trajectories:
            continue

        rpm = rpm_midpoint_usd(niche)
        scores.append(score_niche(niche, trajectories, rpm))
        change_profiles[name] = profiles

    if not scores:
        raise MissingDataError("no niche produced a scorable sample")

    ranked = rank(scores)
    write_report(ranked, change_profiles, raw_responses, out_dir, now)
    return ranked, current


def _live_transport(api_key: str):
    from googleapiclient.discovery import build

    service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def _transport(endpoint: str, params: dict) -> dict:
        resource, method = endpoint.split(".")
        return getattr(getattr(service, resource)(), method)(**params).execute()

    return _transport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    research = subparsers.add_parser("research", help="rank niches from live YouTube data")
    research.add_argument("--geography", default=None)
    research.add_argument("--out", type=Path, default=Path("data/research"))
    research.add_argument("--channels-per-niche", type=int, default=100)
    research.add_argument("--videos-per-channel", type=int, default=50)
    args = parser.parse_args(argv)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("YOUTUBE_API_KEY is not set (copy .env.example to .env)")

    now = datetime.now(timezone.utc)
    out_dir = args.out / now.date().isoformat()
    client = YouTubeClient(api_key=api_key, transport=_live_transport(api_key))

    ranked, ledger = run_research(
        client=client, niches=None, table_path=Path("data/niches.csv"),
        out_dir=out_dir, now=now, ledger=QuotaLedger(),
        channels_per_niche=args.channels_per_niche,
        videos_per_channel=args.videos_per_channel,
        geography=args.geography,
    )
    print(
        f"Wrote {len(ranked)} ranked niches to {out_dir} "
        f"({ledger.spent} of {ledger.daily_limit} quota units used)"
    )
    return 0
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass

```bash
git rm src/contentforge/config.py
```

- [ ] **Step 5: Commit**

```bash
git add src/contentforge/cli.py tests/test_cli_end_to_end.py
git commit -m "feat: wide-sampling research loop over the niche table"
```

---

## Definition of done

`pipeline research` runs against a real key and writes `data/research/<date>/report.{json,md}` plus `raw/`, sampling on the order of 500 channels across 12–15 niches within the 10,000-unit budget, with a readable markdown report.

**The gate is unchanged and it is human:** if the top-ranked niche is one you could have guessed without building this, the engine has told you nothing. Revision 1 failed that gate. If revision 2 also fails it — if breakout rate turns out as flat across niches as competitor count was — then the premise that public metrics can identify a niche is wrong, and niche selection should fall back to RPM plus operator interest. That is a legitimate finding, and it is cheaper to learn here than after fifty videos.

## Quota budget

| step | cost |
|---|---|
| searches: 15 niches × 3 queries × 100 | 4,500 |
| uploads playlists: 500 channels ÷ 50 × 1 | 10 |
| playlistItems: 500 channels × 1 | 500 |
| videos: 500 channels × 1 | 500 |
| **total** | **~5,510 of 10,000** |

One full run per day fits comfortably. Start with `--channels-per-niche 25` while validating, then widen.
