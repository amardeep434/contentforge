# Publishing to YouTube

`pipeline publish` uploads a finished video. This page sets up the one-time
Google authorisation it needs. Written for someone who has never touched the
Google Cloud Console.

**Publishing is deliberately separate from making.** `pipeline make` produces the
mp4 and stops. You run `pipeline publish` yourself, it shows you the title and
tags and asks before uploading, and it defaults to **private** — the video
appears only in your own YouTube dashboard until you change it. Nothing goes
public by accident.

---

## 1. Why this needs more than an API key

Reading YouTube data (what the research side does) uses an API key. **Uploading a
video does not** — it changes your channel, so Google requires OAuth: you sign in
once in a browser and approve the app. This is on purpose, and it is why the
scraping key and the publishing credential are never the same thing.

---

## 2. Create an OAuth client (one time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create
   a project (or reuse the one your `YOUTUBE_API_KEY` is in).
2. **Enable the YouTube Data API v3**: APIs & Services → Library → search
   "YouTube Data API v3" → Enable.
3. **Configure the consent screen**: APIs & Services → OAuth consent screen →
   External → fill the app name and your email. Add yourself under **Test users**
   — while the app is in "testing" only test users can authorise it, which is
   exactly what you want.
4. **Create the credential**: APIs & Services → Credentials → Create Credentials
   → OAuth client ID → **Desktop app**. Download the JSON.
5. Save it where the pipeline looks by default:

   ```bash
   mkdir -p ~/.config/contentforge
   mv ~/Downloads/client_secret_*.json ~/.config/contentforge/youtube_client_secret.json
   ```

That file is a secret. It is already outside the repo; never commit it.

---

## 3. Install the publish dependencies

```bash
cd ~/Projects/contentforge
.venv/bin/pip install -e '.[publish]'
```

This adds only the Google OAuth libraries. Research and rendering do not need
them.

---

## 4. Publish

```bash
pipeline publish my-video
```

The first time, it opens a browser for you to sign in and approve. After that
the token is cached in `~/.config/contentforge/youtube_token.json` and refreshed
automatically — you will not sign in again.

It then prints what it is about to do and waits:

```
  title:    Why your ceiling fan is quietly wasting money
  privacy:  private
  tags:     ceiling fans, cooling, energy, ...
  video:    data/videos/my-video/video.mp4
  thumb:    data/videos/my-video/thumbnail.png

  upload to YouTube as private? [y/N]
```

Answer `y` and it uploads the video, sets the thumbnail, and prints the watch
URL. The video is private — open it in YouTube Studio to review, then flip it to
public there when you are happy.

### Options

```bash
pipeline publish my-video --privacy unlisted     # anyone with the link
pipeline publish my-video --headline "STOP DOING THIS"   # override thumbnail text
pipeline publish my-video --yes                  # skip the prompt (unattended)
```

`--privacy public` exists, but consider uploading private first and promoting it
in Studio once reviewed — an upload cannot be un-published, only deleted.

---

## 5. What it records

After a successful upload the run directory gets `final/published.json`:

```json
{ "video_id": "…", "url": "https://www.youtube.com/watch?v=…", "privacy": "private" }
```

That is a record, not a lock. Running `publish` again uploads a **second copy** —
YouTube has no idea it is the same video. Check for `final/published.json`
before re-publishing.

---

## 6. Quota

A single `videos.insert` costs **1600** units of the 10,000/day default quota, so
about six uploads a day before you would need a quota increase. Reading quota is
tracked separately by the research side; publishing quota is not, because six
videos a day is far more than this pipeline is meant to make.
