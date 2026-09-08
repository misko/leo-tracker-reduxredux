import json

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.presence_decision_challenge import (
    PROTOCOL,
    associated,
    audit_control_labels,
    cases,
    continuous_pilot,
    generate,
    passing,
    summarize,
)


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_independent_continuous_model_matches_published_first_frame(rate, edge):
    expected = qin_edge_pilot_frame(rate, edge)
    actual = continuous_pilot(rate, edge, 0.0)
    np.testing.assert_allclose(actual[:len(expected)], expected, atol=2e-7, rtol=2e-7)
    assert not actual.flags.writeable
    assert not np.allclose(continuous_pilot(rate, edge, 0.5), actual)


def spec(kind, **updates):
    return dict(rate_hz=2500000, edge="lower", seed=99001, kind=kind,
                start_ms=40.0, duration_ms=20.0) | updates


def test_pilot_is_confined_to_declared_interval_and_repeatable():
    signal, truth = generate(spec("pilot", snr_db=0.0))
    noise, _ = generate(spec("white_noise"))
    change = np.any(signal != noise, axis=1).reshape(6, 50000).any(axis=1)
    assert change.tolist() == [False, False, True, False, False, False]
    np.testing.assert_array_equal(generate(spec("pilot", snr_db=0.0))[0], signal)
    assert truth["starlink_model_present"] and truth["clipped_components"] == 0
    assert 0 < truth["epoch_samples"] % 1 < 1


def test_boundary_burst_spans_two_slices():
    signal, truth = generate(spec("boundary_pilot", start_ms=38.0, duration_ms=4.0, snr_db=6.0))
    noise, _ = generate(spec("white_noise"))
    change = np.any(signal != noise, axis=1).reshape(6, 50000).any(axis=1)
    assert change.tolist() == [False, True, True, False, False, False]
    assert truth["starlink_model_present"]


@pytest.mark.parametrize("kind", ["white_noise", "colored_noise", "tone", "two_tones",
                                  "pulsed_tone", "chirp", "clipped_tones", "wrong_pilot"])
def test_original_control_labels_and_quantization_are_preserved(kind):
    # wrong_pilot retains the frozen label, but is timing-ambiguous, not a
    # valid hard negative. The separate label audit must say so explicitly.
    iq, truth = generate(spec(kind))
    assert iq.shape == (300000, 2) and iq.dtype == np.int16
    assert not truth["starlink_model_present"]
    assert (truth["clipped_components"] > 0) == (kind == "clipped_tones")


def test_frozen_case_inventory_and_development_threshold_are_explicit():
    protocol = json.loads(PROTOCOL.read_text())
    rows = list(cases(protocol))
    assert len(rows) == 528
    assert len({json.dumps(r, sort_keys=True) for r in rows}) == 528
    assert len(set(s["session_id"] for s in protocol["rf_sessions"])) == 4
    assert protocol["policies"]["frozen_absolute_score_hypothesis"] == {
        "minimum_exact_score": 0.175, "minimum_margin": 0.025,
    }
    assert not protocol["absence_policy_enabled"] and not protocol["live_rf_authorized"]


def test_decision_needs_complete_fractional_work_and_both_thresholds():
    policy = {"minimum_exact_score": 0.175, "minimum_margin": 0.025}
    good = {"fractional_complete": 1, "exact_score": 0.175, "margin": 0.025}
    candidates = [good, good | {"fractional_complete": 0}, good | {"exact_score": 0.174},
                  good | {"margin": 0.024}]
    assert passing(candidates, policy) == [good]


def test_association_requires_time_frequency_and_signal_support():
    _, truth = generate(spec("pilot", snr_db=0.0))
    limits = {"maximum_circular_epoch_difference_us": 2,
              "maximum_cfo_difference_hz": 8000}
    epoch = truth["epoch_samples"]
    candidate = {"epoch": int(epoch), "fractional_offset_samples": epoch % 1,
                 "tracking_cfo_hz": truth["cfo_hz"]}
    assert associated(candidate, truth, 2, limits)
    assert not associated(candidate, truth, 0, limits)
    assert not associated(candidate | {"tracking_cfo_hz": 1e7}, truth, 2, limits)
    assert not associated(candidate | {"epoch": int(epoch) + 100}, truth, 2, limits)


def test_summary_does_not_hide_false_flags_or_unassociated_positives():
    protocol = json.loads(PROTOCOL.read_text())
    rows = [
        {"truth": dict(spec("tone"), starlink_model_present=False),
         "decisions": {name: {"flagged": True, "associated": False}
                       for name in protocol["policies"]}},
        {"truth": dict(spec("pilot"), starlink_model_present=True, snr_db=0.0),
         "decisions": {name: {"flagged": True, "associated": False}
                       for name in protocol["policies"]}},
    ]
    for result in summarize(rows, protocol).values():
        assert result["false_flags"] == 1 and result["primary_flag_fraction"] == 1
        assert result["primary_associated_fraction"] == 0
        assert not result["bounded_challenge_pass"]


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_timing_ambiguous_control_audit_never_turns_original_failure_into_pass(rate):
    protocol = json.loads(PROTOCOL.read_text())
    epoch = 123.25
    shifted = epoch + 17 * 4.4e-6 * rate
    candidate = {"epoch": int(shifted), "fractional_offset_samples": shifted % 1,
                 "fractional_complete": 1, "exact_score": 0.4, "margin": 0.3}
    row = {"truth": dict(spec("wrong_pilot", rate_hz=rate),
                         starlink_model_present=False, epoch_samples=epoch),
           "selected_window": 5, "candidates": [candidate],
           "decisions": {p: {"flagged": True, "associated": False}
                         for p in protocol["policies"]}}
    hard = row | {"truth": row["truth"] | {"kind": "tone"}}
    for audited in audit_control_labels([row, hard], protocol).values():
        assert not audited["qualified"] and audited["original_gate_preserved"]
        assert audited["nonpilot_control_cases"] == audited["flags_in_nonpilot_controls"] == 1
        assert audited["timing_ambiguous_controls"] == 1
        assert audited["flags_in_timing_ambiguous_controls"] == 1
        assert audited["predicted_shift_us"] == pytest.approx(74.8)
        assert audited["accepted_candidate_timing_residual_samples"] == pytest.approx([0], abs=1e-9)


@pytest.mark.parametrize("updates", [{"rate_hz": 10}, {"edge": "bad"},
                                     {"start_ms": -1}, {"duration_ms": 1000},
                                     {"snr_db": float("nan")}, {"kind": "bad"}])
def test_unbounded_or_invalid_control_rejected(updates):
    with pytest.raises(ValueError):
        generate(spec("pilot", snr_db=0.0) | updates)
