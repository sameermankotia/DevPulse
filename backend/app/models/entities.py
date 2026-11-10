"""ORM models for the delivery dataset ingested from GitHub."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.types import UTCDateTime

# Postgres gets JSONB; SQLite (tests) falls back to generic JSON.
JSONColumn = JSONB().with_variant(JSON(), "sqlite")


class PullRequestState(str, enum.Enum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class ReviewState(str, enum.Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"


class RunConclusion(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class DeploymentStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    IN_PROGRESS = "in_progress"


class SyncStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    pull_requests: Mapped[list[PullRequest]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    deployments: Mapped[list[Deployment]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    incidents: Mapped[list[Incident]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class PullRequest(TimestampMixin, Base):
    """A pull request plus the lifecycle timestamps the stage model needs.

    Each nullable timestamp marks a transition. A stage is only measurable when
    both of its bounding timestamps exist, so analytics must skip missing ones
    rather than treat them as zero.
    """

    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),
        Index("ix_pr_repo_merged", "repository_id", "merged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(255), index=True)
    state: Mapped[PullRequestState] = mapped_column(
        Enum(PullRequestState, native_enum=False), default=PullRequestState.OPEN
    )
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)

    # Lifecycle boundaries, in order.
    first_commit_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ready_for_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    merged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    changed_files: Mapped[int] = mapped_column(Integer, default=0)
    commit_count: Mapped[int] = mapped_column(Integer, default=0)
    merge_sha: Mapped[str | None] = mapped_column(String(64))

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")
    reviews: Mapped[list[Review]] = relationship(
        back_populates="pull_request", cascade="all, delete-orphan"
    )
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="pull_request", cascade="all, delete-orphan"
    )

    @property
    def size(self) -> int:
        return self.additions + self.deletions


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("pull_request_id", "github_id", name="uq_review_gh"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True
    )
    github_id: Mapped[int | None] = mapped_column(BigInteger)
    reviewer: Mapped[str] = mapped_column(String(255), index=True)
    state: Mapped[ReviewState] = mapped_column(Enum(ReviewState, native_enum=False))
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)

    pull_request: Mapped[PullRequest] = relationship(back_populates="reviews")


class WorkflowRun(TimestampMixin, Base):
    """One CI run. Attached to a PR when the run was triggered by its head SHA."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_id", name="uq_run_gh"),
        Index("ix_run_repo_started", "repository_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    pull_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True
    )
    github_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(255), index=True)
    head_sha: Mapped[str] = mapped_column(String(64), index=True)
    event: Mapped[str] = mapped_column(String(64), default="pull_request")
    conclusion: Mapped[RunConclusion | None] = mapped_column(
        Enum(RunConclusion, native_enum=False)
    )
    run_attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    pull_request: Mapped[PullRequest | None] = relationship(back_populates="workflow_runs")

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_id", name="uq_deploy_gh"),
        Index("ix_deploy_repo_finished", "repository_id", "finished_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    pull_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="SET NULL")
    )
    github_id: Mapped[int | None] = mapped_column(BigInteger)
    environment: Mapped[str] = mapped_column(String(64), default="production", index=True)
    sha: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, native_enum=False), default=DeploymentStatus.SUCCESS
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    repository: Mapped[Repository] = relationship(back_populates="deployments")
    incidents: Mapped[list[Incident]] = relationship(back_populates="deployment")


class Incident(TimestampMixin, Base):
    """A failed change in production: a rollback, revert, or hotfix deploy."""

    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incident_repo_opened", "repository_id", "opened_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    deployment_id: Mapped[int | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text)
    # How the failure was detected: "revert", "rollback", "hotfix", or "label".
    source: Mapped[str] = mapped_column(String(32), default="revert")
    severity: Mapped[str] = mapped_column(String(16), default="major")
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    repository: Mapped[Repository] = relationship(back_populates="incidents")
    deployment: Mapped[Deployment | None] = relationship(back_populates="incidents")

    @property
    def recovery_seconds(self) -> float | None:
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.opened_at).total_seconds()


class Insight(TimestampMixin, Base):
    """A cached LLM recommendation set for one repository and time window."""

    __tablename__ = "insights"
    __table_args__ = (Index("ix_insight_repo_created", "repository_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    window_days: Mapped[int] = mapped_column(Integer, default=30)
    model: Mapped[str] = mapped_column(String(128))
    # Fingerprint of the metric digest, so identical inputs reuse the cached answer.
    digest_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONColumn, default=dict)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Float)


class SyncRun(TimestampMixin, Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, native_enum=False), default=SyncStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    pull_requests_synced: Mapped[int] = mapped_column(Integer, default=0)
    runs_synced: Mapped[int] = mapped_column(Integer, default=0)
    deployments_synced: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
