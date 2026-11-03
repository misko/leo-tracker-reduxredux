import numpy as np
import pytest
from evaluate import common_score, coordinates, ecef, summarize


def test_failed_fit_does_not_improve_success_median():
    rows = [
        {
            "dataset": "DS11",
            "model": "anchors",
            "success": success,
            "attempted": attempted,
            "reference_error_km": error,
            "runtime_s": runtime,
        }
        for success, attempted, error, runtime in [
            (True, True, 8.0, 1),
            (False, True, 0.0, 3),
            (False, False, None, None),
        ]
    ]
    row = next(row for row in summarize(rows) if row["model"] == "anchors")
    assert row["requested_scans"] == 3
    assert row["attempted_scans"] == 2
    assert row["pending_scans"] == 1
    assert row["successful_scans"] == 1
    assert row["median_error_km"] == 8


def test_reference_metric_uses_same_zero_altitude_convention():
    np.testing.assert_allclose(coordinates([0, 0]), [38.5816, -121.4944])
    assert np.linalg.norm(ecef(0, 0)) == pytest.approx(6378.137)


def test_common_score_counts_alternatives_once_and_penalizes_invisibility():
    class Data:
        group = np.array([4, 4, 9])
        measured = np.array([0.0, 100.0, 0.0])

        def predict(self, parameters):
            return np.zeros((3, 2)), np.array([[True, True], [True, True], [False, False]])

    loss, matched = common_score(Data(), np.zeros(70))
    assert matched == 1
    assert loss == pytest.approx(200**2 * (np.sqrt(101) - 1))
