import numpy as np
import pytest

from leo.analysis.localization_v3 import marginal
from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
from leo.analysis.research.prepared_phase_geometry import PreparedPhaseGeometry
from leo.sky.frames import geodetic_to_ecef_km
from tests.analysis.test_localization_v3_position import prepared
from tools.pipeline_eval.variants.algo08_fused_phase_projection import (
    fused_projection,
    measured_phase_projection,
)


@pytest.mark.parametrize("coordinates", [(47., 16.), (-33., 21.), (89., 2.)])
def test_outputs_preserve_bits_across_geometries_and_modes(coordinates):
    rng = np.random.default_rng(285)
    observer = geodetic_to_ecef_km(*coordinates, 0.0)
    positions = observer + rng.normal(0, 4600., (513, 3))
    positions[0] = observer * 1.09  # Near zenith.
    positions[1] = observer * 0.91  # Opposite the zenith direction.
    velocity = rng.normal(0, 7., positions.shape)
    modes = [rng.normal(0, 1., (len(positions), 3, 3)) for _ in range(2)]
    center = PreparedPhaseGeometry(positions, velocity, *modes)
    shifts = [(positions + step * velocity, velocity.copy()) for step in (.01, -.01)]
    frequency, elevation, modes = center.evaluate(*coordinates)
    plus, minus = [phase_frequency_from_states(*pair, *coordinates)[0] for pair in shifts]
    result = fused_projection(center, shifts, *coordinates)
    for actual, expected in zip(result, (frequency, elevation, (plus - minus) / .02, modes), strict=True):
        assert actual.dtype == expected.dtype and actual.shape == expected.shape
        assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize("fitted", [False, True])
def test_constructor_cache_and_phase_reference_changes_keep_full_objective(fitted):
    scan, node = prepared()
    p = NormalPosition(scan, node, 150., fitted, reference=np.array([.15]))
    for phase in (.15, .21):
        p.reference[0] = phase
        point = np.array([1.2, -3.1])
        reference = marginal._phase_geometry(p, point)
        score = p.residual(point)
        snapshot = p._fixed_phase_geometry_cache
        with measured_phase_projection(enabled=True, stage=lambda: "fit") as counts:
            actual = marginal._phase_geometry(p, point)
            assert p.residual(point).tobytes() == score.tobytes()
        assert p._fixed_phase_geometry_cache is snapshot
        assert counts["fit_calls"] == 2
        assert all(a.tobytes() == b.tobytes() for a, b in zip(actual, reference, strict=True))
