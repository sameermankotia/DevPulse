import pytest

from app.services.stats import mean, median, percentile, trend_ratio


def test_percentile_interpolates_between_ranks():
    assert percentile([0, 10], 50) == 5
    assert percentile([0, 10, 20, 30], 50) == 15


def test_percentile_endpoints():
    values = [4, 1, 3, 2]
    assert percentile(values, 0) == 1
    assert percentile(values, 100) == 4


def test_percentile_single_value():
    assert percentile([7], 90) == 7


def test_percentile_empty_is_none():
    assert percentile([], 50) is None
    assert median([]) is None
    assert mean([]) is None


def test_percentile_rejects_out_of_range():
    with pytest.raises(ValueError):
        percentile([1, 2], 101)


def test_trend_ratio_signs():
    assert trend_ratio(12, 10) == pytest.approx(0.2)
    assert trend_ratio(8, 10) == pytest.approx(-0.2)


def test_trend_ratio_guards_zero_baseline():
    # A ratio against zero carries no information, so it must not be invented.
    assert trend_ratio(5, 0) is None
    assert trend_ratio(None, 10) is None
