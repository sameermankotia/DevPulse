"""Small statistics helpers shared by the analytics services."""

from __future__ import annotations

import math
from collections.abc import Sequence


def percentile(values: Sequence[float], p: float) -> float | None:
    """Linear-interpolated percentile. `p` is 0-100. Returns None for empty input."""
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError("percentile must be between 0 and 100")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (p / 100) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def median(values: Sequence[float]) -> float | None:
    return percentile(values, 50)


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def trend_ratio(current: float | None, previous: float | None) -> float | None:
    """Signed fractional change from `previous` to `current`.

    0.25 means current is 25% higher. Returns None when either side is missing
    or the baseline is zero, since a ratio against zero carries no information.
    """
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous
