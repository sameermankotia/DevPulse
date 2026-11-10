"""Generates a realistic delivery dataset so the product is explorable offline.

The shapes here are not uniform noise. Durations are log-normal (the real
distribution of human queue times), review pickup slows down across the week,
and one repository is deliberately unhealthy so the bottleneck ranking and the
recommendation engine have something true to find.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import (
    Deployment,
    DeploymentStatus,
    Incident,
    PullRequest,
    PullRequestState,
    Repository,
    Review,
    ReviewState,
    RunConclusion,
    WorkflowRun,
)

log = get_logger(__name__)

HOUR = 3600


class RepoProfile:
    """Per-repository delivery characteristics, in hours unless noted."""

    def __init__(
        self,
        full_name: str,
        prs_per_week: float,
        code_hours: float,
        pickup_hours: float,
        review_hours: float,
        merge_hours: float,
        release_hours: float,
        ci_minutes: float,
        ci_failure_rate: float,
        revert_rate: float,
        authors: tuple[str, ...],
    ) -> None:
        self.full_name = full_name
        self.prs_per_week = prs_per_week
        self.code_hours = code_hours
        self.pickup_hours = pickup_hours
        self.review_hours = review_hours
        self.merge_hours = merge_hours
        self.release_hours = release_hours
        self.ci_minutes = ci_minutes
        self.ci_failure_rate = ci_failure_rate
        self.revert_rate = revert_rate
        self.authors = authors


TEAM_A = ("rhodes", "okafor", "lindqvist", "bhatt", "moreau", "tanaka")
TEAM_B = ("okafor", "silva", "nakamura", "whitfield", "aziz")
TEAM_C = ("lindqvist", "petrov", "adeyemi", "calder")

PROFILES: tuple[RepoProfile, ...] = (
    # The flagship service: healthy, but review pickup is quietly the worst stage.
    RepoProfile(
        "northwind/platform-api",
        prs_per_week=22,
        code_hours=14,
        pickup_hours=9.5,
        review_hours=6,
        merge_hours=1.2,
        release_hours=3.5,
        ci_minutes=14,
        ci_failure_rate=0.11,
        revert_rate=0.045,
        authors=TEAM_A,
    ),
    # The problem child: a slow merge queue and a batched weekly release train.
    RepoProfile(
        "northwind/billing-core",
        prs_per_week=9,
        code_hours=31,
        pickup_hours=18,
        review_hours=22,
        merge_hours=9,
        release_hours=41,
        ci_minutes=37,
        ci_failure_rate=0.23,
        revert_rate=0.14,
        authors=TEAM_B,
    ),
    # Near-elite: trunk-based, small changes, continuous deploy.
    RepoProfile(
        "northwind/edge-gateway",
        prs_per_week=31,
        code_hours=5,
        pickup_hours=1.4,
        review_hours=2.1,
        merge_hours=0.4,
        release_hours=0.6,
        ci_minutes=6,
        ci_failure_rate=0.05,
        revert_rate=0.02,
        authors=TEAM_C,
    ),
    # Front end: fast to review, slow to author -- big PRs.
    RepoProfile(
        "northwind/console-web",
        prs_per_week=17,
        code_hours=27,
        pickup_hours=3.2,
        review_hours=5.5,
        merge_hours=0.9,
        release_hours=5,
        ci_minutes=19,
        ci_failure_rate=0.14,
        revert_rate=0.06,
        authors=TEAM_A + TEAM_C,
    ),
)

TITLE_VERBS = (
    "Add", "Fix", "Refactor", "Remove", "Harden", "Cache", "Split", "Instrument",
    "Migrate", "Simplify", "Batch", "Guard", "Backfill", "Rename", "Tune",
)
TITLE_OBJECTS = (
    "the invoice reconciliation job", "retry handling in the webhook consumer",
    "connection pooling for read replicas", "the stale feature-flag cache",
    "idempotency keys on payment intents", "the N+1 in the org members query",
    "timeout handling in the export worker", "tenant scoping on audit events",
    "the dashboard aggregation query", "schema validation at the edge",
    "rate limiting on the public API", "the nightly usage rollup",
    "session revocation on password change", "pagination in the activity feed",
    "structured logging in the scheduler",
)
WORKFLOWS = ("build", "test", "lint", "integration", "e2e")


def _lognormal(rng: random.Random, median_hours: float, sigma: float = 0.85) -> float:
    """Hours drawn from a log-normal with the given median.

    Queue times are right-skewed: most changes move quickly and a tail waits
    days. A normal distribution would understate that tail badly.
    """
    import math

    return math.exp(math.log(max(median_hours, 0.05)) + rng.gauss(0, sigma))


def _business_drag(rng: random.Random, moment: datetime) -> float:
    """Multiplier for work that lands near or on a weekend."""
    weekday = moment.weekday()
    if weekday >= 5:
        return rng.uniform(2.2, 4.0)
    if weekday == 4 and moment.hour >= 15:
        return rng.uniform(1.8, 3.2)
    if moment.hour >= 18 or moment.hour < 7:
        return rng.uniform(1.3, 2.0)
    return rng.uniform(0.75, 1.25)


async def is_seeded(session: AsyncSession) -> bool:
    count = await session.scalar(select(func.count()).select_from(Repository))
    return bool(count)


async def seed(session: AsyncSession, seed_value: int = 20260409, days: int = 120) -> int:
    """Populates the database with the demo dataset. Returns repository count."""
    if await is_seeded(session):
        log.info("demo.seed_skipped", reason="repositories already present")
        return 0

    rng = random.Random(seed_value)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)

    for profile in PROFILES:
        repo = Repository(
            full_name=profile.full_name,
            github_id=rng.randint(10_000_000, 99_999_999),
            default_branch="main",
            is_private=True,
            last_synced_at=now - timedelta(minutes=rng.randint(4, 50)),
        )
        session.add(repo)
        await session.flush()

        await _seed_repository(session, repo, profile, rng, start, now)

    await session.commit()
    log.info("demo.seeded", repositories=len(PROFILES), days=days)
    return len(PROFILES)


async def _seed_repository(
    session: AsyncSession,
    repo: Repository,
    profile: RepoProfile,
    rng: random.Random,
    start: datetime,
    now: datetime,
) -> None:
    total_prs = int(profile.prs_per_week * ((now - start).days / 7))
    number = 1000
    deployments: list[Deployment] = []
    merged_prs: list[PullRequest] = []

    for _ in range(total_prs):
        number += 1
        offset_hours = rng.uniform(0, (now - start).total_seconds() / HOUR)
        first_commit = start + timedelta(hours=offset_hours)

        code = _lognormal(rng, profile.code_hours)
        opened = first_commit + timedelta(hours=code)
        if opened >= now:
            continue

        author = rng.choice(profile.authors)
        size = int(abs(rng.gauss(profile.code_hours * 9, profile.code_hours * 6))) + 12

        pr = PullRequest(
            repository_id=repo.id,
            number=number,
            title=f"{rng.choice(TITLE_VERBS)} {rng.choice(TITLE_OBJECTS)}",
            author=author,
            state=PullRequestState.OPEN,
            is_draft=False,
            first_commit_at=first_commit,
            opened_at=opened,
            ready_for_review_at=opened,
            additions=int(size * rng.uniform(0.55, 0.9)),
            deletions=int(size * rng.uniform(0.1, 0.45)),
            changed_files=max(1, int(size / rng.uniform(18, 60))),
            commit_count=max(1, int(rng.gauss(4, 2))),
        )
        session.add(pr)
        await session.flush()

        # CI runs on the PR head, sometimes more than once.
        _seed_ci_runs(session, repo, pr, profile, rng, opened)

        pickup = _lognormal(rng, profile.pickup_hours) * _business_drag(rng, opened)
        first_review = opened + timedelta(hours=pickup)
        if first_review >= now:
            continue
        pr.first_review_at = first_review

        reviewers = [a for a in profile.authors if a != author]
        reviewer = rng.choice(reviewers) if reviewers else "reviewer"

        review = _lognormal(rng, profile.review_hours)
        approved = first_review + timedelta(hours=review)

        # Roughly a third of reviews ask for changes before approving.
        if rng.random() < 0.34:
            session.add(
                Review(
                    pull_request_id=pr.id,
                    reviewer=reviewer,
                    state=ReviewState.CHANGES_REQUESTED,
                    submitted_at=first_review,
                    comment_count=rng.randint(2, 11),
                )
            )
            approved += timedelta(hours=_lognormal(rng, profile.review_hours * 0.8))

        if approved >= now:
            continue

        session.add(
            Review(
                pull_request_id=pr.id,
                reviewer=reviewer,
                state=ReviewState.APPROVED,
                submitted_at=approved,
                comment_count=rng.randint(0, 4),
            )
        )
        pr.approved_at = approved

        merge_wait = _lognormal(rng, profile.merge_hours) * _business_drag(rng, approved)
        merged = approved + timedelta(hours=merge_wait)
        if merged >= now:
            continue

        pr.merged_at = merged
        pr.closed_at = merged
        pr.state = PullRequestState.MERGED
        pr.merge_sha = f"{rng.getrandbits(160):040x}"
        merged_prs.append(pr)

        release_wait = _lognormal(rng, profile.release_hours)
        deployed = merged + timedelta(hours=release_wait)
        if deployed >= now:
            continue

        deployment = Deployment(
            repository_id=repo.id,
            pull_request_id=pr.id,
            github_id=rng.randint(100_000_000, 999_999_999),
            environment="production",
            sha=pr.merge_sha,
            status=DeploymentStatus.SUCCESS,
            started_at=deployed - timedelta(minutes=rng.randint(3, 22)),
            finished_at=deployed,
        )
        session.add(deployment)
        deployments.append(deployment)

    await session.flush()
    _seed_incidents(session, repo, profile, rng, deployments, now)


def _seed_ci_runs(
    session: AsyncSession,
    repo: Repository,
    pr: PullRequest,
    profile: RepoProfile,
    rng: random.Random,
    opened: datetime,
) -> None:
    head_sha = f"{rng.getrandbits(160):040x}"
    for workflow in rng.sample(WORKFLOWS, k=rng.randint(2, len(WORKFLOWS))):
        failed_first = rng.random() < profile.ci_failure_rate
        attempt = 1
        started = opened + timedelta(minutes=rng.randint(1, 9))

        if failed_first:
            duration = profile.ci_minutes * rng.uniform(0.4, 1.2)
            session.add(
                WorkflowRun(
                    repository_id=repo.id,
                    pull_request_id=pr.id,
                    github_id=rng.randint(10**9, 10**10),
                    name=workflow,
                    head_sha=head_sha,
                    event="pull_request",
                    conclusion=RunConclusion.FAILURE,
                    run_attempt=attempt,
                    started_at=started,
                    completed_at=started + timedelta(minutes=duration),
                )
            )
            attempt += 1
            started += timedelta(minutes=duration + rng.randint(5, 40))

        duration = profile.ci_minutes * rng.uniform(0.7, 1.6)
        session.add(
            WorkflowRun(
                repository_id=repo.id,
                pull_request_id=pr.id,
                github_id=rng.randint(10**9, 10**10),
                name=workflow,
                head_sha=head_sha,
                event="pull_request",
                conclusion=RunConclusion.SUCCESS,
                run_attempt=attempt,
                started_at=started,
                completed_at=started + timedelta(minutes=duration),
            )
        )


def _seed_incidents(
    session: AsyncSession,
    repo: Repository,
    profile: RepoProfile,
    rng: random.Random,
    deployments: list[Deployment],
    now: datetime,
) -> None:
    for deployment in deployments:
        if rng.random() >= profile.revert_rate or deployment.finished_at is None:
            continue

        # Detection lags the deploy; recovery lags detection.
        detected = deployment.finished_at + timedelta(hours=_lognormal(rng, 1.6, sigma=0.7))
        resolved = detected + timedelta(hours=_lognormal(rng, profile.merge_hours + 1.5))
        if resolved >= now:
            continue

        session.add(
            Incident(
                repository_id=repo.id,
                deployment_id=deployment.id,
                title=f"Revert: deploy {deployment.sha[:7]} caused elevated error rate",
                source="revert",
                severity=rng.choice(("major", "major", "minor", "critical")),
                opened_at=detected,
                resolved_at=resolved,
            )
        )
