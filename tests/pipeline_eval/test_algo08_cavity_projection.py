from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from tools.pipeline_eval.variants.algo08_cavity_projection import SharedPhaseGrid, held_times


def sky():
    knots = np.arange(-4, 13, dtype=float)
    rng = np.random.default_rng(6102)
    position = rng.normal(size=(6, len(knots), 3)) + [6400., 10., 2000.]
    velocity = rng.normal(scale=4, size=position.shape)
    return dict(time_s=knots, position_km=position, velocity_km_s=velocity)


@pytest.mark.parametrize("point", [(37.8, -122.4), (-33.05, 21.54)])
@pytest.mark.parametrize("limit", [None, 3, 0])
def test_exact_projection_reuses_time_columns_and_keeps_order(point, limit):
    bank = sky()
    times = [np.array([2., -0., 2., 4., 0., 4.5]), np.array([3., 4., 2., 5., -0., 6.])]
    means = np.asarray([-.14, .36, -.21, 1.48, .3, -1.])
    byte_limit = 2 ** 20 if limit is None else 3 * 2 * 8 * len(means) * limit
    metrics = Counter()
    shared = SharedPhaseGrid(phase_frequency_grid, bank, point, means, times, metrics,
                             maximum_bytes=byte_limit)
    for phase in (means, means + .01, means - .01):
        for dates in times:
            expected = phase_frequency_grid(bank, dates, *point, phase_seconds=phase)
            actual = shared(bank, dates, *point, phase_seconds=phase)
            for a, b in zip(actual, expected, strict=True):
                assert a.tobytes() == b.tobytes()
                assert a.strides == b.strides
    assert metrics["sky_calls"] == 6
    assert metrics["retained_table_bytes"] <= byte_limit
    saved = metrics["requested_sky_cells"] - metrics["evaluated_sky_cells"]
    assert saved == (0 if limit == 0 else 3 * len(means) * (12 - 8))
    for fields in shared.tables.values():
        assert all(not f.flags.writeable for f in fields)

    moved = (point[0] - 0.1, point[1])
    a = shared(bank, times[0], *moved, phase_seconds=means)
    b = phase_frequency_grid(bank, times[0], *moved, phase_seconds=means)
    for x, y in zip(a, b, strict=True):
        np.testing.assert_array_equal(x, y)
    assert metrics["sky_calls"] == 6


def test_cavity_inventory_keeps_active_masks_and_eligible_predictive_times():
    tracks = [{"times": np.arange(4) + i * 10} for i in range(4)]
    base = SimpleNamespace(rows=[{"candidate_index": j} for j in (3, 8, 3)],
                           members=[1, 0, 2], slices=[slice(i, i + 4) for i in (0, 4, 8)])
    context = dict(base=base, scan=SimpleNamespace(tracks=tracks),
                   keep=np.array([True, True, False, False] + [False] * 4 + [False, True, True, False]),
                   entries=[{"candidate_index": j, "track_index": 3} for j in (3, 8)])
    dates, = held_times(context)
    np.testing.assert_array_equal(dates, [10, 11, 21, 22, 30, 31, 32, 33])
