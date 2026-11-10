"""Initial delivery schema.

Revision ID: 0001
Revises:
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PR_STATE = sa.Enum("OPEN", "MERGED", "CLOSED", name="pullrequeststate", native_enum=False)
REVIEW_STATE = sa.Enum(
    "APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED",
    name="reviewstate", native_enum=False,
)
RUN_CONCLUSION = sa.Enum(
    "SUCCESS", "FAILURE", "CANCELLED", "TIMED_OUT", "SKIPPED",
    name="runconclusion", native_enum=False,
)
DEPLOY_STATUS = sa.Enum(
    "SUCCESS", "FAILURE", "IN_PROGRESS", name="deploymentstatus", native_enum=False
)
SYNC_STATUS = sa.Enum("RUNNING", "SUCCEEDED", "FAILED", name="syncstatus", native_enum=False)

TS = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False, unique=True),
        sa.Column("default_branch", sa.String(255), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", TS, nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"])

    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("state", PR_STATE, nullable=False),
        sa.Column("is_draft", sa.Boolean(), nullable=False),
        sa.Column("first_commit_at", TS, nullable=True),
        sa.Column("opened_at", TS, nullable=False),
        sa.Column("ready_for_review_at", TS, nullable=True),
        sa.Column("first_review_at", TS, nullable=True),
        sa.Column("approved_at", TS, nullable=True),
        sa.Column("merged_at", TS, nullable=True),
        sa.Column("closed_at", TS, nullable=True),
        sa.Column("additions", sa.Integer(), nullable=False),
        sa.Column("deletions", sa.Integer(), nullable=False),
        sa.Column("changed_files", sa.Integer(), nullable=False),
        sa.Column("commit_count", sa.Integer(), nullable=False),
        sa.Column("merge_sha", sa.String(64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),
    )
    op.create_index("ix_pull_requests_repository_id", "pull_requests", ["repository_id"])
    op.create_index("ix_pull_requests_author", "pull_requests", ["author"])
    op.create_index("ix_pull_requests_opened_at", "pull_requests", ["opened_at"])
    op.create_index("ix_pr_repo_merged", "pull_requests", ["repository_id", "merged_at"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pull_request_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewer", sa.String(255), nullable=False),
        sa.Column("state", REVIEW_STATE, nullable=False),
        sa.Column("submitted_at", TS, nullable=False),
        sa.Column("comment_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("pull_request_id", "github_id", name="uq_review_gh"),
    )
    op.create_index("ix_reviews_pull_request_id", "reviews", ["pull_request_id"])
    op.create_index("ix_reviews_reviewer", "reviews", ["reviewer"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pull_request_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("github_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("conclusion", RUN_CONCLUSION, nullable=True),
        sa.Column("run_attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("completed_at", TS, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("repository_id", "github_id", name="uq_run_gh"),
    )
    op.create_index("ix_workflow_runs_repository_id", "workflow_runs", ["repository_id"])
    op.create_index("ix_workflow_runs_pull_request_id", "workflow_runs", ["pull_request_id"])
    op.create_index("ix_workflow_runs_name", "workflow_runs", ["name"])
    op.create_index("ix_workflow_runs_head_sha", "workflow_runs", ["head_sha"])
    op.create_index("ix_run_repo_started", "workflow_runs", ["repository_id", "started_at"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pull_request_id",
            sa.Integer(),
            sa.ForeignKey("pull_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("github_id", sa.BigInteger(), nullable=True),
        sa.Column("environment", sa.String(64), nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("status", DEPLOY_STATUS, nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("repository_id", "github_id", name="uq_deploy_gh"),
    )
    op.create_index("ix_deployments_repository_id", "deployments", ["repository_id"])
    op.create_index("ix_deployments_environment", "deployments", ["environment"])
    op.create_index("ix_deployments_sha", "deployments", ["sha"])
    op.create_index("ix_deploy_repo_finished", "deployments", ["repository_id", "finished_at"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deployment_id",
            sa.Integer(),
            sa.ForeignKey("deployments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("opened_at", TS, nullable=False),
        sa.Column("resolved_at", TS, nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_incidents_repository_id", "incidents", ["repository_id"])
    op.create_index("ix_incident_repo_opened", "incidents", ["repository_id", "opened_at"])

    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("digest_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_insights_repository_id", "insights", ["repository_id"])
    op.create_index("ix_insights_digest_hash", "insights", ["digest_hash"])
    op.create_index("ix_insight_repo_created", "insights", ["repository_id", "created_at"])

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", SYNC_STATUS, nullable=False),
        sa.Column("started_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        sa.Column("pull_requests_synced", sa.Integer(), nullable=False),
        sa.Column("runs_synced", sa.Integer(), nullable=False),
        sa.Column("deployments_synced", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_sync_runs_repository_id", "sync_runs", ["repository_id"])


def downgrade() -> None:
    for table in (
        "sync_runs",
        "insights",
        "incidents",
        "deployments",
        "workflow_runs",
        "reviews",
        "pull_requests",
        "repositories",
    ):
        op.drop_table(table)
