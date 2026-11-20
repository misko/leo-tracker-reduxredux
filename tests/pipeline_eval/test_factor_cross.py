from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.factor_cross import (
    ALIAS_HZ,
    CFO,
    assess,
    interchange,
    matches,
)


def row(rank, epoch, cfo, margin):
    return {
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.25,
        "fractional_tracking_cfo_hz": cfo,
        "fractional_exact_score": margin + 0.5,
        "fractional_control_score": 0.5,
        "fractional_margin": margin,
        "passed_fractional_margin_gate": margin >= 0.025,
        "candidate_rank": rank,
    }


def native(candidates):
    return {
        "source": {
            "sample_rate_hz": 10_000_000,
            "probes": [
                {
                    "visit_index": 100,
                    "receiver_id": 1,
                    "candidates": candidates,
                }
            ],
        }
    }


def test_matching_uses_fractional_epoch_and_folded_frequency_without_scores():
    a = [row(3, 17, 100, 0.05)]
    b = [row(0, 13350, 100 + ALIAS_HZ, 0.015)]
    pairs, degrees = matches(a, b, 13333)
    assert pairs == [(0, 0)]
    assert degrees == ([1], [1])
    b.append(row(1, 17, 101, 0.20))
    assert matches(a, b, 13333)[0] == []


def test_cross_holds_unmatched_support_and_local_cfo_alias_branch():
    a, b = (
        native([row(0, 17, 100, 0.05), row(1, 22, 40, 0.04)]),
        native([row(2, 13350, 134 + ALIAS_HZ, 0.015)]),
    )
    before = deepcopy(a)
    rows, counts = assess(a, b)
    assert counts["matched_pairs"] == counts["gate_10"] == counts["cross_alias_pairs"] == 1
    assert counts["capture_era_no_edge"] == 1
    by_score, stat = interchange(a, b, rows, "score", reverse=False)
    assert stat["changed_gate_flags"] == stat["winner_switched"] == 1
    assert "changed_cfo_measurements" not in stat
    by_cfo, stat = interchange(a, b, rows, "cfo", reverse=False)
    assert stat["winner_switched"] == 0 and stat["changed_winning_measurement"] == 1
    both, _ = interchange(a, b, rows, "both", reverse=False)
    values = both["source"]["probes"][0]["candidates"]
    assert values[0][CFO] == pytest.approx(134)
    assert values[0]["candidate_rank"] == 0 and values[0]["integer_epoch_sample"] == 17
    assert values[1] == before["source"]["probes"][0]["candidates"][1]
    assert by_score["source"]["probes"][0]["candidates"][0][CFO] == 100
    assert by_cfo["source"]["probes"][0]["candidates"][0]["passed_fractional_margin_gate"]
    assert a == before


def test_cross_requires_exact_receiver_and_probe_support():
    a, b = native([]), native([])
    b["source"]["probes"][0]["receiver_id"] = 2
    with pytest.raises(ValueError, match="identical probe support"):
        assess(a, b)
