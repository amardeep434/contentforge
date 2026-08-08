"""Upload a finished video to YouTube.

Publishing is the one stage that is not idempotent and not reversible: a second
run uploads a second copy, and a public video is public the moment it lands. So
this stage does nothing on its own. `make` never calls it; a human runs
`pipeline publish` deliberately, and the default privacy is **private** - the
video appears in the channel's own dashboard and nowhere else until a person
changes it in the YouTube UI.

Uploading needs OAuth, not an API key. The API key that scraping uses is
read-only and cannot write to a channel (C: scraping and publishing never share
credentials). The user authorises once in a browser; the token is cached and
refreshed after that.

The Google client is injected everywhere it is used, so the upload logic - the
part that could put the wrong privacy on a video - is tested without touching
YouTube.
"""

import json
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.publish.metadata import Metadata

#: Write scope only. Never request more than uploading needs.
SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)

#: The only default that cannot embarrass anyone. A public-by-default upload is
#: one fat-fingered command away from publishing an unreviewed video.
DEFAULT_PRIVACY = "private"
PRIVACIES = ("private", "unlisted", "public")


def load_credentials(client_secret: Path, token: Path, flow_runner=None):
    """OAuth credentials, from a cached token or a one-time browser consent.

    `flow_runner` is injected in tests so nothing opens a browser. In
    production it is the installed-app flow, which prints a URL and waits.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise MissingDataError(
            "google-auth is not installed. Run: pip install "
            "'contentforge[publish]'"
        ) from None

    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), list(SCOPES))
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json())
            return creds

    if not client_secret.exists():
        raise MissingDataError(
            f"no OAuth client secret at {client_secret}. Create a Desktop OAuth "
            "client in Google Cloud Console and download it there. See "
            "docs/setup/publishing.md"
        )
    creds = (flow_runner or _browser_flow)(client_secret)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json())
    return creds


def _browser_flow(client_secret: Path):
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise MissingDataError(
            "google-auth-oauthlib is not installed. Run: pip install "
            "'contentforge[publish]'"
        ) from None
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), list(SCOPES))
    return flow.run_local_server(port=0)


def build_service(credentials):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _body(metadata: Metadata, privacy: str) -> dict:
    if privacy not in PRIVACIES:
        raise MissingDataError(
            f"privacy {privacy!r} is not one of {', '.join(PRIVACIES)}"
        )
    return {
        "snippet": {
            "title": metadata.title,
            "description": metadata.description,
            "tags": list(metadata.tags),
            "categoryId": metadata.category_id,
        },
        "status": {
            "privacyStatus": privacy,
            # Marks the video as not made for kids; required since 2020 or the
            # insert is rejected.
            "selfDeclaredMadeForKids": False,
        },
    }


def upload(service, video: Path, metadata: Metadata,
           privacy: str = DEFAULT_PRIVACY, media_factory=None) -> str:
    """Insert the video, resumably, and return its id.

    Resumable because a 20-minute 1080p file is large enough that a single-shot
    upload drops on any network hiccup; resumable retries the failed chunk
    rather than the whole file.
    """
    if not video.exists() or video.stat().st_size == 0:
        raise MissingDataError(f"no video to upload at {video}")

    if media_factory is None:
        from googleapiclient.http import MediaFileUpload

        media_factory = lambda path: MediaFileUpload(
            str(path), chunksize=-1, resumable=True, mimetype="video/mp4"
        )

    request = service.videos().insert(
        part="snippet,status",
        body=_body(metadata, privacy),
        media_body=media_factory(video),
    )
    response = _run_resumable(request)
    video_id = response.get("id")
    if not video_id:
        raise MissingDataError(f"upload returned no video id: {str(response)[:200]}")
    return video_id


def _run_resumable(request) -> dict:
    """Drive a resumable request to completion, returning the final response."""
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response


def set_thumbnail(service, video_id: str, thumbnail: Path, media_factory=None) -> None:
    if not thumbnail.exists():
        raise MissingDataError(f"no thumbnail to set at {thumbnail}")
    if media_factory is None:
        from googleapiclient.http import MediaFileUpload

        media_factory = lambda path: MediaFileUpload(str(path), mimetype="image/png")
    service.thumbnails().set(
        videoId=video_id, media_body=media_factory(thumbnail)
    ).execute()


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def record_upload(run_dir: Path, video_id: str, privacy: str) -> Path:
    """Note what was published, so a rerun does not upload a second copy blindly.

    Not a lock - a determined rerun with --force can still re-upload - but a
    visible record that this run already produced a video, and which one.
    """
    path = run_dir / "final" / "published.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "video_id": video_id,
        "url": watch_url(video_id),
        "privacy": privacy,
    }, indent=2))
    return path
