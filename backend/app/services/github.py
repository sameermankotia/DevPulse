"""Thin async GitHub REST client covering the delivery surface we ingest.

Handles pagination, secondary rate limits, and the 403/429 retry dance. It
deliberately returns plain dicts: mapping into ORM objects is the ingestor's
job, which keeps the transport layer easy to record and replay in tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


class GitHubError(RuntimeError):
    pass


class GitHubRateLimited(GitHubError):
    """Raised when GitHub asks us to back off; carries the wait in seconds."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class GitHubClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.github_token:
            raise GitHubError("GITHUB_TOKEN is required to sync from GitHub")
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.github_api_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Authorization": f"Bearer {settings.github_token}",
                "User-Agent": "devpulse-sync",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, GitHubRateLimited)),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        response = await self._client.get(path, params=params)

        if response.status_code in (403, 429):
            remaining = response.headers.get("x-ratelimit-remaining")
            # A 403 with budget left is a secondary limit, not a permissions problem.
            if remaining == "0" or "retry-after" in response.headers:
                wait = float(response.headers.get("retry-after", 60))
                log.warning("github.rate_limited", path=path, retry_after=wait)
                await asyncio.sleep(min(wait, 60))
                raise GitHubRateLimited(wait)

        if response.status_code >= 400:
            raise GitHubError(f"GET {path} -> {response.status_code}: {response.text[:300]}")
        return response

    async def _paginate(
        self, path: str, params: dict[str, Any] | None = None, limit: int | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        page_params = dict(params or {})
        page_params.setdefault("per_page", self._settings.github_page_size)
        page = 1
        yielded = 0

        while True:
            page_params["page"] = page
            response = await self._get(path, page_params)
            batch = response.json()
            if isinstance(batch, dict):
                # Search-style endpoints nest their results.
                batch = batch.get("items", [])
            if not batch:
                return

            for item in batch:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

            if "next" not in response.links:
                return
            page += 1

    async def get_repository(self, full_name: str) -> dict[str, Any]:
        response = await self._get(f"/repos/{full_name}")
        return response.json()

    async def list_pull_requests(
        self, full_name: str, since: datetime | None = None, limit: int | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Pull requests, newest first. Stops early once older than `since`."""
        params = {"state": "all", "sort": "updated", "direction": "desc"}
        async for pr in self._paginate(f"/repos/{full_name}/pulls", params, limit):
            if since is not None:
                updated = _parse_time(pr.get("updated_at"))
                if updated is not None and updated < since:
                    return
            yield pr

    async def get_pull_request(self, full_name: str, number: int) -> dict[str, Any]:
        """Detail view, which is the only place additions/deletions are returned."""
        response = await self._get(f"/repos/{full_name}/pulls/{number}")
        return response.json()

    async def list_reviews(self, full_name: str, number: int) -> list[dict[str, Any]]:
        return [r async for r in self._paginate(f"/repos/{full_name}/pulls/{number}/reviews")]

    async def list_commits(self, full_name: str, number: int) -> list[dict[str, Any]]:
        return [c async for c in self._paginate(f"/repos/{full_name}/pulls/{number}/commits")]

    async def list_workflow_runs(
        self, full_name: str, since: datetime | None = None, limit: int | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        params: dict[str, Any] = {}
        if since is not None:
            params["created"] = f">={since.date().isoformat()}"
        async for run in self._paginate(f"/repos/{full_name}/actions/runs", params, limit):
            yield run

    async def list_deployments(
        self, full_name: str, environment: str = "production", limit: int | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        async for deployment in self._paginate(
            f"/repos/{full_name}/deployments", {"environment": environment}, limit
        ):
            yield deployment

    async def list_deployment_statuses(
        self, full_name: str, deployment_id: int
    ) -> list[dict[str, Any]]:
        return [
            s
            async for s in self._paginate(
                f"/repos/{full_name}/deployments/{deployment_id}/statuses"
            )
        ]


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
