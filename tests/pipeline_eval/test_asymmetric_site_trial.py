from collections import Counter

import pytest

from tools.pipeline_eval.qualification import asymmetric_site_trial as trial
from tools.pipeline_eval.qualification.independent_site_omissions import tile_distance
from tools.pipeline_eval.scoring import validate_result


def test_tile_stream_deterministic_and_centers_all_perturbed():
    boards = list(trial.generate_boards("test-capture", count=10))
    assert boards == list(trial.generate_boards("test-capture", count=10))
    assert len({tuple(point) for board in boards for point in board}) == 4 * len(boards)
    selected, receipt = trial.select_boards("test-capture", trial.ANCHOR)
    assert receipt["consumed"] >= len(selected)
    assert Counter(row[2] for row in selected) == {"containing": 3, "omitted": 3}
    for index, board, condition, _, gap in selected:
        assert (
            list(trial.generate_boards("test-capture", count=receipt["consumed"]))[index] == board
        )
        if condition == "omitted":
            assert 0.75 <= gap <= 3
            assert all(tile_distance(center, trial.ANCHOR) > 0 for center in board)


@pytest.mark.parametrize("gain, expected", [(1.0, "withheld"), (1.01, "ok")])
def test_new_policy_uses_original_fft_scale_and_matched_position(gain, expected):
    point = [40.1, -88.1]
    arm = dict(latlon=None, forced_latlon=point, rf_rms_hz=222)
    stock = dict(
        status="withheld",
        reason="weak_held_spatial_margin",
        boundary="Measured test boundary",
        metrics=dict(edge_km=1.0, null_margin_hz2=gain * trial.field.receiver.BIN_HZ**2),
        arms=dict(c0=arm, fitted_c=dict(arm)),
    )
    board = [point, [40.4, -88.6], [40.6, -88.2], [41.0, -88.0]]
    candidate, reference, interior_only, geography = trial.policy(stock, board)
    assert [r["status"] for r in (candidate, reference, interior_only, geography)] == [
        expected,
        "withheld",
        "ok",
        "ok",
    ]
    assert candidate["arms"]["c0"]["forced_latlon"] == interior_only["arms"]["c0"]["latlon"]
    assert geography["arms"]["c0"] == {"latlon": point}
    for row in (candidate, reference, interior_only, geography):
        validate_result(row)
        assert row["arms"]["fitted_c"]["status"] == "unavailable"
