"""Pydantic response models. These define the contract the frontend types mirror."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    default_branch: str
    is_private: bool
    last_synced_at: datetime | None


class TrackRepositoryIn(BaseModel):
    full_name: str = Field(pattern=r"^[\w.-]+/[\w.-]+$", examples=["octocat/hello-world"])
    backfill_days: int | None = Field(default=None, ge=1, le=365)


class MetricPointOut(BaseModel):
    at: date
    value: float


class MetricOut(BaseModel):
    key: str
    label: str
    unit: str
    value: float | None
    band: Literal["elite", "high", "medium", "low"] | None
    trend: float | None
    higher_is_better: bool
    sample_count: int
    series: list[MetricPointOut]


class StageOut(BaseModel):
    stage: str
    label: str
    description: str
    is_queue: bool
    sample_count: int
    p50_seconds: float | None
    p75_seconds: float | None
    p90_seconds: float | None
    share_of_pipeline: float


class BottleneckOut(BaseModel):
    stage: str
    label: str
    severity: Literal["critical", "elevated", "healthy"]
    p50_seconds: float
    p90_seconds: float
    threshold_seconds: float
    overage: float
    is_queue: bool
    sample_count: int
    share_of_pipeline: float
    evidence_pr_numbers: list[int]


class CiHealthOut(BaseModel):
    median_duration_seconds: float | None
    p90_duration_seconds: float | None
    success_rate: float | None
    flake_rate: float | None
    total_runs: int


class PullRequestOut(BaseModel):
    number: int
    title: str
    author: str
    state: str
    opened_at: datetime
    merged_at: datetime | None
    additions: int
    deletions: int
    changed_files: int
    # Stage durations present for this PR, in seconds.
    stages: dict[str, float]
    lead_time_seconds: float | None


class SnapshotOut(BaseModel):
    repository: RepositoryOut
    window_days: int
    window_start: datetime
    window_end: datetime
    metrics: list[MetricOut]
    stages: list[StageOut]
    bottlenecks: list[BottleneckOut]
    ci: CiHealthOut
    pull_request_count: int
    contributor_count: int
    median_pr_size: float | None


class RecommendationOut(BaseModel):
    title: str
    stage: str
    impact: Literal["high", "medium", "low"]
    effort: Literal["low", "medium", "high"]
    rationale: str
    expected_effect: str
    ai_assisted: bool
    ai_note: str


class InsightOut(BaseModel):
    id: int
    repository_id: int
    window_days: int
    model: str
    created_at: datetime
    headline: str
    summary: str
    confidence: str
    recommendations: list[RecommendationOut]
    risks: list[str]
    latency_ms: float | None


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    pull_requests_synced: int
    runs_synced: int
    deployments_synced: int
    error: str | None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    environment: str
    database: bool
    llm_configured: bool
    demo_mode: bool
