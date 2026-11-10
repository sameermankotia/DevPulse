"""The four DORA metrics, computed from the ingested delivery dataset.

Definitions follow the DORA research program:
  - Deployment frequency: successful production deployments per day.
  - Lead time for changes: first commit to production deploy.
  - Change failure rate: share of deployments that caused a failure.
  - Time to restore: incident opened to incident resolved.

Performance bands come from the published DORA cutoffs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.models import Deployment, DeploymentStatus, Incident, PullRequest
from app.services.stats import median, percentile, trend_ratio

DAY = 86400.0

Band = str  # "elite" | "high" | "medium" | "low"


@dataclass(slots=True)
class MetricPoint:
    at: date
    value: float


@dataclass(slots=True)
class Metric:
    key: str
    label: str
    unit: str
    value: float | None
    band: Band | None
    # Signed fractional change against the preceding window of equal length.
    trend: float | None
    # True when a rising value is a good thing (deployment frequency only).
    higher_is_better: bool
    sample_count: int
    series: list[MetricPoint]


def _band_deployment_frequency(per_day: float) -> Band:
    if per_day >= 1:
        return "elite"
    if per_day >= 1 / 7:
        return "high"
    if per_day >= 1 / 30:
        return "medium"
    return "low"


def _band_lead_time(seconds: float) -> Band:
    if seconds < DAY:
        return "elite"
    if seconds < 7 * DAY:
        return "high"
    if seconds < 30 * DAY:
        return "medium"
    return "low"


def _band_change_failure_rate(rate: float) -> Band:
    if rate <= 0.05:
        return "elite"
    if rate <= 0.10:
        return "high"
    if rate <= 0.15:
        return "medium"
    return "low"


def _band_restore_time(seconds: float) -> Band:
    if seconds < 3600:
        return "elite"
    if seconds < DAY:
        return "high"
    if seconds < 7 * DAY:
        return "medium"
    return "low"


def _daily_counts(moments: Sequence[datetime]) -> list[MetricPoint]:
    buckets: dict[date, int] = defaultdict(int)
    for moment in moments:
        buckets[moment.date()] += 1
    return [MetricPoint(at=day, value=float(count)) for day, count in sorted(buckets.items())]


def _daily_medians(pairs: Sequence[tuple[datetime, float]]) -> list[MetricPoint]:
    buckets: dict[date, list[float]] = defaultdict(list)
    for moment, value in pairs:
        buckets[moment.date()].append(value)
    return [
        MetricPoint(at=day, value=median(values) or 0.0) for day, values in sorted(buckets.items())
    ]


def _successful(deployments: Sequence[Deployment]) -> list[Deployment]:
    return [
        d
        for d in deployments
        if d.status == DeploymentStatus.SUCCESS and d.finished_at is not None
    ]


def deployment_frequency(
    deployments: Sequence[Deployment], window_days: int, previous: Sequence[Deployment]
) -> Metric:
    shipped = _successful(deployments)
    per_day = len(shipped) / window_days if window_days else 0.0
    prior_rate = len(_successful(previous)) / window_days if window_days else 0.0

    return Metric(
        key="deployment_frequency",
        label="Deployment frequency",
        unit="per_day",
        value=per_day,
        band=_band_deployment_frequency(per_day),
        trend=trend_ratio(per_day, prior_rate),
        higher_is_better=True,
        sample_count=len(shipped),
        series=_daily_counts([d.finished_at for d in shipped if d.finished_at]),
    )


def lead_time_for_changes(
    pairs: Sequence[tuple[PullRequest, Deployment]],
    previous_pairs: Sequence[tuple[PullRequest, Deployment]],
) -> Metric:
    """Median seconds from a change's first commit to its production deploy."""

    def durations(items: Sequence[tuple[PullRequest, Deployment]]) -> list[tuple[datetime, float]]:
        out: list[tuple[datetime, float]] = []
        for pr, deployment in items:
            start = pr.first_commit_at or pr.opened_at
            if deployment.finished_at is None:
                continue
            seconds = (deployment.finished_at - start).total_seconds()
            if seconds >= 0:
                out.append((deployment.finished_at, seconds))
        return out

    current = durations(pairs)
    prior = durations(previous_pairs)
    value = median([d for _, d in current])

    return Metric(
        key="lead_time",
        label="Lead time for changes",
        unit="seconds",
        value=value,
        band=_band_lead_time(value) if value is not None else None,
        trend=trend_ratio(value, median([d for _, d in prior])),
        higher_is_better=False,
        sample_count=len(current),
        series=_daily_medians(current),
    )


