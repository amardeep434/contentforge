import json
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.harvest.plan import slugify, HarvestEntry, write_plan, read_plan


def test_slugify():
    assert slugify("The Economics of Owning a Laundromat!") == "the-economics-of-owning-a-laundromat"


def test_plan_round_trip(tmp_path):
    entries = [HarvestEntry("s1", "T1", "v1", "http://x/v1", "T1"),
               HarvestEntry("s2", "T2", "v2", "http://x/v2", "T2")]
    write_plan(entries, tmp_path / "biz", "chan")
    back = read_plan(tmp_path / "biz", "chan")
    assert [e.slug for e in back] == ["s1", "s2"]
    assert back[0].topic == "T1"


def test_build_plan_from_a_fake_client():
    from contentforge.harvest.plan import build_plan

    class FakeFacts:
        channel_id = "UCabcdefghijklmnopqrstuv"      # 24 chars

    class FakeVideo:
        def __init__(self, vid, title):
            self.video_id = vid
            self.title = title

    class FakeClient:
        def channel_by_handle(self, handle, ledger):
            assert handle == "somechannel"           # @ stripped
            return FakeFacts(), ledger
        def get_uploads_playlists(self, ids, ledger):
            return {ids[0]: "UU_uploads"}, ledger
        def get_playlist_video_ids(self, playlist_id, ledger, max_videos):
            assert playlist_id == "UU_uploads"
            return ["v1", "v2"], ledger
        def get_videos(self, ids, ledger):
            return [FakeVideo("v1", "Owning a Laundromat"),
                    FakeVideo("v2", "Owning a Car Wash!")], ledger

    entries, _ledger = build_plan(FakeClient(), "@somechannel", ledger=object(), limit=10)
    assert [e.slug for e in entries] == ["owning-a-laundromat", "owning-a-car-wash"]
    assert entries[0].url == "https://www.youtube.com/watch?v=v1"
    assert entries[0].topic == "Owning a Laundromat"


class _FakeFacts:
    channel_id = "UCabcdefghijklmnopqrstuv"


class _FakeVideo:
    def __init__(self, vid, title):
        self.video_id = vid
        self.title = title


def _fake_client(video_ids, videos):
    class FakeClient:
        def channel_by_handle(self, handle, ledger):
            return _FakeFacts(), ledger
        def get_uploads_playlists(self, ids, ledger):
            return {ids[0]: "UU_uploads"}, ledger
        def get_playlist_video_ids(self, playlist_id, ledger, max_videos):
            return video_ids, ledger
        def get_videos(self, ids, ledger):
            return videos, ledger
    return FakeClient()


def test_build_plan_dedupes_colliding_slugs():
    from contentforge.harvest.plan import build_plan

    client = _fake_client(
        ["v1", "v2"],
        [_FakeVideo("v1", "Owning a Laundromat!"), _FakeVideo("v2", "Owning a Laundromat?")],
    )
    entries, _ledger = build_plan(client, "@somechannel", ledger=object(), limit=10)
    assert [e.slug for e in entries] == ["owning-a-laundromat", "owning-a-laundromat-2"]


def test_build_plan_falls_back_to_video_id_for_empty_slug():
    from contentforge.harvest.plan import build_plan

    client = _fake_client(["v1"], [_FakeVideo("v1", "Кафе")])
    entries, _ledger = build_plan(client, "@somechannel", ledger=object(), limit=10)
    assert entries[0].slug == "v1"


def test_build_plan_raises_when_all_videos_dropped_for_missing_duration():
    from contentforge.harvest.plan import build_plan

    client = _fake_client(["v1", "v2"], [])
    with pytest.raises(MissingDataError):
        build_plan(client, "@somechannel", ledger=object(), limit=10)


def test_build_plan_warns_when_limit_exceeds_page_cap(caplog):
    from contentforge.harvest.plan import build_plan

    client = _fake_client(["v1"], [_FakeVideo("v1", "T")])
    with caplog.at_level("WARNING"):
        build_plan(client, "@somechannel", ledger=object(), limit=75)
    assert any("capped at 50" in r.message for r in caplog.records)


