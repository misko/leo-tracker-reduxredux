"""Public-port adaptation preserves gaps, probe offsets and physical identities."""

from copy import deepcopy

import pytest

from leo.analysis.research.public_tracking_points import public_tracking_points


def example():
    candidate = dict(
        candidate_rank=0,
        fractional_margin=0.1,
        fractional_tracking_cfo_hz=123.0,
        passed_fractional_margin_gate=True,
    )
    probe = dict(
        receiver_id=0,
        visit_index=0,
        probe_index=0,
        channel=1,
        edge="lower",
        actual_rf_hz=11e9,
        valid_start_counter=1000,
        payload_start_sample=0,
        probe_start_ms=0,
        candidates=[candidate],
    )
    return dict(
        session_id="capture",
        qualified=True,
        sample_rate_hz=1000,
        probe_ms=20,
        input_manifest_sha256="sha256:example",
        probes=[probe],
        timing=dict(
            session_id="capture",
            qualified=True,
            sample_rate_hz=1000,
            session_start_device_sample_counter=0,
            begin_before_realtime_ns=10000000000,
            begin_before_monotonic_ns=0,
            begin_after_realtime_ns=10100000000,
            begin_after_monotonic_ns=100000000,
            terminal_realtime_ns=12000000000,
            terminal_monotonic_ns=2000000000,
            first_sample_earliest_utc_ns=10000000000,
            first_sample_latest_utc_ns=10100000000,
            first_sample_estimate_utc_ns=10050000000,
        ),
    )


def test_device_gaps_and_multiple_probes_in_one_visit_are_preserved():
    doc = example()
    second = deepcopy(doc["probes"][0])
    second.update(probe_index=1, probe_start_ms=120)
    doc["probes"].append(second)
    third = deepcopy(second)
    third.update(
        visit_index=1, valid_start_counter=5000, probe_start_ms=0, payload_start_sample=200
    )
    doc["probes"].append(third)
    points, metadata = public_tracking_points(doc)
    assert [p["time_s"] for p in points] == pytest.approx([1.01, 1.13, 5.01])
    assert len({p["observation_id"] for p in points}) == 3
    assert metadata["anchor_utc_ns"] == 10050000000
    assert metadata["causal_cutoff_utc_ns"] == 10000000000


def test_physical_identity_is_independent_of_chosen_peak():
    doc = example()
    first, _ = public_tracking_points(doc)
    doc["probes"][0]["candidates"][0]["fractional_tracking_cfo_hz"] += 1000
    second, _ = public_tracking_points(doc)
    assert first[0]["observation_id"] == second[0]["observation_id"]
    doc["probes"][0]["candidates"][0]["passed_fractional_margin_gate"] = False
    assert public_tracking_points(doc)[0] == []


def test_duplicate_support_including_gate_rejected_probes_fails():
    doc = example()
    duplicate = deepcopy(doc["probes"][0])
    duplicate["candidates"] = []
    doc["probes"].append(duplicate)
    with pytest.raises(ValueError, match="physical probe"):
        public_tracking_points(doc)


@pytest.mark.parametrize("mutation", ["unqualified", "wrong_midpoint", "clock_step", "bad_rf"])
def test_unqualified_or_inconsistent_authority_is_rejected(mutation):
    doc = example()
    if mutation == "unqualified":
        doc["qualified"] = False
    elif mutation == "wrong_midpoint":
        doc["timing"]["first_sample_estimate_utc_ns"] += 1
    elif mutation == "clock_step":
        doc["timing"]["terminal_realtime_ns"] += 3000000000
    else:
        doc["probes"][0]["actual_rf_hz"] = -1
    with pytest.raises(ValueError):
        public_tracking_points(doc)
