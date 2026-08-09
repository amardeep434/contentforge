def test_make_uses_niche_run_dir_and_loads_config(tmp_path):
    from contentforge.cli import main
    # a minimal niche.toml under the tmp data root
    niche_dir = tmp_path / "biz"
    niche_dir.mkdir(parents=True)
    (niche_dir / "niche.toml").write_text(
        '[niche]\nname="biz"\ntitle_format="T {subject}"\n'
        '[visual]\nhouse_style="hs"\nnegative="neg"\nbg=[1,2,3]\naccent=[4,5,6]\nimage_model="qwen"\n'
        '[voice]\nreference="~/r.wav"\npace=0.8\nmusic=false\n'
        '[script]\nsystem="sys"\ntarget_words=[10,20]\n'
        '[metadata]\nsystem="msys"\n'
    )
    script = tmp_path / "s.txt"
    script.write_text("One sentence here. Two sentence here. Three here.\n")
    rc = main(["make", "smoke", "--niche", "biz", "--root", str(tmp_path),
               "--script-file", str(script), "--dry-run"])
    assert rc == 0
    # dry-run wrote the script into the niche-scoped run dir
    assert (tmp_path / "biz" / "videos" / "smoke" / "meta" / "script.txt").exists()


def _mock_scriptwriter_internals(monkeypatch, seen):
    """Fully mock the LLM/validation plumbing scriptwriter's write closure hits."""
    import contentforge.runtime as runtime

    def fake_generate_script(client, topic, sources, shape, **kw):
        seen["sources"] = sources
        seen["called"] = True
        return "SCRIPT"

    monkeypatch.setattr("contentforge.script.generate.generate_script", fake_generate_script)
    monkeypatch.setattr("contentforge.script.validate.find_violations", lambda s, sources: [])
    monkeypatch.setattr(runtime, "llm_client", lambda: object())


def test_make_dry_run_auto_detects_staged_transcript(tmp_path, monkeypatch):
    from contentforge.cli import main

    staged = (tmp_path / "biz" / "videos" / "smoke" / "meta" / "sources"
              / "reference-transcript.txt")
    staged.parent.mkdir(parents=True)
    staged.write_text("AUTO-DETECTED TRANSCRIPT")

    seen = {}
    _mock_scriptwriter_internals(monkeypatch, seen)

    rc = main(["make", "smoke", "--niche", "biz", "--root", str(tmp_path),
               "--topic", "T", "--dry-run"])
    assert rc == 0
    assert seen["sources"][0].text == "AUTO-DETECTED TRANSCRIPT"


def test_make_dry_run_uses_explicit_transcript_file(tmp_path, monkeypatch):
    from contentforge.cli import main

    transcript = tmp_path / "somewhere" / "t.txt"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("EXPLICIT TRANSCRIPT")

    seen = {}
    _mock_scriptwriter_internals(monkeypatch, seen)

    rc = main(["make", "smoke", "--niche", "biz", "--root", str(tmp_path),
               "--topic", "T", "--transcript-file", str(transcript), "--dry-run"])
    assert rc == 0
    assert seen["sources"][0].text == "EXPLICIT TRANSCRIPT"


def test_make_dry_run_script_file_wins_over_topic_generation(tmp_path, monkeypatch):
    from contentforge.cli import main

    script = tmp_path / "s.txt"
    script.write_text("One sentence here. Two sentence here. Three here.\n")

    seen = {}
    _mock_scriptwriter_internals(monkeypatch, seen)

    rc = main(["make", "smoke", "--niche", "biz", "--root", str(tmp_path),
               "--script-file", str(script), "--dry-run"])
    assert rc == 0
    assert "called" not in seen   # generate_script never invoked; hand-written script used verbatim


