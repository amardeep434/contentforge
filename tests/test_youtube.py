"""Upload logic, driven by a fake YouTube service. Nothing touches the network."""

import json

import pytest

from contentforge.errors import MissingDataError
from contentforge.publish.metadata import Metadata
from contentforge.publish.youtube import (
    DEFAULT_PRIVACY,
    record_upload,
    set_thumbnail,
    upload,
    watch_url,
)

META = Metadata(title="How fans work", description="They move air.",
                tags=("fans", "cooling"))


class FakeInsert:
    def __init__(self, recorder, chunks=1):
        self._recorder = recorder
        self._chunks = chunks

    def next_chunk(self):
        self._chunks -= 1
        if self._chunks > 0:
            return ({"progress": 0.5}, None)
        return (None, {"id": "vid123"})


class FakeVideos:
    def __init__(self, recorder, chunks=1):
        self._recorder = recorder
        self._chunks = chunks

    def insert(self, part, body, media_body):
        self._recorder["insert"] = {"part": part, "body": body, "media": media_body}
        return FakeInsert(self._recorder, self._chunks)


class FakeThumbnails:
    def __init__(self, recorder):
        self._recorder = recorder

    def set(self, videoId, media_body):
        self._recorder["thumbnail"] = {"videoId": videoId, "media": media_body}
        return self

    def execute(self):
        return {}


class FakeService:
    def __init__(self, chunks=1):
        self.recorder = {}
        self._chunks = chunks

    def videos(self):
        return FakeVideos(self.recorder, self._chunks)

    def thumbnails(self):
        return FakeThumbnails(self.recorder)


def video_file(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fake mp4 bytes")
    return path


def test_upload_returns_the_video_id(tmp_path):
    service = FakeService()
    vid = upload(service, video_file(tmp_path), META,
                 media_factory=lambda p: f"media:{p}")
    assert vid == "vid123"


def test_the_default_privacy_is_private(tmp_path):
    # A public-by-default upload is one fat-fingered command from publishing an
    # unreviewed video.
    service = FakeService()
    upload(service, video_file(tmp_path), META, media_factory=lambda p: p)
    assert service.recorder["insert"]["body"]["status"]["privacyStatus"] == "private"
    assert DEFAULT_PRIVACY == "private"


def test_metadata_reaches_the_insert_body(tmp_path):
    service = FakeService()
    upload(service, video_file(tmp_path), META, media_factory=lambda p: p)
    snippet = service.recorder["insert"]["body"]["snippet"]
    assert snippet["title"] == "How fans work"
    assert snippet["tags"] == ["fans", "cooling"]


def test_made_for_kids_is_declared_false(tmp_path):
    # Required since 2020, or the insert is rejected.
    service = FakeService()
    upload(service, video_file(tmp_path), META, media_factory=lambda p: p)
    assert service.recorder["insert"]["body"]["status"]["selfDeclaredMadeForKids"] is False


def test_a_resumable_upload_drives_every_chunk(tmp_path):
    service = FakeService(chunks=3)
    assert upload(service, video_file(tmp_path), META,
                  media_factory=lambda p: p) == "vid123"


def test_an_invalid_privacy_is_rejected(tmp_path):
    with pytest.raises(MissingDataError, match="not one of"):
        upload(FakeService(), video_file(tmp_path), META, privacy="everyone",
               media_factory=lambda p: p)


def test_a_missing_video_raises(tmp_path):
    with pytest.raises(MissingDataError, match="no video to upload"):
        upload(FakeService(), tmp_path / "absent.mp4", META,
               media_factory=lambda p: p)


def test_an_empty_video_raises(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(MissingDataError, match="no video to upload"):
        upload(FakeService(), empty, META, media_factory=lambda p: p)


def test_the_thumbnail_is_set_against_the_video(tmp_path):
    thumb = tmp_path / "t.png"
    thumb.write_bytes(b"png")
    service = FakeService()
    set_thumbnail(service, "vid123", thumb, media_factory=lambda p: p)
    assert service.recorder["thumbnail"]["videoId"] == "vid123"


def test_a_missing_thumbnail_raises(tmp_path):
    with pytest.raises(MissingDataError, match="no thumbnail"):
        set_thumbnail(FakeService(), "vid123", tmp_path / "absent.png",
                      media_factory=lambda p: p)


def test_the_upload_is_recorded_so_a_rerun_does_not_duplicate(tmp_path):
    path = record_upload(tmp_path, "vid123", "private")
    data = json.loads(path.read_text())
    assert data["video_id"] == "vid123"
    assert data["url"] == watch_url("vid123")
    assert "vid123" in data["url"]
