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
    monkeypatch.setattr("contentforge.script.validate.validate_script", lambda s, sources: None)
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
    monkeypatch.setattr(cli, "build_plan", lambda client, channel, ledger, limit: ([e1, e2], ledger))

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
