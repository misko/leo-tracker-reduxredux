import math
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("topology_m0", HERE / "calibrate_topology_m0.py")
M0 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = M0
SPEC.loader.exec_module(M0)

ROBUST_SPEC = importlib.util.spec_from_file_location(
    "topology_m0_robust", HERE.parent / "2026_09_27_roof_location_geometry/robust_core.py"
)
ROBUST = importlib.util.module_from_spec(ROBUST_SPEC)
assert ROBUST_SPEC.loader
sys.modules[ROBUST_SPEC.name] = ROBUST
ROBUST_SPEC.loader.exec_module(ROBUST)


def test_m0_shared_identity_factors_to_d_plus_constant_with_full_denominator():
    predicted = np.array([[0., 0., 0., 0.], [0., 2., 3., 4.]])
    measured = np.zeros(4)
    train = np.array([True, False, False, False])
    candidate_east = np.array([[-1., -.5, .2, .8], [1., .5, -.2, -.8]])
    shortlist = {
        "candidate_indices": [0, 1],
        "profiled_cfo_hz": [0., 0.],
        "log_weights": [math.log(.8), math.log(.2)],
        "scale_hz": 10., "degrees_of_freedom": 2.,
    }
    rows = [
        {"observation_index": 1, "matched": True,
         "detection_logit_east0": .7, "detection_east_slope": 0.,
         "ratio_mean_east0": -.2, "ratio_east_slope": 0.,
         "log_margin_ratio_rx1_rx0": .3},
        {"observation_index": 2, "matched": False,
         "detection_logit_east0": -.4, "detection_east_slope": 0.,
         "ratio_mean_east0": 99., "ratio_east_slope": 0.,
         "log_margin_ratio_rx1_rx0": None},
        # Reserve observation index 3 deliberately has no reception row.
    ]
    variance = .5
    result = ROBUST.joint_heldout_score(
        predicted, candidate_east, measured, train, shortlist, rows,
        ratio_variance=variance,
    )
    detection_nll = np.logaddexp(0., -.7) + np.logaddexp(0., -.4)
    ratio_nll = .5 * (math.log(2 * math.pi * variance) + (.3 - (-.2))**2 / variance)
    expected_constant = (detection_nll + ratio_nll) / 3
    assert result["reserve_observations"] == 3
    assert result["reception_observations"] == 2
    assert result["scores"]["D_plus_geometry"] == pytest.approx(
        result["scores"]["D"] + expected_constant
    )
    # Changing candidate directions cannot change an M0 likelihood.
    changed = ROBUST.joint_heldout_score(
        predicted, candidate_east * 1e6, measured, train, shortlist, rows,
        ratio_variance=variance,
    )
    assert changed["scores"] == pytest.approx(result["scores"])


def test_direction_free_zero_rx_recovers_d_with_unequal_weights():
    result = ROBUST.joint_heldout_score(
        np.array([[0., 0.], [0., 5.]]), np.array([[-1., -1.], [1., 1.]]),
        np.zeros(2), np.array([True, False]),
        {"candidate_indices": [0, 1], "profiled_cfo_hz": [0., 0.],
         "log_weights": [math.log(.9), math.log(.1)],
         "scale_hz": 10., "degrees_of_freedom": 2.},
        [], ratio_variance=1.,
    )
    assert result["scores"]["D_plus_detection"] == pytest.approx(result["scores"]["D"])
    assert result["scores"]["D_plus_geometry"] == pytest.approx(result["scores"]["D"])