def test_read_plan_raises_missing_data_error_on_malformed_row(tmp_path):
    path = tmp_path / "biz" / "harvest" / "chan" / "plan.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"slug": "s1"}\n', encoding="utf-8")  # missing required fields
    with pytest.raises(MissingDataError, match="row 1"):
        read_plan(tmp_path / "biz", "chan")


def test_write_plan_warns_when_overwriting_existing_plan(tmp_path, caplog):
    entries = [HarvestEntry("s1", "T1", "v1", "http://x/v1", "T1")]
    write_plan(entries, tmp_path / "biz", "chan")
    with caplog.at_level("WARNING"):
        write_plan(entries, tmp_path / "biz", "chan")
    assert any("overwriting" in r.message for r in caplog.records)


def test_build_plan_calls_on_ledger_after_each_completed_api_call():
    """The handler needs the latest ledger even if a later call in build_plan
    raises, so on_ledger must fire after every completed call, in order,
    with strictly increasing spend (each fake call charges the real ledger)."""
    from contentforge.harvest.plan import build_plan
    from contentforge.providers.quota import QuotaLedger

    class FakeClient:
        def channel_by_handle(self, handle, ledger):
            return _FakeFacts(), ledger.charge("channels.list")
        def get_uploads_playlists(self, ids, ledger):
            return {ids[0]: "UU_uploads"}, ledger.charge("playlistItems.list")
        def get_playlist_video_ids(self, playlist_id, ledger, max_videos):
            return ["v1"], ledger.charge("playlistItems.list")
        def get_videos(self, ids, ledger):
            return [_FakeVideo("v1", "Owning a Laundromat")], ledger.charge("videos.list")

    seen = []
    entries, final_ledger = build_plan(
        FakeClient(), "@somechannel", ledger=QuotaLedger(), limit=10,
        on_ledger=seen.append,
    )
    assert [e.slug for e in entries] == ["owning-a-laundromat"]
    assert len(seen) == 4
    spends = [l.spent for l in seen]
    assert spends == sorted(spends) and spends[0] > 0
    assert seen[-1].spent == final_ledger.spent


def test_build_plan_on_ledger_captures_partial_spend_on_mid_call_failure():
    """If get_playlist_video_ids raises (e.g. empty channel), on_ledger must
    already have captured the two calls billed before it."""
    from contentforge.harvest.plan import build_plan
    from contentforge.providers.quota import QuotaLedger

    class FakeClient:
        def channel_by_handle(self, handle, ledger):
            return _FakeFacts(), ledger.charge("channels.list")
        def get_uploads_playlists(self, ids, ledger):
            return {ids[0]: "UU_uploads"}, ledger.charge("playlistItems.list")
        def get_playlist_video_ids(self, playlist_id, ledger, max_videos):
            return [], ledger.charge("playlistItems.list")   # empty -> raises below
        def get_videos(self, ids, ledger):
            raise AssertionError("should never be called")

    seen = []
    with pytest.raises(MissingDataError):
        build_plan(FakeClient(), "@somechannel", ledger=QuotaLedger(), limit=10,
                   on_ledger=seen.append)
    assert len(seen) == 3          # channel_by_handle, get_uploads_playlists, get_playlist_video_ids
    assert seen[-1].spent > 0


def test_disambiguate_slugs_suffixes_collision_with_foreign_channel(tmp_path):
    from contentforge.harvest.plan import disambiguate_slugs

    niche = tmp_path / "biz"
    plan_a = niche / "harvest" / "chanA" / "plan.jsonl"
    plan_a.parent.mkdir(parents=True)
    plan_a.write_text(
        json.dumps({"slug": "owning-a-laundromat", "topic": "T", "video_id": "v1",
                    "url": "http://x/v1", "title": "T"}) + "\n",
        encoding="utf-8",
    )

    entry_b = HarvestEntry("owning-a-laundromat", "T2", "v2", "http://x/v2", "T2")
    out = disambiguate_slugs([entry_b], niche, channel="chanB")
    assert out[0].slug == "owning-a-laundromat-2"
    assert out[0].topic == "T2" and out[0].video_id == "v2"   # only slug changed


