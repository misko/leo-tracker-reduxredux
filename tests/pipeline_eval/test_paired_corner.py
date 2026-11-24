from collections import Counter
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from paired_corner import PairProjector, build, ordered_corners


@pytest.fixture(scope="module")
def projectors(tmp_path_factory):
    from tools.pipeline_eval.variants import orbit_projector as stock

    binary = tmp_path_factory.mktemp("paired-corner")/"projection.so"
    build(stock, binary)
    ordinary = stock.Projector(binary)
    return ordinary, PairProjector(ordinary, binary)


def orbit_bank():
    from leo.sky.frames import geodetic_to_ecef_km

    earth_x = geodetic_to_ecef_km(0., 0., 0.)[0]
    times = np.arange(-20., 41., 10.)
    # Exact horizon at the origin, a duplicated row for score ties, and
    # independent above/below rows with opposite signed radial velocity.
    pos = np.zeros((4, len(times), 3))
    pos[:, :, 0] = earth_x + np.array([0., 0., 300., -100.])[:, None]
    pos[:, :, 1] = 980. + times * 3.
    pos[:, :, 2] = times * times / 10.
    vel = np.zeros_like(pos)
    vel[:, :, 1] = np.array([2., 2., -3., 4.])[:, None]
    vel[:, :, 2] = times / 5.
    return dict(time_s=times, position_km=pos, velocity_km_s=vel)


def assert_identical(first, second):
    for left, right in zip(first, second, strict=True):
        assert left.shape == right.shape
        assert left.tobytes() == right.tobytes()


@pytest.mark.parametrize("sites", [[(0., 0.), (0.25, -0.25)], [(62., 179.8), (-37., -179.8)]])
@pytest.mark.parametrize("phases", [0., np.array([0., 0., 1.5, -1.25])])
def test_exact_signed_fields_both_stencils_and_observer_order(projectors, sites, phases):
    from tools.pipeline_eval.variants.orbit_projector import prepare

    ordinary, paired = projectors
    grid = prepare(orbit_bank(), np.array([-7.5, 0., 3.5, 8.5]), phases)
    frequency, elevation, jacobian = paired.evaluate(grid, sites, rf_hz=11.325e9)[0]
    assert (frequency < 0.).any() and (frequency > 0.).any()
    assert (jacobian != 0).any()
    for order in (sites, sites[::-1]):
        for point, result in zip(order, paired.evaluate(grid, order, rf_hz=11.325e9), strict=True):
            assert_identical(ordinary.evaluate(grid, *point, rf_hz=11.325e9), result)
    if sites[0] == (0., 0.):
        assert (elevation[:2] == 0.).all() and (elevation[2] > 0.).all() and (elevation[3] < 0.).all()


def test_saved_second_is_single_use_and_preserves_catalogue_ties(projectors):
    from leo.analysis.research.retained_track_likelihood import profile, whitening
    from tools.pipeline_eval.variants.orbit_projector import prepare

    ordinary, paired = projectors
    t = np.array([0., 3.5, 8.5])
    grid = prepare(orbit_bank(), t)
    locations = ((0., 0.), (0.25, -0.25))
    counts = Counter()
    project = ordered_corners(ordinary.evaluate, grid, locations, paired, counts)
    for point in (*locations, locations[1]):
        control, candidate = ordinary.evaluate(grid, *point), project(grid, *point)
        assert_identical(control, candidate)
        terms = profile(control[0][0], candidate[0], *whitening(t))
        assert terms["cost"][0] == terms["cost"][1]
        assert int(np.argmin(terms["cost"])) == 0
    assert counts == dict(paired_calls=1, served_second=1, lookahead_bytes=288, ordinary_calls=1)


def test_out_of_order_context_and_unsafe_pair_take_stock(projectors):
    from tools.pipeline_eval.variants.orbit_projector import prepare

    ordinary, paired = projectors
    grid = prepare(orbit_bank(), np.array([0., 3.5, 8.5]))
    locations = ((0., 0.), (0.25, -0.25))
    for changed, order, configured, options in (
        (grid, locations[::-1], locations, {}),
        (grid, locations, locations, {"limit": 0}),
        (grid, locations, (locations[0], (91., 0.)), {}),
        (replace(grid, index=grid.index.copy()), locations, locations, {}),
    ):
        counts = Counter()
        project = ordered_corners(ordinary.evaluate, changed, configured, paired, counts, **options)
        for point in order:
            assert_identical(ordinary.evaluate(changed, *point), project(changed, *point))
        assert counts["paired_calls"] == 0 and counts["ordinary_calls"] == 2
    invalid_index = grid.index.copy()
    invalid_index[0, 0, 0] = -1
    invalid_index.setflags(write=False)
    with pytest.raises(ValueError, match="index outside"):
        paired.evaluate(replace(grid, index=invalid_index), locations)
