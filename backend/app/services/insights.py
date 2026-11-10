"""LLM-generated recommendations, served through OpenRouter.

The model is given only the numeric digest of a snapshot -- never raw titles or
author names -- and must return a fixed JSON shape. Responses are validated
against a Pydantic schema and cached by a hash of their input digest, so an
unchanged dataset never pays for a second generation.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models import Insight, Repository
from app.services.analytics import DeliverySnapshot, digest_for_llm

log = get_logger(__name__)

SYSTEM_PROMPT = """\
You are a delivery performance analyst embedded with a software engineering org.
You are given an anonymised, numeric digest of one repository's delivery data for
a time window: DORA metrics with their performance bands, per-stage percentiles
for the pull request lifecycle, and CI health.

Your job is to explain where delivery time is actually being lost and recommend
specific changes, including where AI-assisted workflows would and would not help.

Rules:
- Ground every claim in a number from the digest. Quote the number.
- Rank by impact: a queue stage (nobody working, change just waiting) is cheaper
  to fix than a work stage, so prefer it when the overage is comparable.
- Be concrete. "Add a review SLA of 4 business hours with a bot reminder" beats
  "improve review culture".
- Recommend AI assistance only where the digest supports it. Long coding stages
  and large PRs suit AI-assisted authoring and review; a long merge queue is an
  automation problem, not a model problem. Say so when AI is the wrong tool.
- If the sample count for a stage is under 5, say the signal is weak rather than
  drawing a conclusion from it.
- Write for an engineering lead reading a dashboard, not for a machine. Never
  print a field name from the digest: say "change failure rate", not
  "change_failure_rate"; "median PR size", not "median_pr_size_lines". Give rates
  as percentages ("13%", not "0.1282") and durations in hours or days ("30h",
  not "29.72h" unless the precision matters).
- No preamble, no apology. Return only the JSON object described by the schema.
"""

RESPONSE_SCHEMA_HINT = """\
Return a single JSON object with exactly this shape:

{
  "headline": "one sentence naming the single biggest source of lost time",
  "summary": "2-3 sentences of context, every claim tied to a number",
  "confidence": "high" | "medium" | "low",
  "recommendations": [
    {
      "title": "short imperative action",
      "stage": "code" | "pickup" | "review" | "rework" | "release" | "ci" | "process",
      "impact": "high" | "medium" | "low",
      "effort": "low" | "medium" | "high",
      "rationale": "why, quoting the numbers it rests on",
      "expected_effect": "the metric that should move and roughly how far",
      "ai_assisted": true | false,
      "ai_note": "how AI helps here, or why it does not apply"
    }
  ],
  "risks": ["anything in the data that could mislead, e.g. small samples"]
}

Return between 3 and 5 recommendations.
"""


class Recommendation(BaseModel):
    title: str
    stage: str
    impact: Literal["high", "medium", "low"]
    effort: Literal["low", "medium", "high"]
    rationale: str
    expected_effect: str
    ai_assisted: bool = False
    ai_note: str = ""


class InsightPayload(BaseModel):
    headline: str
    summary: str
    confidence: Literal["high", "medium", "low"] = "medium"
    recommendations: list[Recommendation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class InsightsUnavailable(RuntimeError):
    """Raised when no OpenRouter credential is configured."""


def digest_hash(digest: dict[str, Any]) -> str:
    canonical = json.dumps(digest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response.

    Models wrap JSON in prose or fences often enough that a bare json.loads is
    not reliable, so fall back to the outermost balanced braces.
    """
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model response")
    return json.loads(stripped[start : end + 1])


class InsightsService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings
        if not settings.openrouter_api_key:
            raise InsightsUnavailable("OPENROUTER_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            # OpenRouter attributes requests to an app via these two headers.
            "HTTP-Referer": settings.openrouter_app_url,
            "X-Title": settings.openrouter_app_title,
        }

        client = self._client or httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            timeout=httpx.Timeout(settings.openrouter_timeout_seconds, connect=10.0),
        )
        try:
            response = await client.post("/chat/completions", json=body, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"OpenRouter returned {response.status_code}: {response.text[:400]}"
                )
            return response.json()
        finally:
            if self._client is None:
                await client.aclose()

    async def generate(self, snapshot: DeliverySnapshot) -> tuple[InsightPayload, dict[str, Any]]:
        digest = digest_for_llm(snapshot)
        user_content = (
            f"{RESPONSE_SCHEMA_HINT}\n\nDigest for {snapshot.repository.full_name} "
            f"over the last {snapshot.window_days} days:\n\n"
            f"{json.dumps(digest, indent=2)}"
        )

        body = {
            "model": self._settings.openrouter_model,
            "temperature": 0.2,
            "max_tokens": 4000,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }

        started = time.perf_counter()
        raw = await self._post(body)
        latency_ms = (time.perf_counter() - started) * 1000

        content = raw["choices"][0]["message"]["content"]
        try:
            payload = InsightPayload.model_validate(_extract_json(content))
        except (ValueError, ValidationError) as exc:
            # One repair attempt: hand the model its own output and the error.
            log.warning("insights.parse_failed", error=str(exc)[:200])
            body["messages"].extend(
                [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"That did not validate: {exc}. Return only the corrected "
                            "JSON object, with no commentary."
                        ),
                    },
                ]
            )
            raw = await self._post(body)
            latency_ms = (time.perf_counter() - started) * 1000
            content = raw["choices"][0]["message"]["content"]
            payload = InsightPayload.model_validate(_extract_json(content))

        usage = raw.get("usage") or {}
        meta = {
            "model": raw.get("model", self._settings.openrouter_model),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "latency_ms": latency_ms,
            "digest_hash": digest_hash(digest),
        }
        return payload, meta


async def get_cached(
    session: AsyncSession, repo: Repository, digest: dict[str, Any], window_days: int
) -> Insight | None:
    return await session.scalar(
        select(Insight)
        .where(
            Insight.repository_id == repo.id,
            Insight.window_days == window_days,
            Insight.digest_hash == digest_hash(digest),
        )
        .order_by(Insight.created_at.desc())
        .limit(1)
    )


async def latest(session: AsyncSession, repo: Repository) -> Insight | None:
    return await session.scalar(
        select(Insight)
        .where(Insight.repository_id == repo.id)
        .order_by(Insight.created_at.desc())
        .limit(1)
    )


async def generate_and_store(
    session: AsyncSession,
    settings: Settings,
    snapshot: DeliverySnapshot,
    force: bool = False,
) -> Insight:
    digest = digest_for_llm(snapshot)

    if not force:
        cached = await get_cached(session, snapshot.repository, digest, snapshot.window_days)
        if cached is not None:
            return cached

    payload, meta = await InsightsService(settings).generate(snapshot)

    insight = Insight(
        repository_id=snapshot.repository.id,
        window_days=snapshot.window_days,
        model=meta["model"],
        digest_hash=meta["digest_hash"],
        payload=payload.model_dump(),
        prompt_tokens=meta.get("prompt_tokens"),
        completion_tokens=meta.get("completion_tokens"),
        latency_ms=meta.get("latency_ms"),
    )
    session.add(insight)
    await session.commit()
    await session.refresh(insight)
    return insight
