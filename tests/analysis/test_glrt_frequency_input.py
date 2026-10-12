from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.glrt_frequency_input import frequency_evidence


def document():
    candidate = dict(
        fractional_tracking_cfo_hz=120.0,
        fractional_margin=0.3,
        integer_epoch_sample=10,
        fractional_epoch_offset_samples=0.1,
    )
    probe = dict(
        receiver_id=0,
        channel=1,
        valid_start_counter=100000,
        actual_rf_hz=11e9,
        candidates=[candidate, deepcopy(candidate)],
    )
    return dict(
        source=dict(session_id="test", probes=[probe], sample_rate_hz=2500000, probe_ms=20),
        clock_anchor=dict(
            sample_counter=0,
            before=dict(realtime_ns=1000000000, monotonic_ns=0),
            after=dict(realtime_ns=1200000000, monotonic_ns=200000000),
        ),
        delivery_clocks=[],
        last_sample_counter=150000,
        provenance={},
    )


def test_duplicate_candidates_are_collapsed_and_counter_time_preserved():
    data, rf, meta = frequency_evidence(document())
    assert meta["duplicate_candidates_removed"] == 1
    assert meta["distinct_candidates"] == 1
    assert meta["utc_half_width_s"] == 0.1
    assert meta["causal_cutoff_utc_ns"] == 1000000000
    assert data.time_s[0] == pytest.approx(0.05)
    np.testing.assert_array_equal(data.candidate_weight, [[1, 0]])


def test_periodic_alias_is_one_peak_when_the_epoch_matches():
    doc = document()
    period = 1 / 4.4e-6
    doc["source"]["probes"][0]["candidates"][1]["fractional_tracking_cfo_hz"] += period
    _, _, meta = frequency_evidence(doc, alias_period_hz=period)
    assert meta["duplicate_candidates_removed"] == 1
    assert meta["distinct_candidates"] == 1


def test_overlapping_support_is_not_independent_evidence():
    doc = document()
    doc["source"]["probes"].append(deepcopy(doc["source"]["probes"][0]))
    doc["source"]["probes"][1]["valid_start_counter"] += 20000
    with pytest.raises(ValueError, match="overlapping"):
        frequency_evidence(doc)


def test_missing_timing_fails_and_empty_candidates_are_neutral():
    doc = document()
    doc["source"]["probes"][0]["candidates"] = []
    data, _, meta = frequency_evidence(doc)
    assert data.signal_probability[0] == 0
    assert meta["empty_factors"] == 1
    doc["clock_anchor"] = None
    with pytest.raises(ValueError, match="UTC"):
        frequency_evidence(doc)
