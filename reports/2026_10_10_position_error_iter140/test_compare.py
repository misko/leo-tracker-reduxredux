import runpy
from pathlib import Path

import numpy as np
from compare import compare


def test_four_matched_starts_without_common_model_zero_archive_gate():
    api = runpy.run_path(
        str(
            Path(__file__).resolve().parent.parent
            / "2026_10_10_position_error_iter133/test_compare.py"
        )
    )
    model, archive, _ = api["fixture"]()
    endpoints = archive["stages"]["B7"]
    # Historical zero-c belongs to another model; it must not block fresh fits.
    endpoints["zero-c"]["objective"] = -999999
    projection = dict(operational={a: dict(fit=f) for a, f in endpoints.items()})
    calls = []

    def fit(candidate, vector, clock, arm):
        calls.append((vector.copy(), clock.copy(), arm))
        np.testing.assert_array_equal(candidate.precision, model.precision)
        vector[:] = 999
        if len(calls) == 3:
            raise ValueError("preserve failed attempt")
        return dict(converged=True)

    result = compare(model, projection, fit)
    assert result["status"] == "attempt-failed" and len(calls) == 4
    for vector, clock, arm in calls:
        expected = endpoints["fitted-c"]["vector"].copy()
        if arm == "zero-c":
            expected[6] = 0
            assert np.all(clock[-2:] == 0)
        np.testing.assert_array_equal(vector, expected)
    assert result["attempts"]["phase"]["zero-c"]["qualified"]
    assert result["archive"]["zero-c"]["objective"] == -999999
