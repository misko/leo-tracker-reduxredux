import sys
from types import ModuleType, SimpleNamespace

from tools.pipeline_eval.variants import v5_discovery_memory


def fake_discovery(monkeypatch, explore):
    numerical = ModuleType("leo.analysis.localization_v3")
    numerical.discovery = SimpleNamespace(explore=explore)
    monkeypatch.setitem(sys.modules, numerical.__name__, numerical)
    return numerical.discovery


def test_reuses_only_the_identical_pair_and_releases_after_probe(monkeypatch):
    calls = []

    def association(state, base, point, method, *, all_tracks=False):
        calls.append((state, base, point, method, all_tracks))
        return object()

    def explore(scan, state, point, method):
        base = object()
        first = scan.association(state, base, point, method)
        repeated = scan.association(state, base, point, method)
        other = scan.association(state, base, point, method, all_tracks=True)
        return first, repeated, other

    discovery = fake_discovery(monkeypatch, explore)
    scan = SimpleNamespace(association=association)
    with v5_discovery_memory.reuse_discovery_association() as counts:
        for _ in range(2):
            first, repeated, other = discovery.explore(scan, {}, object(), "receiver_smooth")
            assert first is repeated and other is not first
            assert scan.association is association
    assert counts == dict(explorations=2, computed_associations=4, reused_associations=2)
    assert len(calls) == 4 and discovery.explore is explore


def test_nonreusable_method_runs_both_original_calls(monkeypatch):
    def explore(scan, state, point, method):
        base = object()
        return tuple(scan.association(state, base, point, method) for _ in range(2))

    discovery = fake_discovery(monkeypatch, explore)
    scan = SimpleNamespace(association=lambda *args: object())
    with v5_discovery_memory.reuse_discovery_association() as counts:
        first, repeated = discovery.explore(scan, {}, object(), "orbit_em")
    assert first is not repeated
    assert not counts
