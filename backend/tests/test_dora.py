from datetime import UTC, datetime, timedelta

import pytest

from app.models import Deployment, DeploymentStatus, Incident, PullRequest, WorkflowRun
from app.models.entities import RunConclusion
from app.services import dora

NOW = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


def deployment(days_ago: float, status=DeploymentStatus.SUCCESS) -> Deployment:
    finished = NOW - timedelta(days=days_ago)
    return Deployment(
        repository_id=1,
        environment="production",
        sha="a" * 40,
        status=status,
        started_at=finished - timedelta(minutes=5),
        finished_at=finished,
    )


def test_deployment_frequency_bands():
    daily = [deployment(d) for d in range(30)]
    metric = dora.deployment_frequency(daily, 30, [])
    assert metric.value == pytest.approx(1.0)
    assert metric.band == "elite"
    assert metric.higher_is_better is True


def test_deployment_frequency_ignores_failed_and_unfinished():
    deploys = [deployment(1), deployment(2, status=DeploymentStatus.FAILURE)]
    deploys.append(
        Deployment(
            repository_id=1,
            environment="production",
            sha="b" * 40,
            status=DeploymentStatus.SUCCESS,
            started_at=NOW,
            finished_at=None,
        )
    )
    assert dora.deployment_frequency(deploys, 30, []).sample_count == 1


def test_lead_time_measures_from_first_commit_not_pr_open():
    pr = PullRequest(
        id=1,
        repository_id=1,
        number=1,
        title="t",
        author="a",
        first_commit_at=NOW - timedelta(hours=10),
        opened_at=NOW - timedelta(hours=4),
    )
    deploy = deployment(0)
    metric = dora.lead_time_for_changes([(pr, deploy)], [])

    # Measured from the first commit (10h), not from the PR opening (4h).
    assert metric.value == pytest.approx(10 * 3600)
    assert metric.band == "elite"


def test_lead_time_band_cutoffs():
    assert dora._band_lead_time(3600) == "elite"
    assert dora._band_lead_time(3 * 86400) == "high"
    assert dora._band_lead_time(10 * 86400) == "medium"
    assert dora._band_lead_time(60 * 86400) == "low"


def test_change_failure_rate_is_failures_over_deployments():
    deploys = [deployment(d) for d in range(10)]
    incidents = [
        Incident(repository_id=1, title="revert", opened_at=NOW - timedelta(days=1)),
    ]
    metric = dora.change_failure_rate(deploys, incidents, [], [])
    assert metric.value == pytest.approx(0.1)
    assert metric.band == "high"


def test_change_failure_rate_is_none_without_deployments():
    assert dora.change_failure_rate([], [], [], []).value is None


def test_time_to_restore_skips_unresolved_incidents():
    resolved = Incident(
        repository_id=1,
        title="x",
        opened_at=NOW - timedelta(hours=4),
        resolved_at=NOW - timedelta(hours=2),
    )
    open_incident = Incident(repository_id=1, title="y", opened_at=NOW - timedelta(hours=1))

    metric = dora.time_to_restore([resolved, open_incident], [])
    assert metric.sample_count == 1
    assert metric.value == pytest.approx(2 * 3600)


def test_ci_health_flake_rate_counts_retried_successes():
    def run(attempt: int, conclusion: RunConclusion) -> WorkflowRun:
        return WorkflowRun(
            repository_id=1,
            name="test",
            head_sha="c" * 40,
            conclusion=conclusion,
            run_attempt=attempt,
            started_at=NOW - timedelta(minutes=20),
            completed_at=NOW - timedelta(minutes=10),
        )

    runs = [
        run(1, RunConclusion.SUCCESS),
        run(2, RunConclusion.SUCCESS),  # passed only after a retry
        run(1, RunConclusion.FAILURE),
    ]
    health = dora.ci_health(runs)

    assert health.total_runs == 3
    assert health.success_rate == pytest.approx(2 / 3)
    assert health.flake_rate == pytest.approx(0.5)


def test_window_bounds_gives_equal_length_comparison_periods():
    previous_start, current_start, end = dora.window_bounds(NOW, 30)
    assert (end - current_start) == (current_start - previous_start) == timedelta(days=30)
