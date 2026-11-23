from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def audit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import live_orbit_setup_audit

    return live_orbit_setup_audit


def bulk(audit, stage, keys, times, position=0.):
    dimensions = (len(keys), len(times), 3)
    state = SimpleNamespace(utc_ns=times, position_teme_km=np.full(dimensions, position),
                            velocity_teme_km_s=np.ones(dimensions), error_code=np.zeros(dimensions[:2], dtype=np.int32))
    return audit.BulkCall(stage, keys, state, 100)


def test_known_overlap_gets_first_claim_and_never_double_counts(audit):
    a, b = ("1 object A", "2 object A"), ("1 object B", "2 object B")
    calls = [bulk(audit, "other", (a,), (2, 3)),
             bulk(audit, "regional_bank", (a, b), (2, 3)),
             bulk(audit, "regional_proof", (b, a), (3, 4))]
    first, second, third = audit.compare_bulk(calls)
    assert first["new_overlap"] == 0
    assert second["new_overlap"] == 2
    assert third["known_overlap"] == 2
    assert third["new_overlap"] == 0
    assert third["previous_stage_cells"] == {"regional_bank": 2}
    assert audit.budgets([first, second, third], audit.Trace()) == {
        "known_partial_cell_estimate_ns": 50,
        "new_partial_cell_estimate_ns": 50,
        "new_whole_call_ns": 0,
        "new_affected_call_inclusive_ns": 100,
        "new_total_cell_proportional_ns": 50,
    }


def test_element_times_status_and_bits_must_all_match(audit):
    key = "1 123", "2 123 initial elements"
    updated = "1 123", "2 123 updated elements"
    initial = bulk(audit, "regional_bank", (key,), (1, 2, 3, 4))
    other = bulk(audit, "other", (updated, key), (2, 3, 4, 5))
    other.state.position_teme_km[1, 0, 0] = -0.
    other.state.error_code[1, 1] = 1
    _, later = audit.compare_bulk([initial, other])
    assert later["new_overlap"] == 1
    assert later["disagreeing_comparisons"] == 2


def test_exact_scalar_keys_include_time_and_bits(audit):
    trace = audit.Trace()
    trace.bind(object(), ("a", "b"))
    values = iter((0., 0., 0., -0.))

    def parse(*_):
        return SimpleNamespace(sgp4=lambda *args: (0, (next(values), 1., 2.), (3., 4., 5.)))

    tracked = trace.phase_elements(parse)
    for time in (0., 1., 0., 0.):
        tracked.twoline2rv("a", "b").sgp4(100., time)
    assert trace.phase["preparsed_elsewhere_calls"] == 1
    assert trace.phase["repeated_parse_calls"] == 3
    assert trace.phase["state_calls"] == 4
    assert trace.phase["repeated_state_calls"] == 1
    assert trace.phase["disagreeing_states"] == 1


def test_snapshot_comparison_uses_entire_text_and_executes_all_validations(audit):
    trace = audit.Trace()
    calls = []

    def record(text):
        calls.append(text)
        return text.splitlines()

    parser = trace.snapshot_parser(record)
    for value in ("a\nb", "a\nb", "a\nb\n"):
        assert parser(value) == ["a", "b"]
    assert calls == ["a\nb", "a\nb", "a\nb\n"]
    assert trace.records["repeated_calls"] == 1
    assert trace.records["repeated_records"] == 2
