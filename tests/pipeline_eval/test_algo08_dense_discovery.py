from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import discovery
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.retained_track_likelihood import PERIOD, profile, whitening
from tools.pipeline_eval.variants.algo08_dense_discovery import DenseWhiteProfile, dense_discovery


def same_terms(expected, actual):
    assert expected.keys() == actual.keys()
    for name, values in expected.items():
        assert values.shape == actual[name].shape
        assert values.dtype == actual[name].dtype
        assert values.tobytes() == actual[name].tobytes(), name


@pytest.mark.parametrize("order", ("C", "F"))
def test_whole_catalogue_profile_preserves_every_score_and_tie(order):
    rng = np.random.default_rng(6)
    cached = DenseWhiteProfile(profile)
    for count in (93, 1, 17, 93):
        y = rng.uniform(-PERIOD, PERIOD, count)
        f = np.array(rng.uniform(-PERIOD, PERIOD, (7, count)), order=order)
        f[0] = f[1] = y
        f[2] = y - PERIOD / 2
        f[3] = y + PERIOD / 2
        f[4] = np.nextafter(f[3], np.inf)
        w, volume = whitening(np.arange(count, dtype=float))
        expected = profile(y, f, w, volume)
        actual = cached(y, f, w, volume)
        same_terms(expected, actual)
        assert np.argmin(actual["cost"]) == 0
        # The next call reuses scratch but cannot mutate returned diagnostics.
        same_terms(profile(-y, f, w, 3.0), cached(-y, f, w, 3.0))
        same_terms(expected, actual)
    assert cached.calls == 8
    assert cached.buffer.size == 7 * 93


def test_profile_falls_back_for_unsupported_whitening_and_scratch_size():
    y = np.arange(5, dtype=float)
    predicted = np.array([y, -y, y + 1])
    white, volume = whitening(y, correlated_sigma_hz=150)
    cached = DenseWhiteProfile(profile)
    same_terms(profile(y, predicted, white, volume), cached(y, predicted, white, volume))
    limited = DenseWhiteProfile(profile, scratch_bytes=32)
    white, volume = whitening(y)
    same_terms(profile(y, predicted, white, volume), limited(y, predicted, white, volume))
    assert cached.calls == limited.calls == 0


def test_association_reuse_scoped_to_explore_and_matching_objects(monkeypatch):
    state, base = {}, object()
    calls = []

    def associate(state, base, point, method, *, all_tracks=False):
        result = object()
        calls.append(result)
        return result

    def explore(scan):
        current = scan.association(state, base, [1, 2], "receiver_smooth")
        assert scan.association(state, base, [1, 2], "receiver_smooth") is current
        assert scan.association(dict(state), base, [1, 2], "receiver_smooth") is not current
        return current

    scan = SimpleNamespace(association=associate)
    monkeypatch.setattr(discovery, "explore", explore)
    with dense_discovery(scan, reuse_associations=True) as counts:
        first = discovery.explore(scan)
        assert discovery.explore(scan) is not first
    assert scan.association is associate
    assert counts["association_reused"] == 2
    assert len(calls) == 4


def test_association_reuse_keeps_search_positions_and_scan_regions_distinct(monkeypatch):
    state, base = {}, object()
    center, edge = (0., 0.), (15., 0.)
    northern = SearchRegion((52., 12.), 30.)
    southern = SearchRegion((-36., 145.), 30.)
    calls = []

    def scan_for(region):
        def associate(state, base, point, method, *, all_tracks=False):
            coordinates = region.latlon(point)
            calls.append(coordinates)
            return coordinates

        return SimpleNamespace(association=associate)

    def explore(scan):
        return [scan.association(state, base, point, "receiver_smooth")
                for point in (center, center, edge)]

    first, second = scan_for(northern), scan_for(southern)
    monkeypatch.setattr(discovery, "explore", explore)
    with dense_discovery(first, reuse_associations=True) as counts:
        assert discovery.explore(first) == [northern.center, northern.center, northern.latlon(edge)]
        assert discovery.explore(second) == [southern.center, southern.center, southern.latlon(edge)]
    assert counts["association_reused"] == 1
    assert calls == [northern.center, northern.latlon(edge), southern.center,
                     southern.center, southern.latlon(edge)]
