import importlib

import pytest

trial = importlib.import_module("reports.ALGO08.single-core-2x.solver_deployed_margin_trial")


def test_margin_crossover_binds_observation_fields_and_preserves_order():
    original = [
        dict(observation_id="one", time_s=3., measured_cfo_hz=14., fractional_margin=.017),
        dict(observation_id="two", time_s=4., measured_cfo_hz=-7., fractional_margin=.021),
    ]
    candidate = [dict(row, fractional_margin=.039) for row in original[::-1]]
    assert trial.matched_margins(original, candidate) == original[::-1]
    assert all(row["fractional_margin"] == .039 for row in candidate)

    changed = [dict(candidate[0], measured_cfo_hz=-7.00000001), candidate[1]]
    with pytest.raises(ValueError, match="observations do not match"):
        trial.matched_margins(original, changed)
    with pytest.raises(ValueError, match="Duplicate winning observation"):
        trial.matched_margins(original, [candidate[0], candidate[0]])
