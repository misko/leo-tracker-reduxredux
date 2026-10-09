import numpy as np
from policy import timing_metric, trigger


def test_metric_uses_timing_parameters_not_reference_error():
    row = dict(vector=[0] * 8 + [2, 2], converged=True, error_km=100)
    a = timing_metric(row)
    row["error_km"] = 0
    assert timing_metric(row) == a and a["normalized_energy"] == 1
    # Orthonormal basis changes preserve energy.
    row["vector"] = [0] * 8 + [np.sqrt(8), 0]
    assert abs(timing_metric(row)["normalized_energy"] - 1) < 1e-14


def test_missing_or_failed_arm_triggers_shared_search():
    good = timing_metric(dict(vector=[0] * 10, converged=True))
    assert not trigger(dict(a=good, b=good), 3)
    assert trigger(dict(a=good, b=timing_metric(None)), 3)
    failed = timing_metric(dict(vector=[0] * 10, converged=False))
    assert trigger(dict(a=good, b=failed), 3)


def test_fixed_threshold_not_reference_error_drives_trigger():
    metric = timing_metric(dict(vector=[0] * 8 + [4, 4], converged=True))
    assert trigger(dict(a=metric, b=metric), 3)
    assert not trigger(dict(a=metric, b=metric), 5)
