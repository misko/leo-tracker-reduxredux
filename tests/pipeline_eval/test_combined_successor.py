from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import combined_successor as successor
import nomination_handoff


def node(index):
    return {"seed": {"rows": [{"component": "track", "candidate_index": index,
                               "candidate_norad": index+10}]}, "aliases": [0]}


def make_route(monkeypatch, speculative_nodes):
    active = False
    calls = []
    originals = [node(3), node(9), node(6)]
    screens = SimpleNamespace(screen_nodes=lambda *_: "ordinary-screen")

    def ready(*_):
        return object()

    def rank(scan):
        calls.append((active, scan))
        return speculative_nodes if active else originals

    @contextmanager
    def trial(trace):
        nonlocal active
        active = True
        trace["paid_centres"] = 2
        try:
            yield
        finally:
            active = False

    core = SimpleNamespace(scan_context=ready, ranked_initial_nodes=rank)
    monkeypatch.setattr(nomination_handoff, "screen_port", lambda stock, consume: lambda scan, rows: consume(scan, rows))
    monkeypatch.setattr(successor, "two_seeds", trial)
    state = successor.SuccessorHandoff(core, screens, rank, {})
    prepared = {"tracks": {"tracks": []},
                "sky": {"metadata": {}, "nominal_elements": {}, "previous_receipt": {},
                        "previous_tle": [], "bank": {"finite": np.zeros(3)}}}
    args = (prepared, object(), "noise", object(), "previous")
    return state, args, core, screens, originals, calls


def completed(nodes):
    return {i: (value, np.zeros(2), {value["seed"]["rows"][0]["candidate_index"]: 0.}, 4.)
            for i, value in enumerate(nodes)}


def test_speculative_rank_cannot_supply_named_prefix_even_with_same_signed_rows(monkeypatch):
    candidate = [node(3), node(9), node(6)]
    handoff, args, core, screens, ordinary, calls = make_route(monkeypatch, candidate)
    with handoff.producer():
        scan = core.scan_context(*args)
        # Even a stale checkpoint from before speculation is invalidated.
        handoff.nodes, handoff.checkpoint = ordinary, ["old-prefix"]
        nodes = core.ranked_initial_nodes(scan)
        handoff.capture(scan, nodes, completed(nodes))
        assert nodes == ordinary and handoff.checkpoint is None
        with handoff.fallback():
            actual = core.scan_context(*args)
            assert actual is not scan
            assert core.ranked_initial_nodes(actual) is ordinary
            assert screens.screen_nodes(actual, ordinary) == "ordinary-screen"
    assert calls == [(True, scan), (False, actual)]
    assert handoff.counts["speculative_prefix_sets_excluded"] == 1
    assert handoff.counts["rank_reuses"] == handoff.counts["prefixes_reused"] == 0


@pytest.mark.parametrize("mutate_bank", (False, True))
def test_retry_leaves_exact_handoff_and_its_bank_guard_intact(monkeypatch, mutate_bank):
    handoff, args, core, screens, ordinary, calls = make_route(monkeypatch, [node(3)] * 3)
    with handoff.producer():
        scan = core.scan_context(*args)
        rows = core.ranked_initial_nodes(scan)
        handoff.capture(scan, rows, completed(rows))
    assert rows is ordinary and len(calls) == 2 and not handoff.speculative
    if mutate_bank:
        args[0]["sky"]["bank"]["finite"][-1] = 1
    with handoff.fallback():
        resumed = core.scan_context(*args)
        assert core.ranked_initial_nodes(resumed) == ordinary
        prefix = screens.screen_nodes(resumed, ordinary)
    if mutate_bank:
        assert resumed is not scan and prefix is None
        assert handoff.counts["prefixes_reused"] == 0
    else:
        assert resumed is scan and len(prefix) == 3
        assert handoff.counts["prefixes_reused"] == 3


def test_unqualified_grid_binding_uses_original_sampler(monkeypatch):
    import grid_feature_projection as native
    import grid_phase_state_reuse as phase

    monkeypatch.setattr(native, "supported_cpu", lambda: False)
    ordinary, audit = phase.cached_predictive_grid, {}
    with successor.exact_grid("not opened", "not opened", audit):
        assert phase.cached_predictive_grid is ordinary
    assert audit == {"fallback": "unsupported_native_grid_binding"}


def test_worker_exports_grid_telemetry_after_leaving_native_context(monkeypatch, tmp_path):
    import aperture_trial
    import combined_successor as port
    import combined_successor_0289 as trial
    import empty_bootstrap as boot
    import solver_exception_live

    (tmp_path/"routed").mkdir()
    observed = {}
    monkeypatch.setattr(boot, "load_runtime", lambda: None)
    monkeypatch.setattr(trial, "read", lambda _: dict(sources={}, job_sha256=trial.JOB_SHA, libraries={}))
    monkeypatch.setattr(trial, "source_pins", dict)
    monkeypatch.setattr(trial, "admitted_libraries", dict)
    monkeypatch.setattr(solver_exception_live, "worker", lambda *_: boot.load_runtime())
    monkeypatch.setattr(aperture_trial, "write", lambda path, value: observed.update({path.name: dict(value)}))

    @contextmanager
    def native_grid(_projection, _template, audit):
        yield
        audit["projection"] = {"native_projection": 3}
        audit["assembly"] = {"assembly_calls": 2}

    monkeypatch.setattr(port, "exact_grid", native_grid)
    trial.worker(tmp_path)
    assert observed["combined-grid.json"] == {
        "projection": {"native_projection": 3}, "assembly": {"assembly_calls": 2}}