def change_failure_rate(
    deployments: Sequence[Deployment],
    incidents: Sequence[Incident],
    previous_deployments: Sequence[Deployment],
    previous_incidents: Sequence[Incident],
) -> Metric:
    shipped = _successful(deployments)

    def rate(deploys: Sequence[Deployment], failures: Sequence[Incident]) -> float | None:
        return len(failures) / len(deploys) if deploys else None

    value = rate(shipped, incidents)
    prior = rate(_successful(previous_deployments), previous_incidents)

    # Daily rate: failures that day over deployments that day.
    deploys_by_day: dict[date, int] = defaultdict(int)
    for d in shipped:
        if d.finished_at:
            deploys_by_day[d.finished_at.date()] += 1
    failures_by_day: dict[date, int] = defaultdict(int)
    for incident in incidents:
        failures_by_day[incident.opened_at.date()] += 1

    series = [
        MetricPoint(at=day, value=failures_by_day.get(day, 0) / count)
        for day, count in sorted(deploys_by_day.items())
        if count
    ]

    return Metric(
        key="change_failure_rate",
        label="Change failure rate",
        unit="ratio",
        value=value,
        band=_band_change_failure_rate(value) if value is not None else None,
        trend=trend_ratio(value, prior),
        higher_is_better=False,
        sample_count=len(shipped),
        series=series,
    )


def time_to_restore(
    incidents: Sequence[Incident], previous_incidents: Sequence[Incident]
) -> Metric:
    def recoveries(items: Sequence[Incident]) -> list[tuple[datetime, float]]:
        return [
            (i.resolved_at, i.recovery_seconds)
            for i in items
            if i.resolved_at is not None and i.recovery_seconds is not None
        ]

    current = recoveries(incidents)
    value = median([v for _, v in current])

    return Metric(
        key="time_to_restore",
        label="Time to restore service",
        unit="seconds",
        value=value,
        band=_band_restore_time(value) if value is not None else None,
        trend=trend_ratio(value, median([v for _, v in recoveries(previous_incidents)])),
        higher_is_better=False,
        sample_count=len(current),
        series=_daily_medians(current),
    )


@dataclass(slots=True)
class CiHealth:
    """Continuous integration signal that sits underneath the DORA numbers."""

    median_duration_seconds: float | None
    p90_duration_seconds: float | None
    success_rate: float | None
    # Share of PRs whose CI passed only after an earlier attempt failed.
    flake_rate: float | None
    total_runs: int


def ci_health(runs: Sequence) -> CiHealth:
    finished = [r for r in runs if r.completed_at is not None]
    durations = [
        d for d in (r.duration_seconds for r in finished) if d is not None and d >= 0
    ]
    conclusive = [r for r in finished if r.conclusion is not None]
    successes = [r for r in conclusive if r.conclusion.value == "success"]

    # A retried run that eventually succeeds is the clearest flake signal available
    # without parsing logs.
    retried_successes = [r for r in successes if r.run_attempt > 1]

    return CiHealth(
        median_duration_seconds=median(durations),
        p90_duration_seconds=percentile(durations, 90),
        success_rate=len(successes) / len(conclusive) if conclusive else None,
        flake_rate=len(retried_successes) / len(successes) if successes else None,
        total_runs=len(finished),
    )


def window_bounds(now: datetime, window_days: int) -> tuple[datetime, datetime, datetime]:
    """Returns (previous_start, current_start, now) for trend comparison."""
    current_start = now - timedelta(days=window_days)
    previous_start = current_start - timedelta(days=window_days)
    return previous_start, current_start, now
