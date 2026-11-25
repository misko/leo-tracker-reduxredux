"""Keep exact stereo identity and dependent labels distinct."""

import pytest

from radio_consistency_custody import CFO_PERIOD, exact_pairs, grade, label_types, winner


def measurement(cfo, epoch, *, gate=True, margin=1, rank=0):
    return dict(passed_fractional_margin_gate=gate, fractional_margin=margin, candidate_rank=rank,
                fractional_tracking_cfo_hz=cfo, integer_epoch_sample=epoch,
                fractional_epoch_offset_samples=0)


def test_released_winner_tie_uses_smallest_rank_after_gate():
    eligible = measurement(100, 0)
    probe = {"candidates": [measurement(300, 0, gate=False, margin=10),
                           measurement(200, 0, rank=1), eligible]}
    assert winner(probe) is eligible
    assert winner({"candidates": []}) is None


def test_exact_clock_and_rf_pair_exposes_alias_without_changing_measured_cfo():
    def probe(radio, counter, rf, cfo, epoch):
        return dict(receiver_id=radio, valid_start_counter=counter, channel=7, actual_rf_hz=rf,
                    candidates=[measurement(cfo, epoch)])

    probes = [probe("RX1", 1, 10, 0, 0), probe("RX2", 1, 10, 3 * CFO_PERIOD + 125, 1),
              probe("RX1", 2, 10, 0, 0), probe("RX2", 2, 11, 0, 0)]
    rows = exact_pairs({"source": {"sample_rate_hz": 10_000_000, "probe_ms": 20,
                                    "session_id": "original", "probes": probes}})
    a, b, c = rows
    assert a["removed_cfo_periods"] == 3
    assert a["delta_signed_hz"] == pytest.approx(3 * CFO_PERIOD + 125)
    assert a["delta_modulo_hz"] == pytest.approx(125)
    assert a["delta_epoch_samples"] == 1
    assert b["positive"] == [True, False]
    assert c["positive"] == [False, True]


def test_joint_label_agreement_does_not_manufacture_independent_training():
    pair = dict(ids=["a", "b"], positive=[True, True], start=0,
                delta_signed_hz=0, delta_modulo_hz=0, delta_epoch_samples=0, removed_cfo_periods=0)
    agree = {"a": (100, "predictive"), "b": (100, "conditional")}
    differ = dict(agree, b=(200, "conditional"))
    assert label_types(pair, agree, agree) == "joint_same_family"
    assert label_types(pair, differ, differ) == "joint_different_families"
    assert label_types(pair, agree, differ) == "joint_assignments_disagree"
    assert label_types(pair, agree, {"a": agree["a"]}) == "unowned_in_one_or_both"
    target = dict(train=[pair], origin=0, seed_dual=[], seed_radio=2, comparison_clocks={})
    result = grade(target, 100, agree, agree)
    assert result["training_proxies"]["joint_same_family"]["pairs"] == 1
    assert result["independently_labelled_training_pairs"] == 0