def test_disambiguate_slugs_leaves_same_channel_slug_unchanged(tmp_path):
    """Resume: re-harvesting chanA against its own existing plan must not
    suffix its own slugs."""
    from contentforge.harvest.plan import disambiguate_slugs

    niche = tmp_path / "biz"
    plan_a = niche / "harvest" / "chanA" / "plan.jsonl"
    plan_a.parent.mkdir(parents=True)
    plan_a.write_text(
        json.dumps({"slug": "owning-a-laundromat", "topic": "T", "video_id": "v1",
                    "url": "http://x/v1", "title": "T"}) + "\n",
        encoding="utf-8",
    )

    entry_a = HarvestEntry("owning-a-laundromat", "T", "v1", "http://x/v1", "T")
    out = disambiguate_slugs([entry_a], niche, channel="chanA")
    assert out[0].slug == "owning-a-laundromat"


def test_disambiguate_slugs_no_collision_unchanged(tmp_path):
    from contentforge.harvest.plan import disambiguate_slugs

    niche = tmp_path / "biz"
    entry = HarvestEntry("owning-a-car-wash", "T", "v1", "http://x/v1", "T")
    out = disambiguate_slugs([entry], niche, channel="chanB")
    assert out[0].slug == "owning-a-car-wash"


def test_disambiguate_slugs_guards_against_within_batch_duplicate(tmp_path):
    """foreign={x} + this channel's own entries [x, x-2] (build_plan already
    deduped two same-title videos within-channel). x -> x-2 collides with the
    second entry's own slug unless the guard checks `taken`, not just
    `foreign`. Both outputs must end up distinct."""
    from contentforge.harvest.plan import disambiguate_slugs

    niche = tmp_path / "biz"
    plan_a = niche / "harvest" / "chanA" / "plan.jsonl"
    plan_a.parent.mkdir(parents=True)
    plan_a.write_text(
        json.dumps({"slug": "x", "topic": "T", "video_id": "v0",
                    "url": "http://x/v0", "title": "T"}) + "\n",
        encoding="utf-8",
    )

    entries = [
        HarvestEntry("x", "T1", "v1", "http://x/v1", "T1"),
        HarvestEntry("x-2", "T2", "v2", "http://x/v2", "T2"),
    ]
    out = disambiguate_slugs(entries, niche, channel="chanB")
    slugs = [e.slug for e in out]
    assert len(slugs) == len(set(slugs)), f"duplicate slugs: {slugs}"
    assert slugs == ["x-2", "x-2-2"]


def test_disambiguate_slugs_skips_corrupt_line_in_foreign_plan(tmp_path, caplog):
    """A hand-edited/corrupt line in a DIFFERENT channel's plan.jsonl must not
    abort this harvest; it should be logged and skipped, while good lines in
    the same foreign plan still count."""
    from contentforge.harvest.plan import disambiguate_slugs

    niche = tmp_path / "biz"
    plan_a = niche / "harvest" / "chanA" / "plan.jsonl"
    plan_a.parent.mkdir(parents=True)
    plan_a.write_text(
        "not json at all\n" + json.dumps({"slug": "x", "topic": "T", "video_id": "v0",
                                           "url": "http://x/v0", "title": "T"}) + "\n",
        encoding="utf-8",
    )

    entry = HarvestEntry("x", "T1", "v1", "http://x/v1", "T1")
    with caplog.at_level("WARNING"):
        out = disambiguate_slugs([entry], niche, channel="chanB")
    assert out[0].slug == "x-2"          # good foreign row "x" still claimed
    assert any("plan.jsonl" in r.message for r in caplog.records)
