"""Preserve folded orbit scene inputs and qualifying figure bounds."""

from pathlib import Path
import sys

import numpy as np
import pytest

from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from direct_orbit_figures import geometry, lane_ticks, legend_columns, scene


def lanes():
    orbit = OrbitCurve("42", (0., 30., 60.), (850., 110000., 200000.))
    return tuple(
        OrbitLane(
            f"RX{receiver}", f"CH{channel}",
            (OrbitPeak("selected", 10., 130000., "42"), OrbitPeak("loose", 12., 1234.)),
            (orbit,),
        )
        for channel in range(1, 9) for receiver in (1, 2)
    )


def test_band_scene_retains_folded_peaks_and_real_curve_discontinuity():
    plot = scene(lanes(), title="Original fitted-c plot", alias_period_hz=227272.7272727)["ch1-4"]
    first = plot["rows"][0]
    assert first["titles"] == (
        "RX1 · CH1 · all 2 · 1 associated + 1 unassociated",
        "RX1 · CH1 · unassociated only: 1/2",
    )
    assert plot["headings"][1] == "8/16 associated top-one passing GLRT windows · 8 unassociated"
    assert [x[0] for x in plot["legend"]] == ["Unassociated", "42"]
    np.testing.assert_allclose(first["associated"][0][1], [[10., -97.2727272727]], rtol=0., atol=1e-10)
    np.testing.assert_allclose(first["loose"], [[12., 1.234]], rtol=0., atol=1e-10)
    assert np.isnan(first["curves"][0][1][2]).all()


def test_geometry_preserves_axis_and_output_extent():
    plot = scene(lanes(), title="Original fitted-c plot", alias_period_hz=227272.7272727)["ch5-8"]
    height, axes = geometry(plot)
    assert height == 3022
    assert len(axes) == 8
    x, y = lane_ticks(plot, axes[-1])
    assert [value for value, _ in x] == list(range(0, 301, 50))
    assert [label for _, label in y] == ["−100", "−50", "0", "50", "100"]


def test_empty_band_and_invalid_period_are_ineligible():
    with pytest.raises(ValueError, match="at least one"):
        scene(lanes()[:8], title="Missing high channels", alias_period_hz=227272.7272727)
    with pytest.raises(ValueError, match="wrapped frequency"):
        scene(lanes(), title="Unsupported frequency", alias_period_hz=0.)


def test_legend_reserves_width_for_longest_label_in_each_column():
    entries = [("Unassociated", None), ("63717", None), ("63841", None)]
    measure = lambda label, _: len(label) * 10
    (start, _), (middle, _), (last, _) = legend_columns(entries, measure)
    assert middle - start == 192
    assert last - middle == 122
