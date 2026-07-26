"""Research report output.

Two artifacts: report.json for downstream plans, report.md for the human gate.
Every number in both carries its source URL inline, so the report can be
audited without re-running anything.
"""

import json
from datetime import datetime
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.research.score import NicheScore


def _fact_json(fact: Fact) -> dict:
    return {
        "value": fact.value,
        "source_url": fact.provenance.source_url,
        "response_id": fact.provenance.response_id,
        "retrieved_at": fact.provenance.retrieved_at.isoformat(),
    }


def write_report(
    scores: list[NicheScore], out_dir: Path, generated_at: datetime
) -> tuple[Path, Path]:
    if not scores:
        raise MissingDataError("refusing to write an empty research report")

    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": generated_at.isoformat(),
        "niches": [
            {
                "niche": score.niche,
                "geography": score.geography,
                "score": score.score,
                "rpm_usd": _fact_json(score.rpm_usd),
                "metrics": {
                    "competitor_count": _fact_json(score.metrics.competitor_count),
                    "median_views_per_day": _fact_json(
                        score.metrics.median_views_per_day
                    ),
                    "entrability": _fact_json(score.metrics.entrability),
                },
            }
            for score in scores
        ],
    }
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(payload, indent=2))

    lines = [
        f"# Niche research — {generated_at.date().isoformat()}",
        "",
        "Every figure links to the response it came from. If a number has no "
        "link, it did not come from this pipeline.",
        "",
    ]
    for position, score in enumerate(scores, start=1):
        metrics = score.metrics
        lines += [
            f"## {position}. {score.niche} ({score.geography}) — score {score.score:.2f}",
            "",
            f"- RPM (USD): {score.rpm_usd.value:.2f} "
            f"— [source]({score.rpm_usd.provenance.source_url})",
            f"- Competitors ≥10k subs: {metrics.competitor_count.value} "
            f"— [source]({metrics.competitor_count.provenance.source_url})",
            f"- Median views/day: {metrics.median_views_per_day.value:.1f} "
            f"— [source]({metrics.median_views_per_day.provenance.source_url})",
            f"- Entrability: {metrics.entrability.value:.2f} "
            f"— [source]({metrics.entrability.provenance.source_url})",
            "",
        ]
    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(lines))

    return json_path, md_path
