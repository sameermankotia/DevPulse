import pytest
from pydantic import ValidationError

from app.services.insights import InsightPayload, _extract_json, digest_hash


def test_extract_json_handles_a_bare_object():
    assert _extract_json('{"headline": "x"}') == {"headline": "x"}


def test_extract_json_strips_markdown_fences():
    raw = '```json\n{"headline": "fenced"}\n```'
    assert _extract_json(raw)["headline"] == "fenced"


def test_extract_json_recovers_an_object_wrapped_in_prose():
    raw = 'Here is the analysis:\n{"headline": "wrapped"}\nHope that helps.'
    assert _extract_json(raw)["headline"] == "wrapped"


def test_extract_json_raises_when_there_is_no_object():
    with pytest.raises(ValueError):
        _extract_json("no json at all")


def test_digest_hash_is_order_independent():
    # Key ordering must not invalidate the cache, or every request regenerates.
    assert digest_hash({"a": 1, "b": 2}) == digest_hash({"b": 2, "a": 1})


def test_digest_hash_changes_with_content():
    assert digest_hash({"a": 1}) != digest_hash({"a": 2})


def test_payload_rejects_an_invalid_impact_level():
    with pytest.raises(ValidationError):
        InsightPayload.model_validate(
            {
                "headline": "h",
                "summary": "s",
                "recommendations": [
                    {
                        "title": "t",
                        "stage": "pickup",
                        "impact": "enormous",
                        "effort": "low",
                        "rationale": "r",
                        "expected_effect": "e",
                    }
                ],
            }
        )


def test_payload_tolerates_a_minimal_response():
    payload = InsightPayload.model_validate({"headline": "h", "summary": "s"})
    assert payload.confidence == "medium"
    assert payload.recommendations == []
