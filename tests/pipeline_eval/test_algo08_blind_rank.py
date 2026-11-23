from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from leo.analysis.localization_v3 import discovery
from tools.pipeline_eval.variants.algo08_blind_rank import shared_rank_preparation


def fixture(order):
    rng = np.random.default_rng(251)
    times = np.linspace(0, 80, 19)
    rows = rng.normal(size=(3, 6, len(times))) * 100
    tracks = [dict(key="a", channel=3, receiver=1, rf_hz=10.7e9,
                   times=times[[0, 6, 7, 10, 10, 14]], values=rng.normal(size=6) * 1e6),
              dict(key="b", channel=7, receiver=2, rf_hz=11.9e9,
                   times=times[[1, 3, 8, 9, 16, 18]], values=rng.normal(size=6) * 1e6)]
    scan = SimpleNamespace(geometry=object(), times=times,
                           search_region=SimpleNamespace(center=(10.0, -20.0)))

    def project(states, latitude, longitude):
        assert states is scan.geometry
        return tuple(np.array(array + latitude + longitude, order=order) for array in rows)

    return scan, tracks, project


def statistics(scan, tracks, point, corrections):
    frequency, elevation, derivative = discovery.phase_linear_frequency(scan.geometry, *point)
    bank = dict(time_s=scan.times, doppler_0=frequency, elevation_deg=elevation)
    stats = discovery.statistics([(track["key"], [track]) for track in tracks], bank, corrections)
    return discovery.augment_phase_statistics(stats, scan.times, frequency, derivative)


def equal_statistics(a, b):
    assert a.keys() == b.keys()
    for key in a.keys() - {"fragments"}:
        assert a[key].shape == b[key].shape and a[key].dtype == b[key].dtype
        assert a[key].tobytes() == b[key].tobytes(), key


@pytest.mark.parametrize("order", ["C", "F"])
@pytest.mark.parametrize("cache", [0, 2**20])
def test_exact_centre_updates_and_distinct_corner_projection(order, cache):
    scan, tracks, project = fixture(order)
    center = scan.search_region.center
    corner = (center[0] - 0.11, center[1] + 0.15)
    correction = {"3": 0.0, "7": 0.0}
    adjusted = [dict(track, values=track["values"] - np.linspace(1.5, -2.5, 6)) for track in tracks]
    args = [(tracks, center, correction), (adjusted, center, correction), (adjusted, corner, correction)]

    with patch.object(discovery, "phase_linear_frequency", project):
        expected = [statistics(scan, *entry) for entry in args]
        with shared_rank_preparation(scan, max_track_bytes=cache) as counts:
            actual = [statistics(scan, *entry) for entry in args]
    for before, after in zip(expected, actual, strict=True):
        equal_statistics(before, after)
    assert counts["nominal_projections"] == 2
    assert counts["centre_projections_reused"] == 1
    assert counts["other_projections"] == 1
    assert counts["fused_passes"] == 3
    assert counts["centre_track_terms_reused"] == (2 if cache else 0)


@pytest.mark.parametrize("correction", [-0.0, 1.0])
def test_correction_outside_fused_scope_uses_released_phase_pass(correction):
    scan, tracks, project = fixture("F")
    args = (scan, tracks, scan.search_region.center, {"3": correction, "7": 0.0})
    with patch.object(discovery, "phase_linear_frequency", project):
        expected = statistics(*args)
        with shared_rank_preparation(scan) as counts:
            actual = statistics(*args)
    equal_statistics(expected, actual)
    assert counts["fused_passes"] == 0
