"""Decide what a measurement means, and say why.

This module is deliberately pure: measurements in, verdicts out, no network, no
files, no clock. That is the whole point of splitting it from resolution.
Criteria have already changed four times in this project - mean, then median,
then hit-rate, then reachability - and each change previously forced a full
rescan at ~2 quota units per channel. Judging stored measurements instead means
re-deciding costs nothing.

Every verdict carries the ruleset that produced it, so a potentials file written
under old criteria is recognisable rather than silently mixed in.
"""

from dataclasses import dataclass

#: Bump whenever a threshold below changes. Rows judged under an older version
#: can then be re-analysed rather than trusted.
CRITERIA_VERSION = "2026-07-30.2"

#: A channel needs enough videos before a median means anything. Three separate
#: conclusions in this project died from being read off n=4 (C-004/C-007/C-014).
MIN_VIDEOS = 8

#: mean/median. Above this the average is measuring one or two viral hits rather
#: than the channel's typical output (C-001).
MAX_SKEW = 3.0

#: Median views the channel must clear to be a viable model at all.
MIN_MEDIAN_VIEWS = 10_000

#: Views per subscriber. This is the load-bearing test, and it replaced an
#: absolute hit-rate threshold that was quietly measuring channel *size*:
#: "40% of videos above 100,000 views" rejected 95 of 176 channels, including
#: every small consistent one worth learning from. A channel pulling several
#: times its subscriber count is being served beyond its own audience, which is
#: the only way a new channel grows. The giants score 0.1-0.5 here; the small
#: consistent ones score 3-7.
MIN_VIEWS_PER_SUB = 1.0

#: Retained for reporting, no longer a gate.
HIT_THRESHOLD_VIEWS = 100_000

#: Above this, a channel's views come partly from its existing base and standing,
#: so its numbers say nothing about a channel starting from zero. Inferring from
#: large channels is the error C-007 was withdrawn for.
REACHABLE_MAX_SUBS = 150_000

#: Mirrors research.authorship.PERSONAL. Duplicated rather than imported to keep
#: this module free of dependencies - it must stay pure.
PERSONAL = "personal"
NETWORK = "network"

EXEMPLAR = "exemplar"
WATCH = "watch"
REJECT = "reject"


@dataclass(frozen=True)
class Verdict:
    channel_id: str
    status: str
    reason: str
    criteria_version: str = CRITERIA_VERSION


def judge(measurement: dict) -> Verdict:  # noqa: C901
    """One channel's verdict, with the reason stated in the measurement's terms.

    Order matters: the first failing test is the one reported, so the reason is
    the most fundamental problem rather than an arbitrary one.
    """
    channel_id = measurement["channel_id"]
    n = int(measurement["n"])
    skew = float(measurement["skew"])
    hit_rate = float(measurement["hit_rate"])
    subs = int(measurement["subs"])
    median = int(measurement["median"])

    def verdict(status: str, reason: str) -> Verdict:
        return Verdict(channel_id, status, reason, CRITERIA_VERSION)

    if n < MIN_VIDEOS:
        return verdict(REJECT, f"only {n} long-form videos; need {MIN_VIDEOS} to judge")
    if skew > MAX_SKEW:
        return verdict(
            REJECT,
            f"lottery-shaped: mean is {skew:.1f}x the median, above {MAX_SKEW}",
        )
    if median < MIN_MEDIAN_VIEWS:
        return verdict(
            REJECT,
            f"median {median:,} views is below {MIN_MEDIAN_VIEWS:,} - too small to "
            "be a viable model",
        )
    views_per_sub = median / max(subs, 1)
    if views_per_sub < MIN_VIEWS_PER_SUB:
        return verdict(
            REJECT,
            f"{views_per_sub:.1f} views per subscriber - it is not being served "
            "beyond its own audience, which is the only way a new channel grows",
        )
    if subs > REACHABLE_MAX_SUBS:
        return verdict(
            WATCH,
            f"repeatable, but {subs:,} subs is above {REACHABLE_MAX_SUBS:,} - its "
            "numbers cannot be extrapolated to a new channel",
        )
    # A person narrating their own expertise, with an audience already assembled
    # elsewhere, is not a template a pipeline can follow. This project picked a
    # niche around exactly such a channel before checking (C-048).
    operator = measurement.get("operator")
    if operator in (PERSONAL, NETWORK):
        what = "a personal brand" if operator == PERSONAL else "a team or network"
        return verdict(
            WATCH,
            f"consistent and reachable, but it is {what} rather than a faceless "
            f"operation ({measurement.get('operator_evidence', 'see check')}) - its "
            "numbers may rest on the operator, not the format",
        )
    return verdict(
        EXEMPLAR,
        f"consistent and reachable: {subs:,} subs, median {median:,}, "
        f"{views_per_sub:.1f} views per subscriber, skew {skew:.1f}",
    )


def judge_all(measurements: list[dict]) -> list[Verdict]:
    return [judge(measurement) for measurement in measurements]


def tally(verdicts: list[Verdict]) -> dict[str, int]:
    counts = {EXEMPLAR: 0, WATCH: 0, REJECT: 0}
    for verdict in verdicts:
        counts[verdict.status] = counts.get(verdict.status, 0) + 1
    return counts
