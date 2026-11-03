"""RF coefficient controls preserve the zero-c arm and native-Hz calibration."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_separate_rf_calibration")
    finally:
        sys.path.remove(path)


def test_zero_c_disables_every_RF_coefficient_and_matches_original_loss(tool):
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    for mode in ("global", "receiver", "band"):
        p = tool.SeparateRFFamilies(scan, seed, "shared_phase", False, (0, 0), mode=mode)
        assert len(p.initial) == len(base.initial)
        np.testing.assert_allclose(p.residual(p.initial), base.residual(base.initial))


def test_receiver_RF_contrast_is_native_hz_and_has_opposite_RX_sign(tool):
    scan, seed = problem_inputs()
    p = tool.SeparateRFFamilies(scan, seed, "shared_phase", True, (0, 0), mode="receiver")
    x = p.initial.copy()
    x[-1] = 0.1
    df = p.predicted(x)[0] - p.predicted(p.initial)[0]
    centres = tool.rf_centres(scan.tracks)
    for t, block in zip(scan.tracks, p.slices, strict=True):
        sign = -1 if t["receiver"] == 1 else 1
        expected = sign * 1000 * (t["rf_hz"] - centres[t["receiver"], int(t["channel"] > 4)]) / 1e9
        np.testing.assert_allclose(df[block] * t["rf_hz"] / 11.5e9, expected, atol=1e-8)


def test_group_contrasts_have_no_common_mode_and_priors_stay_separate(tool):
    scan, seed = problem_inputs()
    p = tool.rf_problem(scan, seed, "shared_phase", True, (0, 0), mode="band")
    np.testing.assert_allclose(p.rf_contrasts.sum(axis=0), 0)
    np.testing.assert_allclose(p.rf_contrasts.T @ p.rf_contrasts, np.eye(3))
    x = p.initial.copy()
    x[-3:] = [0.2, 0.3, 0.4]
    x[p.pairs[0][0]] = 0.5
    r = p.residual(x)
    np.testing.assert_allclose(r[:3], [0.2, 0.3, 0.4])
    start = len(r) - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [0.5, 0, 0, 0])
