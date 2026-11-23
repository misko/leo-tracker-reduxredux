"""Preserve the prepared state arithmetic and per-view feature layout."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
from leo.analysis.research.prepared_phase_geometry import PreparedPhaseGeometry
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.variants.algo08_curved_design import direct_features, selected_design

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_feature_projection import Design, Native, build, exact


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    lib = tmp_path_factory.mktemp("grid-feature-projection") / "project.so"
    build(lib)
    return Native(lib)


@pytest.mark.parametrize("latitude,longitude", [(38.4, -122.5), (-54.2, 16.4), (0., 180.)])
def test_projection_uses_exact_order_for_every_result(native, latitude, longitude):
    rng = np.random.default_rng(49)
    rows = 513
    p = rng.normal(size=(rows, 3)) * 4432.
    v = rng.normal(size=(rows, 3)) * 3.
    mode = rng.normal(size=(rows, 3, 3))
    center = PreparedPhaseGeometry(p, v, mode.copy(), mode * 0.001)
    shifts = [(p + t * v, v) for t in (0.01, -0.01)]
    projected = native.projection(center, shifts, latitude, longitude)
    frequency, elevation, modes = center.evaluate(latitude, longitude)
    plus, minus = [phase_frequency_from_states(*s, latitude, longitude)[0] for s in shifts]
    assert all(exact(a, b) for a, b in zip(projected, (frequency, elevation, (plus-minus)/0.02, modes), strict=True))


def test_projection_declines_degenerate_nonfinite_and_strided_states(native):
    row = np.zeros((4, 3))
    row[0] = geodetic_to_ecef_km(38.4, -122.5, 0.)
    v = np.ones_like(row)
    modes = np.zeros((4, 3, 3))
    shifts = [(row + t * v, v) for t in (0.01, -0.01)]
    assert native.projection(PreparedPhaseGeometry(row, v, modes, modes), shifts, 38.4, -122.5) is None
    row[0] = np.nan
    assert native.projection(PreparedPhaseGeometry(row, v, modes, modes), shifts, 38.4, -122.5) is None
    assert native.projection(PreparedPhaseGeometry(v[:, ::-1], v, modes, modes), shifts, 38.4, -122.5) is None


def test_design_has_distinct_scaffolds_and_checks_mutated_inputs():
    rng = np.random.default_rng(9)
    rows = 87
    problem = SimpleNamespace(
        flat_labels=np.arange(rows) % 3,
        labels=[90, 20, 30],
        supported_local=[2, 0],
        supported=[30, 90],
        hardware=rng.normal(size=(rows, 8)),
        smooth=rng.normal(size=(rows, 7)),
        constants=rng.normal(size=(rows, 15)),
        q=rng.normal(size=rows),
        phase_sigma=np.array([1.5, 3., 2.5]),
    )
    other = SimpleNamespace(**vars(problem))
    other.constants = problem.constants + 0.1
    template = Design(direct_features)
    derivative, modes, scale = rng.normal(size=rows), rng.normal(size=(rows, 3)), np.ones(3)
    for p in (problem, other, problem):
        assert exact(template.assemble(p, derivative, modes, scale), direct_features(p, derivative, modes, scale))
        derivative = derivative * -1.07
    problem.constants[0] = 21.0
    assert exact(template.assemble(problem, derivative, modes, scale), direct_features(problem, derivative, modes, scale))
    assert template.counts == {"design_views": 2, "template_design": 3, "design_fallback": 1}


def test_selected_design_keeps_row_order_and_signed_zeros(native):
    values = np.arange(40, dtype=float).reshape(8, 5)
    values[2, 0] = -0.
    values[7, 4] = -0.
    scale = np.array([1., 1., 0.3, 0.3, 0.3])
    keep = np.array([False, False, True, False, True, False, False, True])
    for source in (values, values[:, ::-1]):
        assert exact(native.selected_design(source, scale, keep, selected_design), selected_design(source, scale, keep))
    assert native.counts["selection_fallback"] == 1
