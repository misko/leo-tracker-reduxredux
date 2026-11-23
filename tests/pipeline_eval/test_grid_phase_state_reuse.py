"""The exact predictive features use the same fixed phase states at each point."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import marginal, predictive_linear

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_phase_state_reuse import identical, prepared_features


@pytest.fixture(params=(False, True), ids=("zero", "fitted"))
def view(request):
    rng = np.random.default_rng(786)
    knots = np.arange(-20., 33., 2.)
    centre = rng.normal(size=(2, len(knots), 3)) + np.array([3245., 5895., 748.])
    velocity = rng.normal(size=centre.shape) + np.array([1., -2., 7.])
    modes = rng.normal(size=(6, len(knots), 3))
    times = np.array([2., 2., 8.25, 5., 7., 12.5])
    search = SimpleNamespace(latlon=lambda xy: (4.2 + xy[1]/111, 37.5 + xy[0]/111))
    return SimpleNamespace(
        sky=dict(time_s=knots, position_km=centre, velocity_km_s=velocity),
        mode_bank=dict(time_s=knots, position_km=modes, velocity_km_s=modes * 0.01),
        flat_times=times, flat_labels=np.array([1, 0, 1, 1, 0, 0]), reference=np.array([0.5, -1.7]),
        scan=SimpleNamespace(search_region=search), variant="radio_noise", labels=[19, 24],
        mode_metadata={}, phase_sigma=np.array([3., 10.]), q=np.linspace(.9, 1.1, len(times)),
        supported=[19], supported_local=[0], hardware=rng.normal(size=(len(times), 8+request.param)),
        smooth=rng.normal(size=(len(times), 12)), constants=np.ones((len(times), 2)),
    )


def test_predictive_features_keep_binary64_layout_and_reuse_state(view):
    original = predictive_linear.geometry_features
    geometry = prepared_features(original, marginal._phase_geometry)
    first, second = np.array([-5., 12.]), np.array([0., -2.])
    f = geometry(view, first, 0.)
    cache = view._fixed_phase_geometry_cache
    assert identical(f, original(view, first, 0.))
    g = geometry(view, second, 0.)
    assert identical(g, original(view, second, 0.))
    assert view._fixed_phase_geometry_cache is cache
    assert not identical(f, g)


@pytest.mark.parametrize("field", ["times", "phase", "mode_bank"])
def test_predictive_cache_rebuilds_on_reference_and_input_change(view, field):
    original = predictive_linear.geometry_features
    geometry = prepared_features(original, marginal._phase_geometry)
    position = np.zeros(2)
    geometry(view, position, 0.)
    cache = view._fixed_phase_geometry_cache
    if field == "times":
        view.flat_times[0] += 0.2
    elif field == "phase":
        view.reference[0] -= 0.9
    else:
        view.mode_bank["position_km"] = view.mode_bank["position_km"] * 4
    assert identical(geometry(view, position, 0.), original(view, position, 0.))
    assert view._fixed_phase_geometry_cache is not cache


def test_nonzero_altitude_uses_original_predictive_path(view):
    original = predictive_linear.geometry_features

    def unused(*_args):
        raise AssertionError("zero-altitude cache used for a nonzero observer altitude")

    geometry = prepared_features(original, unused)
    point = np.array([-3., -8.])
    assert identical(geometry(view, point, 18.), original(view, point, 18.))


def test_equivalence_includes_signed_zero_and_strides():
    samples = np.zeros((2, 3))
    changed = samples.copy()
    changed[0, 0] = -0.
    assert not identical({"x": samples}, {"x": changed})
    assert not identical({"x": samples}, {"x": samples.copy(order="F")})
