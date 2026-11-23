"""Preserve the prepared state arithmetic and per-view feature layout."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.continuous_curve_fit import phase_frequency_from_states
from leo.analysis.research.prepared_phase_geometry import PreparedPhaseGeometry
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.variants.algo08_curved_design import selected_design

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import grid_feature_projection as projection
import grid_phase_state_reuse as cache
from grid_feature_projection import Native, build, exact


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


def test_selected_design_keeps_row_order_and_signed_zeros(native):
    values = np.arange(40, dtype=float).reshape(8, 5)
    values[2, 0] = -0.
    values[7, 4] = -0.
    scale = np.array([1., 1., 0.3, 0.3, 0.3])
    keep = np.array([False, False, True, False, True, False, False, True])
    for source in (values, values[:, ::-1]):
        assert exact(native.selected_design(source, scale, keep, selected_design), selected_design(source, scale, keep))
    assert native.counts["selection_fallback"] == 1


def test_unavailable_cpu_keeps_active_scope_on_incumbent(tmp_path, monkeypatch):
    path = tmp_path / "verified"
    path.write_bytes(b"reviewed")
    monkeypatch.setattr(projection, "LIBRARY_SHA", sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(projection, "supported_cpu", lambda: False)
    audit = {}
    original = cache.cached_predictive_grid
    with projection.active_projection(path, audit):
        assert cache.cached_predictive_grid is original
    assert audit["runtime_fallbacks"] == 1


def test_unreviewed_library_fails_before_loading(tmp_path):
    path = tmp_path / "unreviewed"
    path.write_bytes(b"unknown")
    with pytest.raises(ValueError, match="Unreviewed bootstrap input"):
        with projection.active_projection(path, {}):
            pytest.fail("The unchecked library reached the publication scope")


def test_mapped_or_unbound_sampler_preserves_both_incumbent_operations():
    def sample(**kwargs):
        return tuple(kwargs)

    native = SimpleNamespace(counts=Counter())
    grid, predictive = projection.bind_grid(native, sample, None, lambda *_: "stock predictive")
    assert grid() == ()
    assert grid(map_batches=tuple) == ("map_batches",)
    assert predictive(None) == "stock predictive"
    assert native.counts == {"layout_fallbacks": 1, "mapped_grid_fallbacks": 1}
