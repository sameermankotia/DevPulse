"""Composes the stage model and DORA metrics from the database for one window."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Deployment,
    DeploymentStatus,
    Incident,
    PullRequest,
    Repository,
    WorkflowRun,
)
from app.services import dora, stages
from app.services.stats import median


@dataclass(slots=True)
class DeliverySnapshot:
    repository: Repository
    window_days: int
    window_start: datetime
    window_end: datetime
    metrics: list[dora.Metric]
    stage_summaries: list[stages.StageSummary]
    bottlenecks: list[stages.Bottleneck]
    ci: dora.CiHealth
    pull_request_count: int
    contributor_count: int
    median_pr_size: float | None
    # The merged PRs in-window, newest first, for the detail table.
    recent_pull_requests: list[tuple[PullRequest, Deployment | None]]


async def get_repository(session: AsyncSession, repo_id: int) -> Repository | None:
    return await session.get(Repository, repo_id)


async def list_repositories(session: AsyncSession) -> Sequence[Repository]:
    return (await session.scalars(select(Repository).order_by(Repository.full_name))).all()


async def _deployment_by_pr(
    session: AsyncSession, repo_id: int
) -> dict[int, Deployment]:
    """First successful production deploy per pull request."""
    rows = (
        await session.scalars(
            select(Deployment)
            .where(
                Deployment.repository_id == repo_id,
                Deployment.status == DeploymentStatus.SUCCESS,
                Deployment.finished_at.isnot(None),
                Deployment.pull_request_id.isnot(None),
            )
            .order_by(Deployment.finished_at)
        )
    ).all()

    out: dict[int, Deployment] = {}
    for deployment in rows:
        assert deployment.pull_request_id is not None
        out.setdefault(deployment.pull_request_id, deployment)
    return out


async def build_snapshot(
    session: AsyncSession, repo: Repository, window_days: int = 30, now: datetime | None = None
) -> DeliverySnapshot:
    now = now or datetime.now(UTC)
    previous_start, current_start, window_end = dora.window_bounds(now, window_days)

    deploy_by_pr = await _deployment_by_pr(session, repo.id)

    # Pull requests touched in the full two-window span, so trends have a baseline.
    prs = (
        await session.scalars(
            select(PullRequest)
            .where(
                PullRequest.repository_id == repo.id,
                PullRequest.opened_at >= previous_start,
            )
            .options(selectinload(PullRequest.reviews))
            .order_by(PullRequest.opened_at.desc())
        )
    ).all()

    def in_window(pr: PullRequest, start: datetime, end: datetime) -> bool:
        anchor = pr.merged_at or pr.opened_at
        return start <= anchor < end

    current_prs = [pr for pr in prs if in_window(pr, current_start, window_end)]
    previous_prs = [pr for pr in prs if in_window(pr, previous_start, current_start)]

    def pair(items: Sequence[PullRequest]) -> list[tuple[PullRequest, Deployment | None]]:
        return [(pr, deploy_by_pr.get(pr.id)) for pr in items]

    deployments = (
        await session.scalars(
            select(Deployment).where(
                Deployment.repository_id == repo.id,
                Deployment.environment == "production",
                Deployment.finished_at >= previous_start,
            )
        )
    ).all()
    current_deploys = [
        d for d in deployments if d.finished_at and d.finished_at >= current_start
    ]
    previous_deploys = [
        d for d in deployments if d.finished_at and d.finished_at < current_start
    ]

    incidents = (
        await session.scalars(
            select(Incident).where(
                Incident.repository_id == repo.id, Incident.opened_at >= previous_start
            )
        )
    ).all()
    current_incidents = [i for i in incidents if i.opened_at >= current_start]
    previous_incidents = [i for i in incidents if i.opened_at < current_start]

    runs = (
        await session.scalars(
            select(WorkflowRun).where(
                WorkflowRun.repository_id == repo.id, WorkflowRun.started_at >= current_start
            )
        )
    ).all()

    # Lead time needs PR/deploy pairs where the deploy actually happened.
    def shipped(items: Sequence[PullRequest]) -> list[tuple[PullRequest, Deployment]]:
        return [(pr, deploy_by_pr[pr.id]) for pr in items if pr.id in deploy_by_pr]

    metrics = [
        dora.deployment_frequency(current_deploys, window_days, previous_deploys),
        dora.lead_time_for_changes(shipped(current_prs), shipped(previous_prs)),
        dora.change_failure_rate(
            current_deploys, current_incidents, previous_deploys, previous_incidents
        ),
        dora.time_to_restore(current_incidents, previous_incidents),
    ]

    samples = stages.collect_samples(pair(current_prs))
    summaries = stages.summarize(samples)

    merged = [pr for pr in current_prs if pr.merged_at is not None]
    sizes = [float(pr.size) for pr in merged]

    return DeliverySnapshot(
        repository=repo,
        window_days=window_days,
        window_start=current_start,
        window_end=window_end,
        metrics=metrics,
        stage_summaries=summaries,
        bottlenecks=stages.detect_bottlenecks(summaries, samples),
        ci=dora.ci_health(runs),
        pull_request_count=len(current_prs),
        contributor_count=len({pr.author for pr in current_prs}),
        median_pr_size=median(sizes),
        recent_pull_requests=pair(current_prs[:50]),
    )


async def ensure_window(window_days: int) -> int:
    """Clamp an arbitrary window to something the dataset can support."""
    return max(7, min(window_days, 180))


def digest_for_llm(snapshot: DeliverySnapshot) -> dict:
    """Compact, numeric-only view of a snapshot for the recommendation prompt.

    Deliberately excludes PR titles and author names: the model needs the shape
    of the delays, not the identity of the people behind them.
    """
    def hours(seconds: float | None) -> float | None:
        return round(seconds / 3600, 2) if seconds is not None else None

    return {
        "window_days": snapshot.window_days,
        "pull_requests": snapshot.pull_request_count,
        "contributors": snapshot.contributor_count,
        "median_pr_size_lines": snapshot.median_pr_size,
        # Durations are converted to hours here: a model asked to reason about
        # "716525" writes it back into its prose verbatim.
        "dora": {
            m.key: {
                "value": hours(m.value) if m.unit == "seconds" else (
                    round(m.value, 4) if m.value is not None else None
                ),
                "unit": "hours" if m.unit == "seconds" else m.unit,
                "band": m.band,
                "trend_fraction": round(m.trend, 4) if m.trend is not None else None,
                "samples": m.sample_count,
            }
            for m in snapshot.metrics
        },
        "stages": [
            {
                "stage": s.stage,
                "label": s.label,
                "is_queue": s.is_queue,
                "p50_hours": hours(s.p50_seconds),
                "p90_hours": hours(s.p90_seconds),
                "share_of_pipeline": round(s.share_of_pipeline, 4),
                "samples": s.sample_count,
            }
            for s in snapshot.stage_summaries
        ],
        "bottlenecks": [
            {
                "stage": b.stage,
                "severity": b.severity,
                "p50_hours": hours(b.p50_seconds),
                "threshold_hours": hours(b.threshold_seconds),
                "times_over_threshold": round(b.overage, 2),
                "is_queue": b.is_queue,
            }
            for b in snapshot.bottlenecks
        ],
        "ci": {
            "median_duration_minutes": round(snapshot.ci.median_duration_seconds / 60, 1)
            if snapshot.ci.median_duration_seconds
            else None,
            "p90_duration_minutes": round(snapshot.ci.p90_duration_seconds / 60, 1)
            if snapshot.ci.p90_duration_seconds
            else None,
            "success_rate": round(snapshot.ci.success_rate, 4)
            if snapshot.ci.success_rate is not None
            else None,
            "flake_rate": round(snapshot.ci.flake_rate, 4)
            if snapshot.ci.flake_rate is not None
            else None,
            "total_runs": snapshot.ci.total_runs,
        },
    }
