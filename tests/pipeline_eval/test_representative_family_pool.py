from collections import Counter
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("representative_family_pool")


def test_representatives_cover_each_receiver_actual_rf_and_time_third(pool):
    def track(key, receiver, rf, times):
        return dict(key=key, receiver=receiver, rf_hz=rf, times=np.array(times))

    tracks = [track("later", 1, 10., [220, 230, 240]), track("short", 1, 10., [5, 10]),
              track("long", 1, 10., [20, 25, 30]), track("other_rf", 1, 11., [20, 25]),
              track("other_rx", 2, 10., [20, 30]), track("ignored", 1, 10., [70, 80, 90])]
    assert set(pool.representatives(SimpleNamespace(curved=list(range(5)), tracks=tracks), 300.)) == {0, 2, 3, 4}


def test_representative_phase_shape_requires_full_time_visibility_and_bounded_drift(pool):
    times = np.linspace(0., 50., 21)
    observed = times * times
    frequency = np.array([observed - 10 * times, observed - 40 * times, observed, np.zeros(len(times))])
    elevation = np.ones_like(frequency)
    elevation[2, 9] = -0.1
    value = pool.phase_shape(observed, frequency, np.zeros_like(frequency), elevation, times, np.ones(4), 150.)
    assert value[0] == pytest.approx(0.)
    assert np.isinf(value[1:3]).all()


def test_compact_catalogue_preserves_every_track_and_original_axis(pool, monkeypatch):
    times = np.array([0., 5., 10.])
    sky = dict(time_s=times, norad=np.array([21, 47, 82]), phase_sigma_s=np.ones(3), position_km=np.arange(9).reshape(3, 3))
    full = SimpleNamespace(tracks=["unchanged"], times=times, sky=sky, norads=sky["norad"],
                           elements={str(n): {} for n in sky["norad"]}, curved=[0], previous_shape_cache={0: "original"})
    seen = []
    monkeypatch.setattr(pool.scan_kernel, "prepare_phase_geometry", lambda reduced, clock: seen.append((reduced, clock)))
    compact = pool.compact_catalogue(full, np.array([1, 2]))
    assert compact.tracks is full.tracks and compact.times is full.times
    assert seen[0][1] is times and seen[0][0]["norad"].tolist() == [47, 82]
    assert compact.previous_shape_cache == {} and full.previous_shape_cache == {0: "original"}
    monkeypatch.setattr(pool.discovery, "zero_state", lambda scan: {"phases": [0] * len(scan.norads)})
    restored = pool.restore(full, dict(seed={"rows": [dict(candidate_index=0, candidate_norad=47)]}, aliases=[-1]),
                            np.array([1, 2]))
    assert restored["seed"]["rows"] == [dict(candidate_index=1, candidate_norad=47)]
    assert restored["aliases"] == [-1]


@pytest.mark.parametrize("points,costs,rescan", [(20, [1., 4.], False), (15, [1., 4.], True), (20, [1., 1.5], True)])
def test_salvage_reuses_full_points_and_widens_ambiguous_support(pool, points, costs, rescan):
    samples = dict(times=np.arange(20.))
    calls = []

    def fine(_kernel, _scan, track, y, noise, _rf, labels, _point):
        assert track is samples and len(y) == len(noise) == 20
        calls.append(set(labels))
        found = [dict(candidate_index=j, points=points if j < 3 else 20, cost=costs[j - 1] if j < 3 else 0.)
                 for j in sorted(labels)]
        return found, 7

    counts = Counter()
    found, supports = pool.fine_pool(fine, {1, 2}, counts, None, None, samples, samples["times"], np.ones(20),
                                     1., {1, 2, 3}, [0., 0.])
    assert calls == ([{1, 2}, {3}] if rescan else [{1, 2}])
    assert found[0]["candidate_index"] == (3 if rescan else 1)
    assert supports == 7 and counts["rescanned_tracks"] == int(rescan)
