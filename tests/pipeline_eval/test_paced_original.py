from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import paced_original as trial
from tools.pipeline_eval.qualification import paced_original_results as results


def valid_reference():
    return dict(
        visit=0,
        delivery_clock={"monotonic_ns": 100},
        sample_start=324,
        sample_end=200_324,
        status="processed",
        probes=[
            dict(
                receiver_id=rx,
                actual_rf_hz=123_000,
                candidates=[dict(passed_fractional_margin_gate=rx == 0)],
            )
            for rx in (0, 1)
        ],
    )


def test_reference_hash_covers_all_candidates_and_exact_schedule():
    packet = valid_reference()
    clock = dict(packet, arrival_ns=0, center_hz=123_000)
    (record,) = trial.bind_ledger([clock], [packet])
    assert record["full_visit_sha256"] == trial.pace.fingerprint(packet)
    with pytest.raises(ValueError, match="timing or physical admission"):
        trial.bind_ledger([dict(clock, sample_end=321)], [packet])
    bad = dict(packet, probes=list(reversed(packet["probes"])))
    with pytest.raises(ValueError, match="physical receivers"):
        trial.bind_ledger([clock], [bad])


def test_invalid_arrival_never_touches_an_active_valid_grid():
    calls = [{"applied": True}]
    grid = SimpleNamespace(calls=calls)
    window = SimpleNamespace(
        sequence=2,
        iq_sha256="hash",
        acquisition={"global_visit": 1},
        samples=np.zeros((1, 2, 2), dtype="<i2"),
    )

    def analyze(*args, **kwargs):
        return SimpleNamespace(
            sample_start=1,
            sample_end=2,
            generation=0,
            status="invalid_capture",
            reason="invalid",
            rf_mapping_authority="test",
        )

    result, _ = trial.original_visit((0, window, None, None), analyze, None, grid, False)
    assert result["probes"] == []
    assert grid.calls == [{"applied": True}]


def test_position_factors_include_only_actual_emissions_and_timely_positive_support():
    packet = valid_reference()
    emitted = dict(
        visit=0,
        outcome="emitted",
        full_visit_sha256=trial.pace.fingerprint(packet),
        emitted_ns=20_000_000,
        arrival_ns=0,
    )
    retained, probes, support = results.retained(
        [emitted, dict(visit=1, outcome="queue_drop")], [packet]
    )
    assert retained == [0]
    assert len(probes) == 2
    assert support["timely_positive_visits"] == 1
    assert support["timely_positive_probes"] == 1
    with pytest.raises(ValueError, match="full candidate packet"):
        results.retained([dict(emitted, full_visit_sha256="stale")], [packet])
