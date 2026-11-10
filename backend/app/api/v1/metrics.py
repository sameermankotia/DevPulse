from fastapi import APIRouter, Query

from app.api.deps import RepositoryDep, SessionDep
from app.schemas.api import (
    BottleneckOut,
    CiHealthOut,
    MetricOut,
    PullRequestOut,
    SnapshotOut,
    StageOut,
)
from app.services import analytics, stages

router = APIRouter()


@router.get("/{repository_id}/snapshot", response_model=SnapshotOut)
async def get_snapshot(
    repository: RepositoryDep,
    session: SessionDep,
    window_days: int = Query(30, ge=7, le=180),
) -> SnapshotOut:
    """Everything the dashboard needs for one repository and window, in one call."""
    snapshot = await analytics.build_snapshot(session, repository, window_days)

    return SnapshotOut(
        repository=repository,
        window_days=snapshot.window_days,
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        metrics=[MetricOut.model_validate(m, from_attributes=True) for m in snapshot.metrics],
        stages=[StageOut.model_validate(s, from_attributes=True) for s in snapshot.stage_summaries],
        bottlenecks=[
            BottleneckOut.model_validate(b, from_attributes=True) for b in snapshot.bottlenecks
        ],
        ci=CiHealthOut.model_validate(snapshot.ci, from_attributes=True),
        pull_request_count=snapshot.pull_request_count,
        contributor_count=snapshot.contributor_count,
        median_pr_size=snapshot.median_pr_size,
    )


@router.get("/{repository_id}/pull-requests", response_model=list[PullRequestOut])
async def list_pull_requests(
    repository: RepositoryDep,
    session: SessionDep,
    window_days: int = Query(30, ge=7, le=180),
    limit: int = Query(50, ge=1, le=200),
) -> list[PullRequestOut]:
    snapshot = await analytics.build_snapshot(session, repository, window_days)

    out: list[PullRequestOut] = []
    for pr, deployment in snapshot.recent_pull_requests[:limit]:
        durations = stages.stage_durations(pr, deployment)
        start = pr.first_commit_at or pr.opened_at
        lead = (
            (deployment.finished_at - start).total_seconds()
            if deployment and deployment.finished_at
            else None
        )
        out.append(
            PullRequestOut(
                number=pr.number,
                title=pr.title,
                author=pr.author,
                state=pr.state.value,
                opened_at=pr.opened_at,
                merged_at=pr.merged_at,
                additions=pr.additions,
                deletions=pr.deletions,
                changed_files=pr.changed_files,
                stages=durations,
                lead_time_seconds=lead,
            )
        )
    return out
