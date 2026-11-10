"""The pull-request stage model: where elapsed time actually goes.

A pull request's life is cut into consecutive stages. Each stage is bounded by
two timestamps, and is only counted when both exist -- a missing boundary means
"not observed", never zero. That distinction is what keeps medians honest.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.models import Deployment, PullRequest
from app.services.stats import percentile

# Ordered so the UI can lay stages out left to right along a real timeline.
STAGE_ORDER: tuple[str, ...] = ("code", "pickup", "review", "rework", "release")

STAGE_LABELS: dict[str, str] = {
    "code": "Coding",
    "pickup": "Waiting for review",
    "review": "In review",
    "rework": "Approved, not merged",
    "release": "Merged, not shipped",
}

STAGE_DESCRIPTIONS: dict[str, str] = {
    "code": "First commit until the pull request is opened for review.",
    "pickup": "Open and waiting for a reviewer to look at it for the first time.",
    "review": "First review until the change is approved.",
    "rework": "Approved and sitting in the merge queue.",
    "release": "Merged and waiting for a production deployment.",
}

# Stages where nobody is working -- the change is queued. These are the ones
# worth attacking first, because removing the wait costs no engineering effort.
QUEUE_STAGES: frozenset[str] = frozenset({"pickup", "rework", "release"})

# Hours above which a stage is treated as a bottleneck candidate. Derived from
# the DORA "elite" lead-time target of under one day end to end, split across
# the pipeline rather than applied to any single stage.
STAGE_THRESHOLD_HOURS: dict[str, float] = {
    "code": 48.0,
    "pickup": 4.0,
    "review": 12.0,
    "rework": 2.0,
    "release": 8.0,
}


@dataclass(slots=True)
class StageSample:
    """One measured stage duration for one pull request."""

    stage: str
    seconds: float
    pull_request_id: int
    pull_request_number: int


@dataclass(slots=True)
class StageSummary:
    stage: str
    label: str
    description: str
    is_queue: bool
    sample_count: int
    p50_seconds: float | None
    p75_seconds: float | None
    p90_seconds: float | None
    total_seconds: float
    # Share of the summed p50 pipeline this stage accounts for, 0-1.
    share_of_pipeline: float = 0.0


def _delta(start: datetime | None, end: datetime | None) -> float | None:
    """Seconds between two boundaries, or None if either is missing or inverted."""
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    # Clock skew and backdated events do occur; a negative stage is unusable.
    return seconds if seconds >= 0 else None


def stage_durations(
    pr: PullRequest, deployment: Deployment | None = None
) -> dict[str, float]:
    """Measured stage durations in seconds for one pull request.

    Stages with a missing boundary are absent from the result rather than zero.
    """
    # A draft PR becomes reviewable only when marked ready, so that is the real
    # start of the review clock. Non-draft PRs start it when opened.
    review_clock_start = pr.ready_for_review_at or pr.opened_at

    candidates: dict[str, float | None] = {
        "code": _delta(pr.first_commit_at, pr.opened_at),
        "pickup": _delta(review_clock_start, pr.first_review_at),
        "review": _delta(pr.first_review_at, pr.approved_at),
        "rework": _delta(pr.approved_at, pr.merged_at),
        "release": _delta(pr.merged_at, deployment.finished_at if deployment else None),
    }
    return {stage: value for stage, value in candidates.items() if value is not None}


def collect_samples(
    pairs: Iterable[tuple[PullRequest, Deployment | None]],
) -> list[StageSample]:
    samples: list[StageSample] = []
    for pr, deployment in pairs:
        for stage, seconds in stage_durations(pr, deployment).items():
            samples.append(
                StageSample(
                    stage=stage,
                    seconds=seconds,
                    pull_request_id=pr.id,
                    pull_request_number=pr.number,
                )
            )
    return samples


def summarize(samples: Sequence[StageSample]) -> list[StageSummary]:
    """Percentile summary per stage, in pipeline order."""
    by_stage: dict[str, list[float]] = {stage: [] for stage in STAGE_ORDER}
    for sample in samples:
        if sample.stage in by_stage:
            by_stage[sample.stage].append(sample.seconds)

    summaries = [
        StageSummary(
            stage=stage,
            label=STAGE_LABELS[stage],
            description=STAGE_DESCRIPTIONS[stage],
            is_queue=stage in QUEUE_STAGES,
            sample_count=len(values),
            p50_seconds=percentile(values, 50),
            p75_seconds=percentile(values, 75),
            p90_seconds=percentile(values, 90),
            total_seconds=sum(values),
        )
        for stage, values in ((s, by_stage[s]) for s in STAGE_ORDER)
    ]

    pipeline_p50 = sum(s.p50_seconds or 0.0 for s in summaries)
    if pipeline_p50 > 0:
        for summary in summaries:
            summary.share_of_pipeline = (summary.p50_seconds or 0.0) / pipeline_p50

    return summaries


@dataclass(slots=True)
class Bottleneck:
    stage: str
    label: str
    severity: str  # "critical" | "elevated" | "healthy"
    p50_seconds: float
    p90_seconds: float
    threshold_seconds: float
    # How many times over the threshold the median sits.
    overage: float
    is_queue: bool
    sample_count: int
    share_of_pipeline: float
    evidence_pr_numbers: list[int] = field(default_factory=list)


def detect_bottlenecks(
    summaries: Sequence[StageSummary], samples: Sequence[StageSample], evidence_limit: int = 3
) -> list[Bottleneck]:
    """Rank stages that exceed their threshold, worst first.

    Queue stages are ranked ahead of equally-overrun work stages: waiting is
    cheaper to remove than engineering effort, so it is the better first move.
    """
    worst_by_stage: dict[str, list[StageSample]] = {}
    for sample in samples:
        worst_by_stage.setdefault(sample.stage, []).append(sample)

    bottlenecks: list[Bottleneck] = []
    for summary in summaries:
        if summary.p50_seconds is None or summary.sample_count == 0:
            continue

        threshold = STAGE_THRESHOLD_HOURS[summary.stage] * 3600
        overage = summary.p50_seconds / threshold
        if overage < 1.0:
            severity = "healthy"
        elif overage < 2.0:
            severity = "elevated"
        else:
            severity = "critical"

        if severity == "healthy":
            continue

        evidence = sorted(
            worst_by_stage.get(summary.stage, []), key=lambda s: s.seconds, reverse=True
        )[:evidence_limit]

        bottlenecks.append(
            Bottleneck(
                stage=summary.stage,
                label=summary.label,
                severity=severity,
                p50_seconds=summary.p50_seconds,
                p90_seconds=summary.p90_seconds or summary.p50_seconds,
                threshold_seconds=threshold,
                overage=overage,
                is_queue=summary.stage in QUEUE_STAGES,
                sample_count=summary.sample_count,
                share_of_pipeline=summary.share_of_pipeline,
                evidence_pr_numbers=[s.pull_request_number for s in evidence],
            )
        )

    bottlenecks.sort(key=lambda b: (b.is_queue, b.overage), reverse=True)
    return bottlenecks
