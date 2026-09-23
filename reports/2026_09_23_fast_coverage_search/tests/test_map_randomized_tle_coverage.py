import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.analysis.research.scanner_tle_screen import rank_curves
from leo.contracts.sky import ObserverSiteV1

PATH = Path(__file__).parents[2] / "tools/research/map_randomized_tle_coverage.py"
SPEC = importlib.util.spec_from_file_location("coverage_map_test", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_one_cell_kernel_matches_standard_rank_curves():
    y = np.asarray([4.0, 1.0, 7.0, 3.0, 9.0])
    predictions = np.asarray([
        [[0, 1, 2, 3, 4], [1, 2, 3, 4, 5], [2, 3, 4, 5, 6]],
        [[5, 4, 3, 2, 1], [6, 5, 4, 3, 2], [7, 6, 5, 4, 3]],
    ], dtype=float)
    mask = np.asarray([True, False, True, False, True])
    # Construct radial states whose Doppler is exactly the supplied bank.
    position = np.zeros((2, 3, 5, 3))
    position[..., 0] = 7000
    velocity = np.zeros_like(position)
    velocity[..., 0] = -predictions * LIGHT_KM_S / REFERENCE_RF_HZ
    sites = Region(0, 0, 100, 100).points([0], [0])
    best, rows, _ = MODULE._score_track(
        y, position, velocity, np.asarray([10, 20]), sites, mask[None],
        np.asarray([-1., 0., 1.]), 800,
    )
    expected = rank_curves(y, predictions, training_mask=mask)
    assert best[0] == np.min(expected["heldout_rms"])
    assert {row["norad"] for row in rows[0]} == {10, 20}


def _radial_states(predictions, cells=1):
    predictions = np.asarray(predictions, dtype=float)
    position = np.zeros((*predictions.shape, 3))
    position[..., 0] = 7000
    velocity = np.zeros_like(position)
    velocity[..., 0] = -predictions * LIGHT_KM_S / REFERENCE_RF_HZ
    sites = Region(0, 0, 100, 100).points(np.zeros(cells), np.zeros(cells))
    return position, velocity, sites


def test_blocked_look_sine_matches_direct_geometry():
    rng = np.random.default_rng(20260923)
    sites = Region(38, -122, 5000, 5000).points(
        rng.uniform(-2400, 2400, 7), rng.uniform(-2400, 2400, 7)
    )
    position = rng.normal(size=(11, 19, 3)) * 9000
    direct_delta = position[None] - sites.ecef_km[:, None, None]
    direct = np.sum(direct_delta * sites.up[:, None, None], axis=-1)
    direct /= np.linalg.norm(direct_delta, axis=-1)
    actual = MODULE._blocked_look_sine(position, sites.ecef_km, sites.up)
    np.testing.assert_allclose(actual, direct, rtol=2e-14, atol=2e-14)


def test_strict_threshold_training_tau_and_broad_visibility():
    # Tau 0 has perfect training and controlled held-out RMS. Tau 1 has worse
    # training but perfect held-out rows, so selecting it would leak evaluation.
    held = [799.99, 800.0, 800.01]
    prediction = np.zeros((3, 2, 4))
    for candidate, value in enumerate(held):
        prediction[candidate, 0] = [0, 0, value, -value]
        prediction[candidate, 1] = [10, -10, 0, 0]
    position, velocity, sites = _radial_states(prediction)
    mask = np.asarray([[True, True, False, False]])
    broad = np.asarray([[True, True, False]])
    best, rows, boundary = MODULE._score_track(
        np.zeros(4),
        position,
        velocity,
        np.asarray([10, 20, 30]),
        sites,
        mask,
        np.asarray([-5.0, 5.0]),
        800.0,
        broad,
        cell_block=1,
    )
    assert np.isclose(best[0], held[0], rtol=0, atol=1e-10)
    # The nominal 800.0 case reconstructs to the immediately lower float through
    # state-to-Doppler arithmetic. The standard applies strict `< 800` to that
    # computed value, so parity requires it to qualify; 800.01 remains excluded.
    assert [row["norad"] for row in rows[0]] == [10, 20]
    assert rows[0][1]["heldout_rms_hz"] < 800.0
    assert rows[0][0]["tau_s"] == -5.0
    assert boundary[0]


def test_cell_batching_preserves_every_candidate_and_cell_result():
    prediction = np.asarray(
        [
            [[0, 0, 100, -100], [20, -20, 0, 0]],
            [[0, 0, 200, -200], [30, -30, 0, 0]],
        ],
        dtype=float,
    )
    position, velocity, sites = _radial_states(prediction, cells=3)
    masks = np.asarray(
        [
            [True, True, False, False],
            [True, False, True, False],
            [False, True, False, True],
        ]
    )
    arguments = (
        np.zeros(4), position, velocity, np.asarray([10, 20]), sites, masks,
        np.asarray([-5.0, 5.0]), 800.0,
    )
    small = MODULE._score_track(*arguments, cell_block=1)
    large = MODULE._score_track(*arguments, cell_block=8)
    np.testing.assert_array_equal(small[0], large[0])
    assert small[1] == large[1]
    np.testing.assert_array_equal(small[2], large[2])
    assert all({row["norad"] for row in cell} == {10, 20} for cell in small[1])


def test_edge_visible_candidate_is_not_excluded_by_centre_visibility():
    region = Region(0, 0, 5000, 5000)
    sites = region.points([0, 2000], [0, 0])
    edge_receiver = sites.ecef_km[1]
    edge_up = sites.up[1]
    position = np.broadcast_to(edge_receiver + 550 * edge_up, (1, 1, 4, 3)).copy()
    velocity = np.zeros_like(position)
    masks = np.asarray([[True, True, False, False]] * 2)
    best, rows, _ = MODULE._score_track(
        np.zeros(4),
        position,
        velocity,
        np.asarray([10]),
        sites,
        masks,
        np.asarray([0.0]),
        800.0,
        broad_visible=np.asarray([[False], [True]]),
        cell_block=1,
    )
    assert not np.isfinite(best[0])
    assert np.isfinite(best[1])
    assert rows[0] == []
    assert rows[1][0]["norad"] == 10


def test_partition_seed_matches_frozen_standard_protocol():
    rows = [
        SimpleNamespace(
            observation_id="sha256:" + hashlib.sha256(str(index).encode()).hexdigest()
        )
        for index in range(10)
    ]
    site = ObserverSiteV1(
        latitude_deg=37.84903264307456,
        longitude_deg=-122.4856541910174,
        altitude_m=0,
        label="spinnaker-sausalito",
    )
    mask, seed = MODULE._partition(
        rows, "sha256:" + "1" * 64, "sha256:" + "2" * 64, site
    )
    assert seed == "sha256:428887ef1da094d038b813d2f10cb5746b42b7308b42f6d07d06794f5bc951b3"
    np.testing.assert_array_equal(
        mask, [True, True, False, True, True, True, False, True, False, False]
    )
