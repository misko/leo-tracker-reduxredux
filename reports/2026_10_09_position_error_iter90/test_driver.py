"""Actual diagnostic-driver integration with synthetic arrays only."""

import json

import numpy as np
from audit_pairs import diagnose_pairs, json_value


def joined(ids, smooth):
    ids = np.asarray(ids, int)
    times = np.arange(len(ids), dtype=float)
    values = 7 + 0.3 * times + 12 * (2 * ids - 1)
    pairs = [
        dict(
            satellite=int(sat),
            channel=0,
            tick_ms=int(t * 1000),
            time_s=float(t),
            difference_hz=float(y),
            rx0_count=1,
            rx1_count=1,
            rx0_time_mean_s=float(t),
            rx1_time_mean_s=float(t),
        )
        for sat, t, y in zip(ids, times, values, strict=True)
    ]
    return dict(
        y_hz=values,
        satellite=ids,
        time_s=times,
        channel=np.zeros(len(ids), int),
        smooth_design=np.asarray(smooth),
        pairs=pairs,
    )


def test_empty_driver_is_serializable_explicit_noop():
    result = diagnose_pairs(joined([], np.zeros((0, 4))))
    assert result["pair_count"] == 0
    for name in ("unadjusted_shrinkage", "background_projected", "smooth_clock_projected"):
        assert result[name]["no_op"]
    assert result["smooth_clock_projected"]["attempted"] is False
    json.dumps(json_value(result), allow_nan=False)


def test_driver_insufficient_eligible_satellites_is_noop():
    ids = np.r_[np.zeros(12, int), np.ones(9, int)]
    result = diagnose_pairs(joined(ids, np.zeros((len(ids), 3))))
    assert result["pair_count"] == 21
    for name in ("background_projected", "smooth_clock_projected"):
        assert result[name]["no_op"]
        np.testing.assert_array_equal(result[name]["contrasts_hz"], [0, 0])


def test_driver_smooth_confounded_direction_has_zero_rank():
    ids = np.tile([0, 1], 20)
    smooth = np.column_stack([2 * ids - 1, np.zeros(len(ids))])
    result = diagnose_pairs(joined(ids, smooth))
    primary, sensitive = result["background_projected"], result["smooth_clock_projected"]
    assert primary["data_rank"] == 1
    assert np.max(np.abs(primary["contrasts_hz"])) > 0
    assert sensitive["data_rank"] == 0 and sensitive["no_op"]
    assert sensitive["unsupported_zero"] and sensitive["attempted"]
    np.testing.assert_array_equal(sensitive["contrasts_hz"], [0, 0])
    assert sensitive["dimensions"] == dict(rows=40, background=4, contrast=1)
    assert len(sensitive["background_columns"]) == 4
    assert sensitive["weak_modes"].shape == (2, 1)
    assert len(sensitive["residual_hz"]) == 40
    json.dumps(json_value(result), allow_nan=False)


def test_driver_redundant_smooth_columns_preserve_primary_contrast():
    ids = np.tile([0, 1], 20)
    times = np.arange(len(ids), dtype=float)
    result = diagnose_pairs(joined(ids, np.column_stack([np.ones(len(ids)), times])))
    primary, sensitive = result["background_projected"], result["smooth_clock_projected"]
    np.testing.assert_allclose(sensitive["contrasts_hz"], primary["contrasts_hz"], atol=1e-10)
    assert sensitive["background_rank"] == primary["background_rank"] == 2
    assert sensitive["data_rank"] == primary["data_rank"] == 1
