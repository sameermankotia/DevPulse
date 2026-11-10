"""Maps GitHub payloads onto the delivery dataset.

The interesting work is derivation, not transport: GitHub does not expose
"when was this first reviewed" or "when did this change break production", so
both are reconstructed from reviews, commits, and revert patterns.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
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
    SyncRun,
    SyncStatus,
    WorkflowRun,
)
from app.services.github import GitHubClient

log = get_logger(__name__)

# A revert or hotfix landing shortly after a deploy is the standard signal for
# a change failure when a team has no incident tracker wired up.
REVERT_PATTERN = re.compile(r"^(revert|rollback)\b", re.IGNORECASE)
HOTFIX_PATTERN = re.compile(r"\b(hotfix|incident|sev[-\s]?\d)\b", re.IGNORECASE)


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _review_state(raw: str) -> ReviewState | None:
    mapping = {
        "APPROVED": ReviewState.APPROVED,
        "CHANGES_REQUESTED": ReviewState.CHANGES_REQUESTED,
        "COMMENTED": ReviewState.COMMENTED,
        "DISMISSED": ReviewState.DISMISSED,
    }
    return mapping.get(raw.upper())


def _conclusion(raw: str | None) -> RunConclusion | None:
    if not raw:
        return None
    try:
        return RunConclusion(raw.lower())
    except ValueError:
        return None


class Ingestor:
    def __init__(self, session: AsyncSession, client: GitHubClient, settings: Settings) -> None:
        self._session = session
        self._client = client
        self._settings = settings

    async def sync_repository(self, full_name: str, backfill_days: int | None = None) -> SyncRun:
        days = backfill_days or self._settings.github_backfill_days
        since = datetime.now(UTC) - timedelta(days=days)

        repo = await self._upsert_repository(full_name)
        sync = SyncRun(repository_id=repo.id, status=SyncStatus.RUNNING)
        self._session.add(sync)
        await self._session.flush()

        try:
            sync.pull_requests_synced = await self._sync_pull_requests(repo, full_name, since)
            sync.runs_synced = await self._sync_workflow_runs(repo, full_name, since)
            sync.deployments_synced = await self._sync_deployments(repo, full_name)
            await self._derive_incidents(repo)

            repo.last_synced_at = datetime.now(UTC)
            sync.status = SyncStatus.SUCCEEDED
        except Exception as exc:
            sync.status = SyncStatus.FAILED
            sync.error = str(exc)[:2000]
            log.exception("sync.failed", repository=full_name)
            raise
        finally:
            sync.finished_at = datetime.now(UTC)
            await self._session.commit()

        return sync

    async def _upsert_repository(self, full_name: str) -> Repository:
        payload = await self._client.get_repository(full_name)
        existing = await self._session.scalar(
            select(Repository).where(Repository.full_name == full_name)
        )
        repo = existing or Repository(full_name=full_name)
        repo.github_id = payload.get("id")
        repo.default_branch = payload.get("default_branch", "main")
        repo.is_private = payload.get("private", False)
        if existing is None:
            self._session.add(repo)
        await self._session.flush()
        return repo

    async def _sync_pull_requests(
        self, repo: Repository, full_name: str, since: datetime
    ) -> int:
        count = 0
        async for summary in self._client.list_pull_requests(full_name, since=since):
            number = summary["number"]
            detail = await self._client.get_pull_request(full_name, number)
            reviews = await self._client.list_reviews(full_name, number)
            commits = await self._client.list_commits(full_name, number)

            pr = await self._session.scalar(
                select(PullRequest).where(
                    PullRequest.repository_id == repo.id, PullRequest.number == number
                )
            )
            if pr is None:
                pr = PullRequest(repository_id=repo.id, number=number, opened_at=datetime.now(UTC))
                self._session.add(pr)

            self._apply_pull_request(pr, detail, commits)
            await self._session.flush()
            self._apply_reviews(pr, reviews)
            count += 1

        await self._session.flush()
        return count

    def _apply_pull_request(
        self, pr: PullRequest, detail: dict[str, Any], commits: list[dict[str, Any]]
    ) -> None:
        pr.title = detail.get("title", "")
        pr.author = (detail.get("user") or {}).get("login", "unknown")
        pr.is_draft = detail.get("draft", False)
        pr.opened_at = _ts(detail.get("created_at")) or pr.opened_at
        pr.merged_at = _ts(detail.get("merged_at"))
        pr.closed_at = _ts(detail.get("closed_at"))
        pr.additions = detail.get("additions", 0)
        pr.deletions = detail.get("deletions", 0)
        pr.changed_files = detail.get("changed_files", 0)
        pr.commit_count = detail.get("commits", len(commits))
        pr.merge_sha = detail.get("merge_commit_sha")

        if pr.merged_at is not None:
            pr.state = PullRequestState.MERGED
        elif pr.closed_at is not None:
            pr.state = PullRequestState.CLOSED
        else:
            pr.state = PullRequestState.OPEN

        # The earliest authored commit is when work on the change actually began,
        # which is what lead time should measure from -- not when the PR opened.
        commit_times = [
            _ts((c.get("commit") or {}).get("author", {}).get("date")) for c in commits
        ]
        valid = [t for t in commit_times if t is not None]
        pr.first_commit_at = min(valid) if valid else pr.opened_at

        # GitHub exposes no ready_for_review timestamp on the REST PR object. A PR
        # that is not a draft was reviewable from the moment it opened.
        if not pr.is_draft and pr.ready_for_review_at is None:
            pr.ready_for_review_at = pr.opened_at

    def _apply_reviews(self, pr: PullRequest, payloads: list[dict[str, Any]]) -> None:
        known = {r.github_id for r in pr.reviews}
        first_at: datetime | None = None
        approved_at: datetime | None = None

        for payload in payloads:
            submitted = _ts(payload.get("submitted_at"))
            state = _review_state(payload.get("state", ""))
            if submitted is None or state is None:
                continue

            reviewer = (payload.get("user") or {}).get("login", "unknown")
            # The author commenting on their own PR is not a review.
            if reviewer != pr.author:
                if first_at is None or submitted < first_at:
                    first_at = submitted
                if state == ReviewState.APPROVED and (
                    approved_at is None or submitted < approved_at
                ):
                    approved_at = submitted

            if payload.get("id") not in known:
                pr.reviews.append(
                    Review(
                        github_id=payload.get("id"),
                        reviewer=reviewer,
                        state=state,
                        submitted_at=submitted,
                    )
                )

        pr.first_review_at = first_at
        pr.approved_at = approved_at

    async def _sync_workflow_runs(
        self, repo: Repository, full_name: str, since: datetime
    ) -> int:
        shas = {
            sha: pr_id
            for sha, pr_id in (
                await self._session.execute(
                    select(PullRequest.merge_sha, PullRequest.id).where(
                        PullRequest.repository_id == repo.id, PullRequest.merge_sha.isnot(None)
                    )
                )
            ).all()
        }

        existing_ids = set(
            (
                await self._session.scalars(
                    select(WorkflowRun.github_id).where(WorkflowRun.repository_id == repo.id)
                )
            ).all()
        )

        count = 0
        async for payload in self._client.list_workflow_runs(full_name, since=since):
            if payload.get("id") in existing_ids:
                continue
            started = _ts(payload.get("run_started_at")) or _ts(payload.get("created_at"))
            if started is None:
                continue

            self._session.add(
                WorkflowRun(
                    repository_id=repo.id,
                    pull_request_id=shas.get(payload.get("head_sha")),
                    github_id=payload.get("id"),
                    name=payload.get("name", "workflow"),
                    head_sha=payload.get("head_sha", ""),
                    event=payload.get("event", "push"),
                    conclusion=_conclusion(payload.get("conclusion")),
                    run_attempt=payload.get("run_attempt", 1),
                    started_at=started,
                    completed_at=_ts(payload.get("updated_at")),
                )
            )
            count += 1

        await self._session.flush()
        return count

    async def _sync_deployments(self, repo: Repository, full_name: str) -> int:
        existing_ids = set(
            (
                await self._session.scalars(
                    select(Deployment.github_id).where(Deployment.repository_id == repo.id)
                )
            ).all()
        )
        merge_shas = {
            sha: pr_id
            for sha, pr_id in (
                await self._session.execute(
                    select(PullRequest.merge_sha, PullRequest.id).where(
                        PullRequest.repository_id == repo.id, PullRequest.merge_sha.isnot(None)
                    )
                )
            ).all()
        }

        count = 0
        async for payload in self._client.list_deployments(full_name):
            if payload.get("id") in existing_ids:
                continue
            created = _ts(payload.get("created_at"))
            if created is None:
                continue

            statuses = await self._client.list_deployment_statuses(full_name, payload["id"])
            # Statuses come back newest first; the terminal one decides the outcome.
            terminal = next(
                (s for s in statuses if s.get("state") in ("success", "failure", "error")),
                None,
            )
            state = (terminal or {}).get("state")
            status = {
                "success": DeploymentStatus.SUCCESS,
                "failure": DeploymentStatus.FAILURE,
                "error": DeploymentStatus.FAILURE,
            }.get(state, DeploymentStatus.IN_PROGRESS)

            self._session.add(
                Deployment(
                    repository_id=repo.id,
                    pull_request_id=merge_shas.get(payload.get("sha")),
                    github_id=payload.get("id"),
                    environment=payload.get("environment", "production"),
                    sha=payload.get("sha", ""),
                    status=status,
                    started_at=created,
                    finished_at=_ts((terminal or {}).get("created_at")),
                )
            )
            count += 1

        await self._session.flush()
        return count

    async def _derive_incidents(self, repo: Repository) -> None:
        """Infer change failures from reverts, rollbacks, and hotfixes.

        Each such PR is matched to the most recent production deployment that
        preceded it; that deployment is the change the fix is undoing.
        """
        prs = (
            await self._session.scalars(
                select(PullRequest)
                .where(
                    PullRequest.repository_id == repo.id,
                    PullRequest.merged_at.isnot(None),
                )
                .order_by(PullRequest.merged_at)
            )
        ).all()

        deployments = (
            await self._session.scalars(
                select(Deployment)
                .where(
                    Deployment.repository_id == repo.id,
                    Deployment.status == DeploymentStatus.SUCCESS,
                    Deployment.finished_at.isnot(None),
                )
                .order_by(Deployment.finished_at)
            )
        ).all()

        known_titles = set(
            (
                await self._session.scalars(
                    select(Incident.title).where(Incident.repository_id == repo.id)
                )
            ).all()
        )

        for pr in prs:
            title = pr.title or ""
            if not (REVERT_PATTERN.match(title) or HOTFIX_PATTERN.search(title)):
                continue
            if title in known_titles:
                continue

            culprit = None
            for deployment in deployments:
                if deployment.finished_at and deployment.finished_at <= (
                    pr.first_commit_at or pr.opened_at
                ):
                    culprit = deployment
                else:
                    break

            # Detection time is when someone started on the fix; recovery is when
            # the fix reached production.
            opened = culprit.finished_at if culprit else pr.opened_at
            resolved = next(
                (
                    d.finished_at
                    for d in deployments
                    if d.pull_request_id == pr.id and d.finished_at
                ),
                pr.merged_at,
            )

            self._session.add(
                Incident(
                    repository_id=repo.id,
                    deployment_id=culprit.id if culprit else None,
                    title=title[:500],
                    source="revert" if REVERT_PATTERN.match(title) else "hotfix",
                    severity="major",
                    opened_at=opened,
                    resolved_at=resolved,
                )
            )
            known_titles.add(title)

        await self._session.flush()
