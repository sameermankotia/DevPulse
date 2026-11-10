import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_health_reports_database_and_llm_state(client: AsyncClient):
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["llm_configured"] is False


async def test_demo_mode_seeds_a_browsable_dataset(client: AsyncClient):
    repositories = (await client.get("/api/v1/repositories")).json()
    assert len(repositories) == 4
    assert all(r["full_name"].startswith("northwind/") for r in repositories)


async def test_snapshot_returns_all_four_dora_metrics(
    client: AsyncClient, repository_id: int
):
    snapshot = (
        await client.get(f"/api/v1/repositories/{repository_id}/snapshot?window_days=30")
    ).json()

    keys = {m["key"] for m in snapshot["metrics"]}
    assert keys == {
        "deployment_frequency",
        "lead_time",
        "change_failure_rate",
        "time_to_restore",
    }
    assert snapshot["pull_request_count"] > 0
    assert len(snapshot["stages"]) == 5


async def test_snapshot_stage_shares_sum_to_one(client: AsyncClient, repository_id: int):
    snapshot = (
        await client.get(f"/api/v1/repositories/{repository_id}/snapshot")
    ).json()
    total = sum(s["share_of_pipeline"] for s in snapshot["stages"])
    assert total == pytest.approx(1.0, abs=1e-6)


async def test_pull_requests_carry_stage_breakdowns(
    client: AsyncClient, repository_id: int
):
    rows = (
        await client.get(f"/api/v1/repositories/{repository_id}/pull-requests?limit=10")
    ).json()
    assert rows
    assert all("stages" in row for row in rows)
    assert any(row["lead_time_seconds"] for row in rows)


async def test_unknown_repository_is_a_404_with_a_useful_message(client: AsyncClient):
    response = await client.get("/api/v1/repositories/9999/snapshot")
    assert response.status_code == 404
    assert "9999" in response.json()["detail"]


async def test_window_outside_supported_range_is_rejected(
    client: AsyncClient, repository_id: int
):
    base = f"/api/v1/repositories/{repository_id}/snapshot"
    assert (await client.get(f"{base}?window_days=2")).status_code == 422
    assert (await client.get(f"{base}?window_days=900")).status_code == 422


async def test_tracking_requires_a_valid_owner_repo_pair(client: AsyncClient):
    response = await client.post("/api/v1/repositories", json={"full_name": "not-a-repo"})
    assert response.status_code == 422


async def test_insights_without_a_key_explains_how_to_configure_it(
    client: AsyncClient, repository_id: int
):
    response = await client.post(f"/api/v1/repositories/{repository_id}/insights")
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]
