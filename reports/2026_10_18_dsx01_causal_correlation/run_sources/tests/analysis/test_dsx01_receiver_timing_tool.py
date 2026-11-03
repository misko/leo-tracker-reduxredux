"""UTC receiver alignment must preserve the orbital phase/Earth rotation distinction."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_receiver_timing")
    finally:
        sys.path.remove(path)


def test_relative_utc_is_symmetric_and_agrees_with_dense_utc_shift(tool):
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    p = tool.TimingFamilies(scan, seed, "shared_phase", False, (0, 0), sigma=0.5)
    np.testing.assert_allclose(p.residual(p.initial)[:-1], base.residual(base.initial))
    x = p.initial.copy()
    x[-1] = 1
    f, e = p.predicted(x)
    for i, block in zip(p.members, p.slices, strict=True):
        shift = -0.25 if scan.tracks[i]["receiver"] == 1 else 0.25
        ff, ee = phase_frequency_grid(scan.sky, scan.tracks[i]["times"] + shift, 37.906, -122.545)
        np.testing.assert_allclose(f[block], ff[0], atol=1e-8)
        np.testing.assert_allclose(e[block], ee[0], atol=1e-10)
        wrong, _ = phase_frequency_grid(
            scan.sky, scan.tracks[i]["times"], 37.906, -122.545, phase_seconds=shift
        )
        assert max(abs(f[block] - wrong[0])) > 0.001


def test_timing_and_radio_priors_remain_separate_after_coordinate_transform(tool):
    scan, seed = problem_inputs()
    p = tool.timing_problem(scan, seed, "shared_phase", True, (0, 0), sigma=0.1)
    x = p.initial.copy()
    x[-1] = 0.6
    x[p.pairs[0][0]] = 0.8
    r = p.residual(x)
    start = len(r) - 1 - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [0.8, 0, 0, 0])
    assert r[-1] == pytest.approx(0.6)
    state = p.association_state(x)
    assert state["rx_time_difference_s"] == pytest.approx(0.06)
    np.testing.assert_allclose(state["beta"][4:6] / 150, [8, 8])
