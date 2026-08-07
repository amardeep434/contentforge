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
