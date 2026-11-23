from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("survey_channels")


def rows(count):
    return [dict(visit_index=i + 2, valid_start_counter=100 * i, actual_rf_hz=1000 * (i % 8),
                 channel=i % 8, receiver_id=antenna,
                 candidates=[{"signal": i}] if i % 8 in (2, 5) else [])
            for i in range(count) for antenna in range(2)]


def test_selection_ignores_suffix_signal_and_keeps_complete_histories(policy):
    probes = rows(384)
    keep, stats = policy.choose(probes)
    assert stats["survey_visits"] == 64 and stats["selected_groups"] == [(2000, 2), (5000, 5)]
    changed = probes[:128] + [dict(p, candidates=[] if p["candidates"] else [{}]) for p in probes[128:]]
    assert policy.choose(changed) == (keep, stats)
    assert keep == {i + 2 for i in range(384) if i < 64 or i % 8 in (2, 5)}


def test_balances_spectrum_ties_and_handles_short_inputs(policy):
    probes = [dict(p, candidates=[]) for p in rows(384)]
    _, stats = policy.choose(probes)
    assert stats["selected_groups"] == [(0, 0), (4000, 4)]
    assert policy.choose(probes[:2])[0] == {2}
    with pytest.raises(ValueError):
        policy.choose(probes[:-1])
    with pytest.raises(ValueError, match="stereo"):
        policy.choose([dict(probes[0], channel=99), *probes[1:]])


def test_worst_quarter_precedes_pooled_yield(policy):
    probes = rows(384)
    for i, probe in enumerate(probes[:128]):
        visit = i // 2
        hit = (visit % 8 == 0 and visit >= 16) or (visit % 8 == 1 and probe["receiver_id"] == 0)
        probe["candidates"] = [{}] if hit else []
    assert policy.choose(probes)[1]["selected_groups"][0] == (1000, 1)
