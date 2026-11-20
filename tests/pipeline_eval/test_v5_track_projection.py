from collections import Counter

import numpy as np
import pytest

from tools.pipeline_eval.variants import orbit_projector, v5_track_projection


@pytest.fixture
def inputs(tmp_path):
    lib = tmp_path / "project.so"
    orbit_projector.compile_kernel(lib)
    project = orbit_projector.Projector(lib).evaluate
    rng = np.random.default_rng(443)
    knots = np.arange(-10.0, 16.0)
    position = rng.normal(size=(12, 1, 3))
    position *= 7000 / np.linalg.norm(position, axis=-1, keepdims=True)
    velocity = rng.normal(size=(12, len(knots), 3))
    bank = dict(
        time_s=knots,
        position_km=position + velocity * knots[None, :, None],
        velocity_km_s=velocity,
    )
    return project, bank, np.array([-4.1, -1.2, 0.5, 1.1, 2.2, 4.9, 8.9, 10.3])


def views(project, grid, counts):
    source = v5_track_projection.TrackColumns(project, grid, (36.1, -118.8), {}, counts)
    return tuple(v5_track_projection.TrackField(source, i) for i in range(3))


def test_track_columns_keep_original_index_order_bytes_and_layout(inputs):
    project, bank, times = inputs
    columns = np.array([5, 2, 2, 0], dtype=np.int64)
    grid = orbit_projector.prepare(bank, times)
    expected = project(grid, 36.1, -118.8)
    counts = Counter()
    fields = views(project, grid, counts)
    for view, array in zip(fields, expected, strict=True):
        actual = view[:, columns]
        np.testing.assert_array_equal(actual, array[:, columns])
        assert actual.strides == array[:, columns].strides
    assert counts["track_projections"] == 1
    assert counts["shared_field_queries"] == 2
    assert counts["max_track_grid_bytes"] == 24 * len(columns) * len(bank["position_km"])


def test_phase_overlay_is_exact_and_does_not_mutate_base_projection(inputs):
    project, bank, times = inputs
    columns = np.array([1, 3, 6])
    rows = np.array([1, 7, 11])
    original = orbit_projector.prepare(bank, times)
    subset = dict(
        bank, position_km=bank["position_km"][rows], velocity_km_s=bank["velocity_km_s"][rows]
    )
    shifted = orbit_projector.prepare(subset, times, [1.5, -0.15, 0.27])
    counts = Counter()
    originals = views(project, original, counts)
    overlays = views(project, shifted, counts)
    normal, shifted_values = (project(stencil, 36.1, -118.8) for stencil in (original, shifted))
    for field, overlay, before, after in zip(
        originals, overlays, normal, shifted_values, strict=True
    ):
        copied = field.copy()
        copied[rows] = overlay
        expected = before.copy()
        expected[rows] = after
        np.testing.assert_array_equal(copied[:, columns], expected[:, columns])
        np.testing.assert_array_equal(field[:, columns], before[:, columns])
    assert counts["track_projections"] == 2
