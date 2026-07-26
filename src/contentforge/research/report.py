"""Research report output.

report.json is the machine-readable artifact and keeps every full source URL.
report.md is for the human gate and cites response etags instead, linking to
raw/<etag>.json — revision 1 inlined all fifty channel ids in every citation
and produced ~3,000-character links that made the report unreadable.
"""

import json
from datetime import datetime
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.research.changes import summarise_changes
from contentforge.research.score import NicheScore

MAX_CHANGE_EXAMPLES = 10


def _fact_json(fact: Fact) -> dict:
    return {
        "value": fact.value,
        "source_url": fact.provenance.source_url,
        "response_id": fact.provenance.response_id,
        "retrieved_at": fact.provenance.retrieved_at.isoformat(),
    }


def _score_json(score: NicheScore) -> dict:
    return {
        "niche": score.niche,
        "geography": score.geography,
        "score": score.score,
        "rpm_usd": _fact_json(score.rpm_usd),
        "sampled_channels": score.sampled_channels,
        "breakout_count": score.breakout_count,
        "breakout_rate": score.breakout_rate,
        "median_lift": score.median_lift,
        "membership_factor": score.membership_factor,
    }


def _ranking_table(scores: list[NicheScore]) -> list[str]:
    lines = [
        "| # | niche | geo | score | RPM $ | channels | breakouts | rate | median lift |",
        "|---|-------|-----|-------|-------|----------|-----------|------|-------------|",
    ]
    for position, score in enumerate(scores, start=1):
        lines.append(
            f"| {position} | {score.niche} | {score.geography} | {score.score:.2f} | "
            f"{score.rpm_usd.value:.2f} | {score.sampled_channels} | "
            f"{score.breakout_count} | {score.breakout_rate:.2f} | "
            f"{score.median_lift:.1f} |"
        )
    return lines


def _change_section(niche: str, profiles: list) -> list[str]:
    """Aggregate first, then a few examples.

    Per-channel lines alone were unreadable noise in the first live run: a
    single channel shortening its videos means nothing. The counts below are
    where a consistent direction would actually show up.
    """
    summary = summarise_changes(profiles)
    if summary is None:
        return []

    lines = [
        f"## What changed at breakout — {niche}",
        "",
        f"Across {summary.channels} breakout channels:",
        "",
        f"- **Duration:** {summary.duration_shorter} shorter, "
        f"{summary.duration_longer} longer, {summary.duration_unchanged} unchanged "
        f"(median ratio {summary.median_duration_ratio:.2f}×)",
        f"- **Cadence:** {summary.cadence_faster} faster, "
        f"{summary.cadence_slower} slower, {summary.cadence_unchanged} unchanged",
        f"- **Title length:** median {summary.median_title_word_delta:+.1f} words",
        "",
        "<details><summary>Per-channel detail</summary>",
        "",
    ]
    for profile in profiles[:MAX_CHANGE_EXAMPLES]:
        lines.append(
            f"- duration {profile.duration_before}s → {profile.duration_after}s; "
            f"cadence {profile.cadence_days_before:.1f}d → "
            f"{profile.cadence_days_after:.1f}d; "
            f"title {profile.title_words_before:.0f} → "
            f"{profile.title_words_after:.0f} words"
        )
    lines += [
        "",
        "</details>",
        "",
        "_These changes coincided with the inflection. Retention, traffic source "
        "and thumbnail click-through are not available for other channels, so "
        "this is association, not cause._",
        "",
    ]
    return lines


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
        "niches": [_score_json(score) for score in scores],
    }
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(payload, indent=2))

    lines = [
        f"# Niche research — {generated_at.date().isoformat()}",
        "",
        "Figures cite the API response etag; raw bodies are in `raw/`.",
        "",
    ]
    lines += _ranking_table(scores)
    lines += ["", f"RPM source etag: `{scores[0].rpm_usd.provenance.response_id}`", ""]

    for score in scores:
        profiles = change_profiles.get(score.niche) or []
        if profiles:
            lines += _change_section(score.niche, profiles)

    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(lines))
    return json_path, md_path
