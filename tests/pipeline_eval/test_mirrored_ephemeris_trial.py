from importlib import import_module

import numpy as np


trial = import_module("reports.ALGO08.single-core-2x.mirrored_ephemeris_trial")


def test_common_projection_removes_identical_nuisances_in_both_orbit_models():
    design = np.column_stack((np.ones(5), np.arange(5.)))
    values = np.column_stack((np.arange(5.) ** 2, np.arange(5.) ** 3))
    offset = design @ np.array([[15., -3.], [4., 8.]])
    first, rank = trial.project(design, values)
    second, _ = trial.project(design, values + offset)
    assert rank == 2
    np.testing.assert_allclose(first, second, atol=1e-13)


def test_orbit_update_alone_can_invert_a_noiseless_face_decision():
    shift = np.array([1., -1., 1., -1.])
    causal = np.column_stack((np.zeros_like(shift), .5 * shift, shift))
    later = causal + .75 * shift[:, None]
    result = trial.face_comparison(causal, later)
    assert result["signature_hz"] == {"causal": 1., "later": 1.}
    assert result["midpoint_error_along_later_signature_m"] == 150.
    assert result["noiseless_control_hz"] == {"A": [0., 1.], "B": [1., 0.]}
    assert result["noiseless_causal_hz"] == {"A": [.75, .25], "B": [1.75, .75]}


def test_simultaneous_receiver_pairs_keep_orbit_and_rf_lanes_fixed():
    first, second = trial.simultaneous_pairs(
        owners=[123, 123, 125, 123, 125], channels=[1, 1, 1, 2, 2],
        times=[2., 2., 2., 2., 2.], receivers=[1, 2, 1, 2, 2],
    )
    assert first.tolist() == [0] and second.tolist() == [1]
