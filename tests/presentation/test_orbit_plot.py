import io

import numpy as np
import pytest

from leo.presentation.orbit_plot import (
    OrbitCurve,
    OrbitLane,
    OrbitPeak,
    _curve_samples,
    make_orbit_plot,
)


def lane(receiver="RX0"):
    return OrbitLane(
        receiver,
        "CH1",
        (OrbitPeak("a", 0, 80, "123"), OrbitPeak("b", 1, 20), OrbitPeak("c", 2, 120, "123")),
        (OrbitCurve("123", (0, 1, 2), (80, 100, 120)),),
    )


def test_counts_and_no_unassigned_duplication():
    figure = make_orbit_plot((lane(),), title="Test", alias_period_hz=200)
    left, right = figure.axes
    assert sum(len(item.get_offsets()) for item in left.collections) == 3
    assert sum(len(item.get_offsets()) for item in right.collections) == 1
    assert len(left.lines) == 1
    assert len(right.lines) == 0
    np.testing.assert_array_equal(
        left.collections[0].get_offsets(), right.collections[0].get_offsets()
    )
    assert "2/3 associated" in figure._suptitle.get_text()
    assert "1/3" in right.get_title()
    output = io.BytesIO()
    figure.savefig(output, format="png")
    assert output.getvalue().startswith(b"\x89PNG")


def test_wrap_break_retains_samples_and_visibility_gaps():
    curve = OrbitCurve("123", (0, 1, 2, 3, 4), (90, 110, np.nan, -90, -110))
    times, values = _curve_samples(curve, 200)
    np.testing.assert_allclose(times, [0, np.nan, 1, 2, 3, np.nan, 4], equal_nan=True)
    np.testing.assert_allclose(
        values, [0.09, np.nan, -0.09, np.nan, -0.09, np.nan, 0.09], equal_nan=True
    )


def test_lanes_have_consistent_colors_and_limits():
    figure = make_orbit_plot((lane(), lane("RX1")), title="Both", time_limits_s=(0, 300))
    assert len(figure.axes) == 4
    np.testing.assert_allclose(
        figure.axes[0].collections[1].get_facecolors(),
        figure.axes[2].collections[1].get_facecolors(),
    )
    assert all(axis.get_xlim() == (0, 300) for axis in figure.axes)


def test_empty_lane_is_explicit():
    figure = make_orbit_plot((OrbitLane("RX0", "CH1", ()),), title="Empty")
    assert "0/0 associated" in figure._suptitle.get_text()
    assert "0/0" in figure.axes[1].get_title()


def test_duplicate_input_rejected():
    with pytest.raises(ValueError, match="lanes must be unique"):
        make_orbit_plot((lane(), lane()), title="Bad")
    repeated = OrbitLane("RX0", "CH1", (OrbitPeak("a", 0, 1), OrbitPeak("a", 1, 2)))
    with pytest.raises(ValueError, match="peak IDs must be unique"):
        make_orbit_plot((repeated,), title="Bad")


def test_association_requires_visible_model_input():
    with pytest.raises(ValueError, match="requires a curve"):
        make_orbit_plot((OrbitLane("RX0", "CH1", (OrbitPeak("a", 0, 1, "123"),)),), title="Bad")


@pytest.mark.parametrize("period", [0, -1, np.inf, np.nan])
def test_invalid_alias_period(period):
    with pytest.raises(ValueError, match="alias period"):
        make_orbit_plot((lane(),), title="Bad", alias_period_hz=period)


def test_curve_shape_and_nonfinite_observations_rejected():
    bad = OrbitCurve("123", (0, 1), (1,))
    with pytest.raises(ValueError, match="paired times"):
        make_orbit_plot((OrbitLane("RX0", "CH1", (), (bad,)),), title="Bad")
    with pytest.raises(ValueError, match="finite times/frequencies"):
        make_orbit_plot((OrbitLane("RX0", "CH1", (OrbitPeak("a", 0, np.nan),)),), title="Bad")
