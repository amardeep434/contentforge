from pathlib import Path

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
