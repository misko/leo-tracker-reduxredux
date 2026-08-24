from __future__ import annotations

import pytest

from tools import report_recent_three_continuity_tle as tool


def test_holm_adjustment_preserves_input_order_and_monotonic_rank() -> None:
    raw = [0.5853658537, 0.0243902439, 0.0731707317, 0.0731707317]

    adjusted = tool.holm_adjusted_pvalues(raw)

    assert adjusted == pytest.approx([0.5853658537, 0.0975609756, 0.2195121951, 0.2195121951])
    assert all(value >= source for value, source in zip(adjusted, raw, strict=True))


@pytest.mark.parametrize("values", [[-0.01], [1.01], [float("nan")], [float("inf")]])
def test_holm_adjustment_rejects_invalid_pvalues(values: list[float]) -> None:
    with pytest.raises(ValueError, match="p-values"):
        tool.holm_adjusted_pvalues(values)


def test_holm_adjustment_accepts_empty_family() -> None:
    assert tool.holm_adjusted_pvalues([]) == []


def test_fisher_exact_greater_matches_small_closed_form_tables() -> None:
    assert tool.fisher_exact_greater(7, 2, 1, 36) == pytest.approx(5.139253949335579e-06)
    assert tool.fisher_exact_greater(2, 1, 0, 13) == pytest.approx(0.025)


@pytest.mark.parametrize("table", [(-1, 1, 1, 1), (0, 0, 0, 0)])
def test_fisher_exact_greater_rejects_invalid_tables(table: tuple[int, int, int, int]) -> None:
    with pytest.raises(ValueError, match="contingency"):
        tool.fisher_exact_greater(*table)


def test_aggregate_scalar_time_null_keeps_common_shifts_clustered_by_dwell() -> None:
    def track(true_error: float, shifted: tuple[float, float]) -> dict[str, object]:
        return {
            "match": {
                "best_absolute_rate_error_hz_s": true_error,
                "null_controls": [
                    {"time_shift_s": -30.0, "best_absolute_rate_error_hz_s": shifted[0]},
                    {"time_shift_s": 30.0, "best_absolute_rate_error_hz_s": shifted[1]},
                ],
            }
        }

    source = {
        "dwells": [
            {"top_tracks": [track(1, (4, 5)), track(2, (5, 6)), track(3, (6, 7))]},
            {"top_tracks": [track(2, (7, 8)), track(3, (8, 9)), track(4, (9, 10))]},
            {"top_tracks": [track(3, (10, 11)), track(4, (11, 12)), track(5, (12, 13))]},
        ]
    }

    result = tool.aggregate_scalar_time_null(source)

    assert result["time_shifts_s"] == [-30.0, 30.0]
    assert result["statistics"]["track_median_error_hz_s"] == {
        "true_time_value_hz_s": 3.0,
        "null_median_hz_s": 8.5,
        "best_null_hz_s": 8.0,
        "true_time_rank_among_true_and_null": 1,
    }
    assert result["statistics"]["dwell_clustered_median_then_mean_error_hz_s"][
        "true_time_value_hz_s"
    ] == pytest.approx(3.0)


def test_aggregate_scalar_time_null_rejects_wrong_cohort_shape() -> None:
    with pytest.raises(ValueError, match="exactly three"):
        tool.aggregate_scalar_time_null({"dwells": []})
