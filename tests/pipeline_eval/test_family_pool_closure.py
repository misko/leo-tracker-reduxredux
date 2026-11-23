from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def closure(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("family_pool_closure")


def test_nominal_anchor_reuse_reassembles_exact_rows_and_projects_only_admissions(closure, monkeypatch):
    labels = np.array([90, 100, 110, 120])
    times = np.array([0., 5., 10.])
    sky = dict(norad=labels, time_s=times)
    full = SimpleNamespace(sky=sky, times=times)
    calls = []

    def project(geometry, latitude, longitude, **_kwargs):
        calls.append(tuple(geometry["norad"]))
        f = geometry["norad"][:, None] + times + latitude + longitude * 2
        return f, f / 8, f * 2

    monkeypatch.setattr(closure.scan_kernel, "prepare_phase_geometry", lambda current, _times: current)
    cache = closure.AnchorPlanes(full, project, byte_limit=500)
    initial = np.array([0, 3])
    compact = SimpleNamespace(geometry=dict(norad=labels[initial]))
    read = cache.scoped(compact, initial)
    read(compact.geometry, 2., 3.)
    read(compact.geometry, 2., 3.)
    expanded = np.array([0, 2, 3])
    compact = SimpleNamespace(geometry=dict(norad=labels[expanded]))
    actual = cache.scoped(compact, expanded)(compact.geometry, 2., 3.)
    assert calls == [(90, 120), (110,)]
    expected = project(compact.geometry, 2., 3.)
    assert all(np.array_equal(actual[i], expected[i]) for i in range(3))
    assert cache.counts["reused_family_rows"] == 4
    assert cache.counts["incremental_projection_calls"] == 1
    assert cache.retained < cache.byte_limit
    assert all(not a.flags.writeable for a in actual)


def test_nominal_cache_respects_memory_and_leaves_other_states_uncached(closure):
    clock = np.array([0., 1.])
    full = SimpleNamespace(sky={}, times=clock)
    geometry, shifted = object(), object()
    calls = []

    def project(grid, *_values, **_options):
        calls.append(grid)
        return tuple(np.zeros((2, 2)) for _ in range(3))

    cache = closure.AnchorPlanes(full, project, byte_limit=1)
    read = cache.scoped(SimpleNamespace(geometry=geometry), np.array([0, 1]))
    read(geometry, 0., 0.)
    read(geometry, 0., 0.)
    read(shifted, 0., 0.)
    assert calls == [geometry, geometry, shifted]
    assert cache.retained == 0 and cache.counts["over_budget"] == 2


def test_round_and_family_caps_are_checked_after_a_complete_outside_scan(closure):
    outside = [{"candidate_index": i} for i in (1, 2, 2)]
    assert closure.next_additions(outside, {1}, round_number=2, previously_added=7) == {2}
    assert closure.next_additions(outside, {1, 2}, round_number=3, previously_added=8) == set()
    for round_number, already in ((3, 0), (2, 8)):
        with pytest.raises(ValueError, match="family or round cap"):
            closure.next_additions(outside, {1}, round_number=round_number, previously_added=already)


def test_unchanged_assignment_reuses_only_exact_fit_and_rechecks_catalogue(closure, monkeypatch):
    class Region:
        def latlon(self, point):
            return point

        def native_point(self, scan, point):
            return point

    region = Region()
    data = [dict(component="curve", candidate_index=0, candidate_norad=100)]
    guard = []

    def associate(*_args):
        guard.append(1)
        return 0., [dict(component="curve", candidate_index=1, candidate_norad=200, compatible=True)], {}, None

    full = SimpleNamespace(norads=np.array([100, 200, 300]), curved=[0], geometry=object(), times=np.array([4., 9.]),
                           tracks=[dict(times=[4., 9.])], association=associate)
    chosen = dict(seed=dict(rows=data, state={}), aliases=[-1])
    ranked_rosters = []
    refined = []
    original = dict(tracks=dict(metadata=dict(duration_s=300.)), noise={})
    monkeypatch.setattr(closure.v5_core, "scan_context", lambda *_: full)
    monkeypatch.setattr(closure, "family_pool", lambda *_: (np.array([0]), [0], 2))
    monkeypatch.setattr(closure, "compact_catalogue", lambda _full, labels: SimpleNamespace(geometry=object(), roster=list(labels)))
    monkeypatch.setattr(closure.v5_core, "ranked_initial_nodes", lambda compact: ranked_rosters.append(compact.roster) or [chosen])
    monkeypatch.setattr(closure.discovery, "phase_linear_frequency", lambda *_: None)
    monkeypatch.setattr(closure, "restore", lambda *_: chosen)
    monkeypatch.setattr(closure, "zero_reference_objective", lambda *_: 3.)
    monkeypatch.setattr(closure, "refine", lambda *_: refined.append(1) or (np.zeros(2), {}, {0: 0.}, 1.))
    measured, roster = {}, set()
    node, *_ = closure.choose_cold(original, region, None, measured, roster)
    rounds = measured["pool_closure"]["rounds"]
    assert node == chosen and ranked_rosters == [[0], [0, 1]] and roster == {0, 1}
    assert len(refined) == 1 and len(guard) == 2
    assert rounds[0]["admitted_norads"] == [200]
    assert rounds[1]["cached_zero_scores"] == 1 and rounds[1]["reused_exact_fit"]
    assert rounds[1]["newly_admitted_winner_tracks"] == {}
