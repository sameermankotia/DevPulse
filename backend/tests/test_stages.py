from datetime import UTC, datetime, timedelta

from app.models import Deployment, DeploymentStatus, PullRequest
from app.services import stages

BASE = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def make_pr(**overrides) -> PullRequest:
    defaults = dict(
        id=1,
        repository_id=1,
        number=42,
        title="Tune the export worker",
        author="rhodes",
        first_commit_at=BASE,
        opened_at=BASE + timedelta(hours=6),
        ready_for_review_at=BASE + timedelta(hours=6),
        first_review_at=BASE + timedelta(hours=10),
        approved_at=BASE + timedelta(hours=14),
        merged_at=BASE + timedelta(hours=15),
    )
    defaults.update(overrides)
    return PullRequest(**defaults)


def make_deployment(finished_at: datetime | None) -> Deployment:
    return Deployment(
        id=1,
        repository_id=1,
        environment="production",
        sha="abc",
        status=DeploymentStatus.SUCCESS,
        started_at=BASE,
        finished_at=finished_at,
    )


def test_stage_durations_cover_the_pipeline():
    pr = make_pr()
    deployment = make_deployment(BASE + timedelta(hours=18))
    durations = stages.stage_durations(pr, deployment)

    assert durations["code"] == 6 * 3600
    assert durations["pickup"] == 4 * 3600
    assert durations["review"] == 4 * 3600
    assert durations["rework"] == 1 * 3600
    assert durations["release"] == 3 * 3600


def test_missing_boundary_omits_the_stage_rather_than_scoring_zero():
    # A PR nobody has reviewed has no measurable pickup time yet -- counting it
    # as zero would drag the team median down and hide the problem.
    pr = make_pr(first_review_at=None, approved_at=None, merged_at=None)
    durations = stages.stage_durations(pr, None)

    assert "code" in durations
    assert "pickup" not in durations
    assert "review" not in durations
    assert "release" not in durations


def test_draft_pr_starts_the_review_clock_at_ready_not_opened():
    pr = make_pr(
        opened_at=BASE,
        ready_for_review_at=BASE + timedelta(hours=20),
        first_review_at=BASE + timedelta(hours=22),
    )
    assert stages.stage_durations(pr, None)["pickup"] == 2 * 3600


def test_inverted_timestamps_are_discarded():
    # Backdated events and clock skew produce negative stages; they are unusable.
    pr = make_pr(first_review_at=BASE + timedelta(hours=2))
    assert "pickup" not in stages.stage_durations(pr, None)


def test_summarize_computes_shares_that_sum_to_one():
    pr = make_pr()
    samples = stages.collect_samples([(pr, make_deployment(BASE + timedelta(hours=18)))])
    summaries = stages.summarize(samples)

    total_share = sum(s.share_of_pipeline for s in summaries)
    assert total_share == 1.0
    assert [s.stage for s in summaries] == list(stages.STAGE_ORDER)


def test_bottlenecks_rank_queue_stages_above_work_stages():
    """A queue stage and a work stage equally over threshold: queue wins.

    Removing waiting costs no engineering effort, so it is the better first move.
    """
    pickup_threshold = stages.STAGE_THRESHOLD_HOURS["pickup"] * 3600
    review_threshold = stages.STAGE_THRESHOLD_HOURS["review"] * 3600

    samples = [
        stages.StageSample("pickup", pickup_threshold * 3, 1, 1),
        stages.StageSample("review", review_threshold * 3, 1, 1),
    ]
    summaries = stages.summarize(samples)
    found = stages.detect_bottlenecks(summaries, samples)

    assert [b.stage for b in found] == ["pickup", "review"]
    assert all(b.severity == "critical" for b in found)


def test_healthy_stages_are_not_reported_as_bottlenecks():
    samples = [stages.StageSample("pickup", 600, 1, 1)]
    summaries = stages.summarize(samples)
    assert stages.detect_bottlenecks(summaries, samples) == []


def test_bottleneck_carries_evidence_of_its_worst_offenders():
    threshold = stages.STAGE_THRESHOLD_HOURS["pickup"] * 3600
    samples = [
        stages.StageSample("pickup", threshold * 10, 1, 101),
        stages.StageSample("pickup", threshold * 8, 2, 102),
        stages.StageSample("pickup", threshold * 6, 3, 103),
    ]
    summaries = stages.summarize(samples)
    bottleneck = stages.detect_bottlenecks(summaries, samples)[0]

    assert bottleneck.evidence_pr_numbers == [101, 102, 103]
