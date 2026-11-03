"""Receiver clock interaction controls using synthetic observation geometry."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import whitening


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_rf_clock")
    finally:
        sys.path.remove(path)


def problem_inputs():
    knots, times = np.arange(-20.0, 321.0, 5), np.linspace(30, 270, 31)
    position = np.array([-2400, -4700, 4300])[None, :] + knots[:, None] * [2, -3, 0.5]
    sky = dict(
        time_s=knots,
        position_km=position[None, :, :],
        velocity_km_s=np.broadcast_to([2, -3, 0.5], (1, len(knots), 3)).copy(),
    )
    tracks, rows = [], []
    for receiver in (1, 2):
        for channel, rf in ((1, 10.7e9), (4, 11.45e9)):
            key = f"R{receiver}C{channel}"
            tracks.append(
                dict(
                    key=key,
                    receiver=receiver,
                    channel=channel,
                    rf_hz=rf,
                    times=times,
                    values=np.zeros(len(times)),
                )
            )
            rows.append(
                dict(
                    component=key,
                    candidate_index=0,
                    candidate_norad=100,
                    points=len(times),
                    active_curvature=True,
                    split_at=-1,
                )
            )
    scan = SimpleNamespace(
        tracks=tracks,
        curved=list(range(4)),
        sky=sky,
        times=times,
        norads=np.array([100]),
        sigma=np.array([1.0]),
        white=[whitening(times)] * 4,
        ou=[whitening(times)] * 4,
    )
    scan.hardware = lambda t, b: (
        b[2 * (t["receiver"] - 1)] + b[4 + 2 * (t["receiver"] - 1)] * (t["times"] - 150) / 150
    )
    seed = dict(
        rows=rows,
        state=dict(beta=np.zeros(8), phases=np.zeros(1), extra={}, smooth=np.zeros((2, 11))),
    )
    return scan, seed


def test_zero_rf_drift_reproduces_original_frequency_and_projected_loss(tool):
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    clock = tool.RFClockFamilies(scan, seed, "shared_phase", False, (0, 0))
    np.testing.assert_allclose(base.predicted(base.initial)[0], clock.predicted(clock.initial)[0])
    np.testing.assert_allclose(base.residual(base.initial), clock.residual(clock.initial)[:-2])
    np.testing.assert_allclose(clock.residual(clock.initial)[-2:], 0)


def test_rf_time_term_is_in_native_hz_and_never_leaks_between_receivers(tool):
    scan, seed = problem_inputs()
    p = tool.RFClockFamilies(scan, seed, "shared_phase", True, (0, 0), sigma=75)
    x = p.initial.copy()
    x[-2] = 2  # RX1 coefficient: 150 Hz / GHz over the normalized scan interval.
    delta = p.predicted(x)[0] - p.predicted(p.initial)[0]
    for t, block in zip(scan.tracks, p.slices, strict=True):
        native = delta[block] * t["rf_hz"] / 11.5e9
        if t["receiver"] == 2:
            np.testing.assert_allclose(native, 0, atol=1e-8)
        else:
            expected = 150 * ((t["rf_hz"] - 11.075e9) / 1e9) * (t["times"] - 150) / 150
            np.testing.assert_allclose(native, expected, atol=1e-8)
