"""Guard evaluation boundaries and differing simulated/raw CFO alias policies."""

import numpy as np
from review_audit import events, planted_recovery


def test_simulated_decisions_wrap_cfo_but_exclude_threshold_ties():
    detected, joint = events(
        np.array([1.0, 2.0, 2.0]), np.array([0.0, 1 / 4.4e-6 + 500.0, 1100.0]), np.zeros(3), 1.0
    )
    np.testing.assert_array_equal(detected, [False, True, True])
    np.testing.assert_array_equal(joint, [False, True, False])


def test_raw_recovery_wraps_epoch_but_never_accepts_cfo_alias():
    config = {
        "injections": {"epoch_sample": 137, "cfo_hz": 57000},
        "epoch_recovery_tolerance_s": 4.4e-6,
        "cfo_recovery_tolerance_hz": 5000,
    }
    candidate = {"epoch_sample": 137 + 10000, "seed_cfo_hz": 57000, "cfo_hz": 1 / 4.4e-6}
    recovered = planted_recovery(candidate, 7500000, config)
    assert recovered["timing_recovered"]
    assert not recovered["cfo_recovered"]
    assert not recovered["joint_recovered"]
