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
