import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np

from leo.analysis.research.regional_doppler import Region
from leo.analysis.research.scanner_tle_screen import rank_curves
from leo.contracts.sky import ObserverSiteV1

PATH = Path(__file__).parents[2] / "tools/research/search_multiresolution_tle_coverage.py"
SPEC = importlib.util.spec_from_file_location("multiresolution_coverage_test", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _ids(count):
    return tuple(
        "sha256:" + hashlib.sha256(f"observation-{index}".encode()).hexdigest()
        for index in range(count)
    )


def test_required_geometry_nodes_are_exact_interpolation_endpoints():
    times = [np.asarray([-5.0, -4.5, 0.0]), np.asarray([2.25])]
    actual = MODULE.required_geometry_nodes(
        times, np.asarray([-5.0, 0.0, 5.0]), grid_start=-10.0, grid_step=1.0, grid_count=30
    )
    # Every query's lower and upper linear-interpolation node is retained,
    # including an integer query whose endpoints coincide.
    np.testing.assert_array_equal(actual, [0, 1, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18])


def test_fixed_partition_is_coordinate_independent_and_legacy_is_not():
    first = ObserverSiteV1(latitude_deg=38.5816, longitude_deg=-121.4944, altitude_m=0, label="a")
    second = ObserverSiteV1(latitude_deg=39.5296, longitude_deg=-119.8138, altitude_m=0, label="b")
    fixed_one = MODULE.partition_mask(
        _ids(10), "sha256:" + "1" * 64, "sha256:" + "2" * 64, first,
    )
    fixed_two = MODULE.partition_mask(
        _ids(10), "sha256:" + "1" * 64, "sha256:" + "2" * 64, second,
    )
    legacy = MODULE.partition_mask(
        _ids(10), "sha256:" + "1" * 64, "sha256:" + "2" * 64, second,
        mode="legacy",
    )
    np.testing.assert_array_equal(fixed_one[0], fixed_two[0])
    assert fixed_one[1] == fixed_two[1]
    assert legacy[1] != fixed_one[1]
    assert fixed_one[0].sum() == 6


def test_prediction_score_is_exact_training_frozen_rank_curves_with_strict_gate():
    measured = np.asarray([0.0, 0.0, 800.0, -800.0])
    predictions = np.asarray([
        [[0.0, 0.0, 800.0, -800.0], [10.0, -10.0, 0.0, 0.0]],
        [[0.0, 0.0, 800.01, -800.01], [10.0, -10.0, 0.0, 0.0]],
    ])
    training = np.asarray([True, True, False, False])
    result = MODULE.score_prediction_bank(
        measured, predictions, training, np.asarray([-5.0, 5.0]), np.asarray([True, True]), [800.0]
    )
    expected = rank_curves(measured, predictions, training_mask=training)
    for candidate, row in enumerate(result):
        assert row["tau_s"] == -5.0
        assert row["training_rms_hz"] == expected["training_rms"][candidate]
        assert row["heldout_rms_hz"] == expected["heldout_rms"][candidate]
        assert row["qualifies"][800.0] is (row["heldout_rms_hz"] < 800.0)
    # A perfect held-out alternate tau must not be selected when it loses on training rows.
    assert result[0]["tau_s"] == -5.0


def test_ranking_uses_unique_observations_then_clipped_rms_then_coordinates():
    def cell(east, north, observations, duration, tracks, rms):
        return MODULE.CellScore(east, north, (MODULE.ThresholdCoverage(
            800.0, observations, duration, tracks, rms, rms
        ),))

    cells = [
        cell(2, 0, 5, 90, 2, 100),
        cell(1, 0, 5, 90, 2, 100),
        cell(0, 0, 5, 80, 9, 1),
        cell(0, 1, 4, 999, 9, 1),
    ]
    ranked = MODULE.rank_coverage_cells(cells, 800.0)
    assert [(row.east_km, row.north_km) for row in ranked] == [(0, 0), (1, 0), (2, 0), (0, 1)]


def test_final_lattice_is_exact_frozen_region_grid_circle():
    region = Region(38.5816, -121.4944, 5000, 5000)
    oracle = region.grid(50.0)
    keep = np.hypot(oracle.east_km, oracle.north_km) <= 350.0
    expected = np.column_stack((oracle.east_km[keep], oracle.north_km[keep]))
    expected = expected[np.lexsort((expected[:, 1], expected[:, 0]))]
    actual = MODULE.regional_circle_offsets(5000.0, 350.0, 50.0)
    np.testing.assert_array_equal(actual, expected)


def test_rim_parent_is_retained_when_its_fine_child_is_inside_circle():
    # The 200 km parent at (400, 0) lies outside radius 355, but the exact
    # 100 km lattice has its (350, 50) child inside. Dropping the parent by
    # centre alone would silently make this final candidate unreachable.
    calls = []

    def evaluator(points):
        calls.append(points.copy())
        return [MODULE.CellScore(
            float(east), float(north), (MODULE.ThresholdCoverage(
                800.0, 1, 1.0, 1, 1.0, 1.0
            ),)
        ) for east, north in points]

    _, trace = MODULE.multiresolution_search(
        evaluator, radius_km=355.0, levels_km=(200.0, 100.0), basins=1
    )
    assert trace[0]["new_cell_count"] > 0
    assert any(np.allclose(point, [350.0, 50.0], rtol=0, atol=1e-10) for point in calls[1])
    all_points = np.concatenate(calls)
    assert len({tuple(point) for point in all_points}) == len(all_points)


def test_returned_comparator_contains_only_last_declared_lattice():
    def evaluator(points):
        return [MODULE.CellScore(
            float(east), float(north), (MODULE.ThresholdCoverage(
                800.0, 99 if (east, north) == (0.0, 0.0) else 1,
                1.0, 1, 1.0, 1.0,
            ),)
        ) for east, north in points]

    final, trace = MODULE.multiresolution_search(
        evaluator, radius_km=300.0, levels_km=(200.0, 100.0), basins=1
    )
    assert [row.east_km for row in final]
    assert all((row.east_km, row.north_km) != (0.0, 0.0) for row in final)
    assert [0.0, 0.0] in trace[-1]["union_incumbents"]


def test_coarse_visibility_keeps_near_horizon_candidates_until_exact_gate():
    site = Region(0, 0, 100, 100).points([0], [0])
    up = site.up[0]
    tangent = np.cross(up, [0.0, 0.0, 1.0])
    tangent /= np.linalg.norm(tangent)

    def bank(elevation_deg):
        direction = (
            tangent * np.cos(np.deg2rad(elevation_deg))
            + up * np.sin(np.deg2rad(elevation_deg))
        )
        nodes = np.arange(507, 512)
        coarse = np.broadcast_to(site.ecef_km[0] + 1000 * direction, (1, len(nodes), 3)).copy()
        position = coarse[:, None, :4, :].copy()
        return MODULE.TrackPredictionBank(
            "track", _ids(4), np.zeros(4), np.arange(4.0), 3.0, "sha256:" + "1" * 64,
            position, np.zeros_like(position), np.asarray([1]), coarse, nodes,
        )

    evaluator = MODULE.CoverageEvaluator(
        (bank(-0.05),), np.asarray([0.0]), "sha256:" + "2" * 64, (800.0,)
    )
    assert evaluator._coarse_visible(evaluator.tracks[0], site).tolist() == [True]
    below_gate = bank(-0.11)
    assert evaluator._coarse_visible(below_gate, site).tolist() == [False]


def test_cache_keys_physical_site_and_rebinds_cached_score_to_requested_offsets():
    first = Region(0, 0, 100, 100).points([0], [0])
    up = first.up[0]
    tangent = np.cross(up, [0.0, 0.0, 1.0])
    tangent /= np.linalg.norm(tangent)
    direction = tangent * np.cos(np.deg2rad(1.0)) + up * np.sin(np.deg2rad(1.0))
    nodes = np.arange(507, 512)
    coarse = np.broadcast_to(first.ecef_km[0] + 1000 * direction, (1, len(nodes), 3)).copy()
    position = coarse[:, None, :4, :].copy()
    track = MODULE.TrackPredictionBank(
        "track", _ids(4), np.zeros(4), np.arange(4.0), 3.0, "sha256:" + "1" * 64,
        position, np.zeros_like(position), np.asarray([1]), coarse, nodes,
    )
    evaluator = MODULE.CoverageEvaluator(
        (track,), np.asarray([0.0]), "sha256:" + "2" * 64, (800.0,)
    )
    second = Region(20, 20, 100, 100).points([0], [0])
    evaluator.evaluate_points(first)
    evaluator.evaluate_points(second)
    assert evaluator.metrics()["cached_cell_count"] == 2

    same_physical_new_offsets = MODULE.Grid(
        np.asarray([321.0]), np.asarray([-123.0]), first.latitude_deg, first.longitude_deg,
        first.altitude_m, first.ecef_km, first.up,
    )
    rebound = evaluator.evaluate_points(same_physical_new_offsets)[0]
    assert (rebound.east_km, rebound.north_km) == (321.0, -123.0)
    assert evaluator.metrics()["cache_hits"] == 1


def test_exact_top_k_keeps_equal_bound_late_improvement_and_skips_partial_cache():
    site = Region(0, 0, 100, 100).points([0, 10, 20], [0, 0, 0])
    nodes = np.arange(507, 512)

    def track(index):
        position = np.zeros((1, 1, 4, 3))
        coarse = np.zeros((1, len(nodes), 3))
        return MODULE.TrackPredictionBank(
            f"track-{index}", _ids(4 * index + 4)[4 * index:], np.zeros(4),
            np.arange(4.0), 3.0, "sha256:" + str(index + 1) * 64,
            position, np.zeros_like(position), np.asarray([index]), coarse, nodes,
        )

    tracks = tuple(track(index) for index in range(3))
    # Cell 10 has the same eight-observation coverage as cell 0, but its
    # later tracks improve clipped RMS. Cell 20 cannot reach eight after two
    # failed tracks and must be pruned without a cache entry.
    best = {
        (0, "track-0"): 100.0, (0, "track-1"): 100.0, (0, "track-2"): 900.0,
        (10, "track-0"): 900.0, (10, "track-1"): 10.0, (10, "track-2"): 10.0,
        (20, "track-0"): 900.0, (20, "track-1"): 900.0, (20, "track-2"): 900.0,
    }

    def evaluator():
        instance = MODULE.CoverageEvaluator(
            tracks, np.asarray([0.0]), "sha256:" + "4" * 64, (800.0,)
        )
        instance._coarse_elevation = lambda _: np.zeros((1, len(nodes)))
        instance._track_best = lambda item, grid, training, *_args, **_kwargs: (
            best[(round(float(grid.east_km[0])), item.tracklet_id)], int(np.sum(~training)),
            None, [],
        )
        return instance

    full = evaluator()
    expected = MODULE.rank_coverage_cells(full.evaluate_points(site), 800.0, 1)
    bounded = evaluator()
    actual, pruned = bounded.evaluate_top_k(site, top_k=1, threshold_hz=800.0)
    assert [(row.east_km, row.north_km) for row in actual] == [
        (row.east_km, row.north_km) for row in expected
    ] == [(10.0, 0.0)]
    assert len(pruned) == 1 and pruned[0]["east_km"] == 20.0
    assert bounded.metrics()["cached_cell_count"] == 2
    assert bounded.metrics()["early_abandoned_cell_count"] == 1