def test_harvest_writes_plan_and_stages_transcripts(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import contentforge.cli as cli
    from contentforge.harvest.plan import HarvestEntry
    from contentforge.errors import MissingDataError

    e1 = HarvestEntry("owning-a-laundromat", "Owning a Laundromat", "v1",
                      "https://www.youtube.com/watch?v=v1", "Owning a Laundromat")
    e2 = HarvestEntry("owning-a-car-wash", "Owning a Car Wash", "v2",
                      "https://www.youtube.com/watch?v=v2", "Owning a Car Wash")

    # Stub the YouTube/quota plumbing so nothing hits the network.
    monkeypatch.setattr(cli, "_credential", lambda profile: ("key", tmp_path / "ledger.json"))
    monkeypatch.setattr(cli, "_live_transport", lambda api_key: (lambda endpoint, params: {}))
    monkeypatch.setattr(cli, "YouTubeClient", lambda api_key, transport: object())
    monkeypatch.setattr(cli, "load_ledger", lambda path, now: SimpleNamespace(spent=0))
    monkeypatch.setattr(cli, "save_ledger", lambda path, ledger, now, started: None)
    monkeypatch.setattr(cli, "build_plan",
                         lambda client, channel, ledger, limit, on_ledger=None: ([e1, e2], ledger))

    def fake_fetch(url):
        if url.endswith("v1"):
            return "TRANSCRIPT ONE"
        raise MissingDataError("no captions for v2")
    monkeypatch.setattr(cli, "fetch_transcript", fake_fetch)

    rc = cli.main(["harvest", "somechannel", "--niche", "biz", "--root", str(tmp_path)])
    assert rc == 0

    plan = (tmp_path / "biz" / "harvest" / "somechannel" / "plan.jsonl").read_text().splitlines()
    assert len(plan) == 1 and "owning-a-laundromat" in plan[0]          # v2 dropped (no captions)
    staged = tmp_path / "biz" / "videos" / "owning-a-laundromat" / "meta" / "sources" / "reference-transcript.txt"
    assert staged.read_text() == "TRANSCRIPT ONE"
    assert not (tmp_path / "biz" / "videos" / "owning-a-car-wash").exists()


def test_harvest_persists_partial_quota_spend_when_build_plan_raises_mid_call(tmp_path, monkeypatch):
    """build_plan can raise after some of its 4 API calls already billed quota
    (e.g. MissingDataError for an empty channel, after channel_by_handle +
    get_uploads_playlists spent real units). The handler must persist that
    partial spend, not the pre-call `ledger`."""
    from types import SimpleNamespace
    import pytest
    import contentforge.cli as cli
    from contentforge.errors import MissingDataError
    from contentforge.providers.quota import QuotaLedger

    started_ledger = QuotaLedger()
    monkeypatch.setattr(cli, "_credential", lambda profile: ("key", tmp_path / "ledger.json"))
    monkeypatch.setattr(cli, "_live_transport", lambda api_key: (lambda endpoint, params: {}))
    monkeypatch.setattr(cli, "YouTubeClient", lambda api_key, transport: object())
    monkeypatch.setattr(cli, "load_ledger", lambda path, now: started_ledger)

    saved = {}
    def fake_save_ledger(path, ledger, now, started):
        saved["ledger"] = ledger
    monkeypatch.setattr(cli, "save_ledger", fake_save_ledger)

    def fake_build_plan(client, channel, ledger, limit, on_ledger=None):
        l1 = ledger.charge("channels.list")
        if on_ledger:
            on_ledger(l1)
        l2 = l1.charge("playlistItems.list")
        if on_ledger:
            on_ledger(l2)
        raise MissingDataError("no videos found for channel")
    monkeypatch.setattr(cli, "build_plan", fake_build_plan)

    with pytest.raises(MissingDataError):
        cli.main(["harvest", "somechannel", "--niche", "biz", "--root", str(tmp_path)])

    assert saved["ledger"].spent == started_ledger.spent + 1 + 1   # channels.list + playlistItems.list
    assert saved["ledger"].spent > started_ledger.spent


def test_harvest_disambiguates_slugs_against_other_channels_in_same_niche(tmp_path, monkeypatch):
    """Two different channels harvested into the same niche whose titles
    slugify identically must not collide on data/<niche>/videos/<slug>/."""
    from types import SimpleNamespace
    import contentforge.cli as cli
    from contentforge.harvest.plan import HarvestEntry, write_plan

    # chanA already has a plan claiming this slug.
    write_plan([HarvestEntry("owning-a-laundromat", "T", "v1", "http://x/v1", "T")],
               tmp_path / "biz", "chanA")

    e_b = HarvestEntry("owning-a-laundromat", "Owning a Laundromat", "v2",
                        "https://www.youtube.com/watch?v=v2", "Owning a Laundromat")

    monkeypatch.setattr(cli, "_credential", lambda profile: ("key", tmp_path / "ledger.json"))
    monkeypatch.setattr(cli, "_live_transport", lambda api_key: (lambda endpoint, params: {}))
    monkeypatch.setattr(cli, "YouTubeClient", lambda api_key, transport: object())
    monkeypatch.setattr(cli, "load_ledger", lambda path, now: SimpleNamespace(spent=0))
    monkeypatch.setattr(cli, "save_ledger", lambda path, ledger, now, started: None)
    monkeypatch.setattr(cli, "build_plan",
                         lambda client, channel, ledger, limit, on_ledger=None: ([e_b], ledger))
    monkeypatch.setattr(cli, "fetch_transcript", lambda url: "TRANSCRIPT B")

    rc = cli.main(["harvest", "chanB", "--niche", "biz", "--root", str(tmp_path)])
    assert rc == 0

    plan = (tmp_path / "biz" / "harvest" / "chanB" / "plan.jsonl").read_text()
    assert "owning-a-laundromat-2" in plan
    staged = (tmp_path / "biz" / "videos" / "owning-a-laundromat-2"
              / "meta" / "sources" / "reference-transcript.txt")
    assert staged.read_text() == "TRANSCRIPT B"
    # chanA's own staged transcript dir must be untouched
    assert not (tmp_path / "biz" / "videos" / "owning-a-laundromat"
                / "meta" / "sources" / "reference-transcript.txt").exists()


def test_harvest_make_runs_batch_over_plan_entries(tmp_path, monkeypatch):
    """Fully mocked: no GPU, no LLM. Patches run_batch itself, so this only
    proves the CLI wires load_niche/read_plan/run_batch/printing together -
    the batch-loop logic (skip/fail/interrupt) is unit-tested in
    test_harvest_batch.py, and the build_one niche=cfg wiring is exercised by
    the harvest-make smoke test (Task 6)."""
    import contentforge.cli as cli
    import contentforge.harvest.batch as batch_mod
    from contentforge.harvest.plan import write_plan, HarvestEntry

    niche_dir = tmp_path / "biz"
    niche_dir.mkdir(parents=True)
    (niche_dir / "niche.toml").write_text(
        '[niche]\nname="biz"\ntitle_format="T {subject}"\n'
        '[visual]\nhouse_style="hs"\nnegative="neg"\nbg=[1,2,3]\naccent=[4,5,6]\nimage_model="qwen"\n'
        '[voice]\nreference="~/r.wav"\npace=0.8\nmusic=false\n'
        '[script]\nsystem="sys"\ntarget_words=[10,20]\n'
        '[metadata]\nsystem="msys"\n'
    )
    entries = [HarvestEntry("s1", "T1", "v1", "http://x/v1", "T1"),
               HarvestEntry("s2", "T2", "v2", "http://x/v2", "T2")]
    write_plan(entries, niche_dir, "chan")

    seen = {}

    def fake_run_batch(entries_arg, niche, root, build_one, channel="channel", **kw):
        seen["slugs"] = [e.slug for e in entries_arg]
        return {e.slug: {"status": "done"} for e in entries_arg}

    monkeypatch.setattr(batch_mod, "run_batch", fake_run_batch)

    rc = cli.main(["harvest-make", "chan", "--niche", "biz", "--root", str(tmp_path)])
    assert rc == 0
    assert seen["slugs"] == ["s1", "s2"]


def test_harvest_then_harvest_make_end_to_end(tmp_path, monkeypatch):
    """harvest -> harvest-make, chained on one real tmp_path data root, with
    every external effect (network, YouTube API, yt-dlp, GPU, LLM) mocked.
    Proves the two commands actually interoperate on disk: harvest's staged
    transcripts + plan.jsonl are what harvest-make reads and renders."""
    from types import SimpleNamespace
    import contentforge.cli as cli
    import contentforge.pipeline as pipeline
    from contentforge import runtime
    from contentforge.harvest.plan import HarvestEntry

    # ---- Phase A: harvest -----------------------------------------------
    e1 = HarvestEntry("owning-a-laundromat", "Owning a Laundromat", "v1",
                       "https://www.youtube.com/watch?v=v1", "Owning a Laundromat")
    e2 = HarvestEntry("owning-a-car-wash", "Owning a Car Wash", "v2",
                       "https://www.youtube.com/watch?v=v2", "Owning a Car Wash")

    monkeypatch.setattr(cli, "_credential", lambda profile: ("key", tmp_path / "ledger.json"))
    monkeypatch.setattr(cli, "_live_transport", lambda api_key: (lambda endpoint, params: {}))
    monkeypatch.setattr(cli, "YouTubeClient", lambda api_key, transport: object())
    monkeypatch.setattr(cli, "load_ledger", lambda path, now: SimpleNamespace(spent=0))
    monkeypatch.setattr(cli, "save_ledger", lambda path, ledger, now, started: None)
    monkeypatch.setattr(cli, "build_plan",
                         lambda client, channel, ledger, limit, on_ledger=None: ([e1, e2], ledger))

    def fake_fetch(url):
        if url.endswith("v1"):
            return "TRANSCRIPT ONE"
        return "TRANSCRIPT TWO"
    monkeypatch.setattr(cli, "fetch_transcript", fake_fetch)

    rc = cli.main(["harvest", "chan", "--niche", "biz", "--root", str(tmp_path)])
    assert rc == 0

    plan_path = tmp_path / "biz" / "harvest" / "chan" / "plan.jsonl"
    assert plan_path.exists()
    for slug in ("owning-a-laundromat", "owning-a-car-wash"):
        staged = (tmp_path / "biz" / "videos" / slug / "meta" / "sources"
                  / "reference-transcript.txt")
        assert staged.exists()

    # ---- Phase B: harvest-make, same root, reads what harvest wrote -----
    niche_dir = tmp_path / "biz"
    niche_dir.mkdir(exist_ok=True)
    (niche_dir / "niche.toml").write_text(
        '[niche]\nname="biz"\ntitle_format="T {subject}"\n'
        '[visual]\nhouse_style="hs"\nnegative="neg"\nbg=[1,2,3]\naccent=[4,5,6]\nimage_model="qwen"\n'
        '[voice]\nreference="~/r.wav"\npace=0.8\nmusic=false\n'
        '[script]\nsystem="sys"\ntarget_words=[10,20]\n'
        '[metadata]\nsystem="msys"\n'
    )

    def fake_build_video(*, run_dir, **kwargs):
        final = run_dir / "final"
        final.mkdir(parents=True, exist_ok=True)
        video = final / "video.mp4"
        video.write_bytes(b"fake")
        return video

    monkeypatch.setattr(pipeline, "build_video", fake_build_video)
    for name in ("spec_planner", "speaker", "illustrator", "upscaler",
                 "renderer", "metadata_writer"):
        monkeypatch.setattr(runtime, name, lambda *a, **k: object())

    rc = cli.main(["harvest-make", "chan", "--niche", "biz", "--root", str(tmp_path)])
    assert rc == 0

    for slug in ("owning-a-laundromat", "owning-a-car-wash"):
        assert (tmp_path / "biz" / "videos" / slug / "final" / "video.mp4").exists()

    import json
    batch = json.loads(
        (tmp_path / "biz" / "harvest" / "chan" / "batch.json").read_text()
    )
    assert batch["owning-a-laundromat"]["status"] == "done"
    assert batch["owning-a-car-wash"]["status"] == "done"


def test_proxy_http_direct_without_proxy(monkeypatch):
    import httplib2
    from contentforge.cli import _proxy_http
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(v, raising=False)
    assert isinstance(_proxy_http(), httplib2.Http)


def test_proxy_http_parses_authenticated_proxy(monkeypatch):
    import socks
    from contentforge.cli import _proxy_http
    monkeypatch.setenv("HTTPS_PROXY", "http://scraper:secret@scrape-proxy:3128")
    pi = _proxy_http().proxy_info
    assert pi is not None
    assert pi.proxy_host == "scrape-proxy"
    assert pi.proxy_port == 3128
    assert pi.proxy_user == "scraper"
    assert pi.proxy_pass == "secret"
    assert pi.proxy_type == socks.PROXY_TYPE_HTTP


def test_proxy_http_unauthenticated_proxy(monkeypatch):
    from contentforge.cli import _proxy_http
    monkeypatch.setenv("HTTPS_PROXY", "http://myproxy:8080")
    pi = _proxy_http().proxy_info
    assert pi.proxy_host == "myproxy"
    assert pi.proxy_port == 8080
    assert pi.proxy_user is None
