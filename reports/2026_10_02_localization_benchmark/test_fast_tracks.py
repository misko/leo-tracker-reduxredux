import time
from pathlib import Path

import fast_tracks
import models as oracle
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "scans" / "scan-fw-4971402f107cf8e1"


def synthetic_blocks(seed=42, receivers=(0, 1, 0, 1, 0, 1)):
    generator = np.random.default_rng(seed)
    blocks = []
    for track_index, receiver in enumerate(receivers):
        length = 3 + track_index % 6
        times = np.sort(generator.uniform(-140, 140, length))
        satellite_shape = generator.normal(0, 80, (length, 64))
        residual = 12000 + receiver * 8000 + 6.5 * times[:, None] + satellite_shape
        residual += generator.integers(-3, 4, 64)[None, :] * oracle.ALIAS_HZ
        visible = generator.random(64) > 0.15
        visible[track_index] = True
        blocks.append(
            {
                "track_index": track_index,
                "track_id": f"track-{track_index}",
                "rows": np.arange(length) + track_index * 100,
                "receiver": receiver,
                "times": times,
                "residual": residual,
                "visible": visible,
            }
        )
    return blocks


def assert_selected_equal(actual, expected):
    assert len(actual) == len(expected)
    for fast, slow in zip(actual, expected, strict=True):
        assert fast["track_index"] == slow["track_index"]
        assert fast["satellite"] == slow["satellite"]
        assert fast["alias_branch"] == slow["alias_branch"]
        assert fast["accepted"] == slow["accepted"]
        assert fast["offset_hz"] == pytest.approx(slow["offset_hz"], abs=1e-8)
        assert fast["cost"] == pytest.approx(slow["cost"], abs=1e-5)
        np.testing.assert_allclose(fast["errors"], slow["errors"], rtol=0, atol=1e-8)


def test_independent_matches_oracle_with_variable_lengths_and_visibility():
    blocks = synthetic_blocks()
    fast = fast_tracks.fit_track_independent(blocks)
    slow = oracle._fit_track_independent(blocks)
    assert fast[0] == pytest.approx(slow[0], abs=1e-5)
    assert fast[2] == slow[2] == {}
    assert_selected_equal(fast[1], slow[1])


@pytest.mark.parametrize("slope_limit", [0.0, 10.0])
def test_shared_matches_oracle_with_variable_lengths_and_visibility(slope_limit):
    blocks = synthetic_blocks()
    initial = np.zeros(70)
    initial[2:6] = [11800, 1.0, 19800, -2.0]
    fast = fast_tracks.fit_track_shared(blocks, initial, slope_limit)
    slow = oracle._fit_track_shared(blocks, initial, slope_limit)
    assert fast[0] == pytest.approx(slow[0], abs=1e-5)
    for receiver in (0, 1):
        np.testing.assert_allclose(fast[2][receiver], slow[2][receiver], rtol=0, atol=1e-8)
    assert_selected_equal(fast[1], slow[1])


def test_shared_missing_receiver_preserves_its_seed_line():
    blocks = synthetic_blocks(receivers=(0, 0, 0, 0))
    initial = np.zeros(70)
    initial[2:6] = [12000, 3.0, -23000, -4.0]
    fast = fast_tracks.fit_track_shared(blocks, initial, 10.0)
    slow = oracle._fit_track_shared(blocks, initial, 10.0)
    np.testing.assert_array_equal(fast[2][1], initial[4:6])
    np.testing.assert_array_equal(fast[2][1], slow[2][1])
    assert fast[0] == pytest.approx(slow[0], abs=1e-5)
    assert_selected_equal(fast[1], slow[1])


def test_shared_slope_cap_matches_oracle():
    blocks = synthetic_blocks(receivers=(0, 0, 0, 0, 0, 0))
    for block in blocks:
        times = block["times"]
        curvature = np.square(times - np.mean(times))[:, None] * np.arange(64)[None, :] * 0.01
        block["residual"] = 30000 + 18 * times[:, None] + curvature
        block["visible"][:] = True
    initial = np.zeros(70)
    initial[2] = 30000
    fast = fast_tracks.fit_track_shared(blocks, initial, 10.0)
    slow = oracle._fit_track_shared(blocks, initial, 10.0)
    assert abs(fast[2][0][1]) == pytest.approx(10.0)
    np.testing.assert_allclose(fast[2][0], slow[2][0], rtol=0, atol=1e-8)
    assert_selected_equal(fast[1], slow[1])


@pytest.mark.skipif(not (ORIGINAL / "bundle.npz").exists(), reason="original bundle unavailable")
def test_original_sample_matches_oracle_and_is_faster_without_fitting():
    from bundle import Data

    data = Data(ORIGINAL)
    arrays, numbers, initial, tracks = oracle._validate_data(data)
    context = oracle._Context(data, arrays, numbers, initial, tracks, float("inf"))
    prediction, visible = context.cache.get(np.array([0.0, 0.0]))
    blocks = oracle._track_blocks(context, prediction, visible)

    started = time.perf_counter()
    fast_independent = fast_tracks.fit_track_independent(blocks)
    fast_constant = fast_tracks.fit_track_shared(blocks, initial, 0.0)
    fast_linear = fast_tracks.fit_track_shared(blocks, initial, 10.0)
    fast_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    slow_independent = oracle._fit_track_independent(blocks)
    slow_constant = oracle._fit_track_shared(blocks, initial, 0.0)
    slow_linear = oracle._fit_track_shared(blocks, initial, 10.0)
    slow_elapsed = time.perf_counter() - started

    for fast, slow in (
        (fast_independent, slow_independent),
        (fast_constant, slow_constant),
        (fast_linear, slow_linear),
    ):
        assert fast[0] == pytest.approx(slow[0], abs=1e-5)
        assert_selected_equal(fast[1], slow[1])
    assert fast_elapsed < slow_elapsed
