from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module


def test_mask_is_local_to_each_rf_and_includes_partial_cycles(research):
    factors = [dict(candidate_rank=n, fractional_margin=n + 0.5, passed_fractional_margin_gate=True) for n in (0, 1)]
    rows = [dict(receiver_id=rx, channel=i % 2, actual_rf_hz=100 + i % 2, edge="lower",
                 visit_index=i, valid_start_counter=1000 + i, candidates=factors)
            for i in range(19) for rx in (0, 1)]
    selected, stats = research("mixed_aperture_availability").select(rows, [1] * len(rows))
    assert [selected[i][0]["candidate_rank"] if selected[i] else None for i in range(0, len(rows), 2)] == [
        1, 1, 0, 0, None, None, 0, 0, None, None, 0, 0, None, None, 0, 0, 1, 1, 0]
    assert selected[::2] == selected[1::2] and sum(stats["counts"].values()) == len(rows)
    rows[1]["receiver_id"] = 0
    with pytest.raises(ValueError):
        research("mixed_aperture_availability").select(rows, [1] * len(rows))


def test_two_receiver_positive_shortcuts_only_after_complete_proof(research):
    module = research("early_region")
    reader = SimpleNamespace(root="/archive")
    for complete, expected_call in ((True, False), (False, True)):
        audit, called = [], []
        def original(*args, **kwargs):
            called.append(True)
            return {"status": "ok"}
        def proof(*args, **kwargs):
            return {"complete": complete, "would_withhold": True}
        outcome = module.before_fit(original, reader, proof, audit, lambda *_: None)({"tracks": {}}, object(), None, {})
        assert bool(called) is expected_call and len(audit) == 1
        assert outcome["status"] == ("ok" if expected_call else "withheld")


def test_scoped_region_reuse_respects_objects_and_full_probes(research):
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    region, tracks, catalogue = object(), {}, object()
    reader = SimpleNamespace(root="/archive")
    calls, audit = [], []

    def probe(*args, **kwargs):
        calls.append(kwargs)
        return {"complete": True, "would_withhold": False}

    def solve(*args, **kwargs):
        check = regional_bound_guard.causal_probes
        check(tracks, reader, region, terminal_only=True, catalogue=catalogue)
        check({}, reader, region, terminal_only=True)
        check(tracks, reader, object(), terminal_only=True)
        check(tracks, reader, region, terminal_only=True, catalogue=object())
        check(tracks, reader, region)
        return {"status": "ok"}

    route = research("early_region").before_fit(solve, reader, probe, audit, lambda *_: catalogue)
    assert route({"tracks": tracks}, region, None, {})["status"] == "ok"
    assert len(calls) == 5 and audit[0]["reused"] == 1
