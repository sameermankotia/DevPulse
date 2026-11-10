"""Scheduled sync: refreshes every tracked repository from GitHub.

Run as a one-shot process (a Kubernetes CronJob in production). Each repository
is synced independently so one failure does not abort the rest; the process
exits non-zero if any repository failed, so the job is retried.
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from app.core.database import dispose_engine, get_session_factory
from app.core.logging import configure_logging, get_logger
from app.services import analytics
from app.services.github import GitHubClient
from app.services.ingest import Ingestor

log = get_logger(__name__)


async def sync_all() -> int:
    """Returns the number of repositories that failed to sync."""
    settings = get_settings()
    if not settings.github_token:
        log.error("sync.no_token", reason="GITHUB_TOKEN is not configured")
        return 1

    factory = get_session_factory()
    async with factory() as session:
        repositories = list(await analytics.list_repositories(session))

    if not repositories:
        log.info("sync.nothing_tracked")
        return 0

    failures = 0
    async with GitHubClient(settings) as client:
        for repo in repositories:
            # A fresh session per repository keeps one failure from poisoning
            # the transaction the next repository would write into.
            async with factory() as session:
                try:
                    run = await Ingestor(session, client, settings).sync_repository(
                        repo.full_name
                    )
                    log.info(
                        "sync.completed",
                        repository=repo.full_name,
                        pull_requests=run.pull_requests_synced,
                        runs=run.runs_synced,
                        deployments=run.deployments_synced,
                    )
                except Exception as exc:
                    failures += 1
                    log.error("sync.failed", repository=repo.full_name, error=str(exc))

    return failures


async def main() -> int:
    configure_logging()
    try:
        return await sync_all()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
