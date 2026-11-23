"""Residual scene parity is independent of the optional Cairo runtime."""

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from direct_residual_figures import PALETTE, scene, ticks


def packet(residual=12.):
    return {
        "rows": {
            "fitted_c": [
                dict(receiver=1, channel=1, norad=6, time_s=14., residual_hz=residual),
                dict(receiver=1, channel=1, norad=2, time_s=20., residual_hz=-10.),
                dict(receiver=1, channel=1, norad=6, time_s=11., residual_hz=5.),
            ],
            "c0": [dict(receiver=1, channel=1, norad=1, time_s=31., residual_hz=500.)],
        },
        "observations": [dict(receiver=1, channel=1) for _ in range(4)],
    }


def test_scene_preserves_series_order_limits_labels_and_empty_lanes():
    charts = scene(packet(), "Saved run")
    assert tuple(charts) == ("ch1-4-residuals", "ch5-8-residuals")
    assert [len(chart["axes"]) for chart in charts.values()] == [8, 8]
    left, right = charts["ch1-4-residuals"]["axes"][:2]
    assert left["title"] == "RX1 CH1 · 3/4 associated"
    assert left["xlim"] == (0., 300.)
    assert left["ylim"] == (-11.1, 13.1)
    assert tuple(color for color, _ in left["series"]) == PALETTE[:2]
    np.testing.assert_array_equal(left["series"][0][1], [[20., -10.]])
    np.testing.assert_array_equal(left["series"][1][1], [[14., 12.], [11., 5.]])
    assert right["title"] == "RX2 CH1 · 0/0 associated"
    assert all(a.shape == (0, 2) for _, a in right["series"])
    assert right["ylim"] == pytest.approx((-.055, .055))


def test_scene_rejects_nonfinite_residual_and_keeps_bounded_ticks():
    with pytest.raises(ValueError, match="Unsupported residual"):
        scene(packet(np.nan), "Nonfinite")
    assert ticks((0., 300.), 9) == tuple((50.*i, str(50*i)) for i in range(7))
    assert ticks((-20., 20.), 5) == ((-20., "−20"), (-10., "−10"), (0., "0"), (10., "10"), (20., "20"))
