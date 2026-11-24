from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_feature_projection import exact, supported_cpu
from paired_secant_geometry import Experiment, PairedProjection, build


pytestmark = [pytest.mark.hardware, pytest.mark.frozen_v5_numerics]


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    if not supported_cpu():
        pytest.fail("The checked build requires the original x86-64 numerical host")
    path = tmp_path_factory.mktemp("secant-pair")/"project.so"
    build(path)
    return PairedProjection(path)


def test_two_projection_views_match_independent_released_results(native):
    from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
    from leo.analysis.research.prepared_phase_geometry import PreparedPhaseGeometry

    rng = np.random.default_rng(26)
    rows = 63
    orbit = np.array([5100.0, -4800.0, 2000.0]) + rng.standard_normal((rows, 3))
    velocity = rng.standard_normal((rows, 3))
    delta_p, delta_v = rng.standard_normal((2, rows, 3, 3))
    center = PreparedPhaseGeometry(orbit, velocity, delta_p, delta_v)
    shifts = tuple((orbit + step * velocity, velocity.copy()) for step in (+0.01, -0.01))
    coordinates = ((33.22, -86.12), (33.220001, -86.120001))
    pair = native(center, shifts, coordinates)
    for place, observed in zip(coordinates, pair, strict=True):
        frequency, elevation, modes = center.evaluate(*place)
        f_plus, f_minus = [phase_frequency_from_states(*v, *place)[0] for v in shifts]
        expected = (frequency, elevation, (f_plus - f_minus) / 0.02, modes)
        assert all(exact(a, b) for a, b in zip(observed, expected, strict=True))


def test_rejects_unsupported_dtype(native):
    position = np.zeros((4, 3), dtype=np.float32)
    center = SimpleNamespace(position_km=position, velocity_km_s=position,
                             mode_position_km=None, mode_velocity_km_s=None)
    assert native(center, [(position, position)] * 2, ((0., 0.), (1., 1.))) is None


def test_no_completed_view_keeps_the_original_optimizer(native):
    from leo.analysis.localization_v3 import marginal, predictive_linear
    from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant
    from nomination_handoff import same

    study = Experiment(bounded_secant, marginal._phase_geometry, predictive_linear.geometry_features, native)

    def residual(x):
        return x - np.array([0.125, -1.0])

    bounds = [-3., -3.], [3., 3.]
    baseline = bounded_secant(residual, [0., 0.], *bounds)
    with study.treatment("pair") as (calls, _):
        candidate = study.optimize(residual, [0., 0.], *bounds)
    assert same(baseline, candidate)
    assert calls["batch_fallback"] == baseline["jacobian_refreshes"]
    assert calls["column_calls"] == 2 * baseline["jacobian_refreshes"]
