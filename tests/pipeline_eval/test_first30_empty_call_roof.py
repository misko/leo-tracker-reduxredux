from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from first30_empty_call_roof import donor_clocks, empty_credit, stereo_counts, wall_gate


def pair(visit, flags, rf=11.5e9):
    return [dict(visit_index=visit, valid_start_counter=10*visit, edge="upper",
                 channel=1, actual_rf_hz=rf, receiver_id=rx,
                 candidates=[{"passed_fractional_margin_gate": True}] if flag else [])
            for rx, flag in enumerate(flags)]


def test_valid_stereo_stream_cadence_and_distinct_empty_sets():
    probes = pair(0, [False, False]) + pair(3, [False, True]) + pair(4, [True, False])
    probes += pair(5, [False, False], rf=11.75e9)
    probes += [r for i in range(6, 12) for r in pair(i, [True, True])]
    counts, valid = stereo_counts(probes)
    assert valid == [0, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert counts["full"]["visits"] == 3
    assert counts["full"]["both_empty"] == 2
    assert counts["short_primary"]["visits"] == 7
    assert counts["short_primary"]["one_empty"] == 2
    assert counts["short_primary"]["empty_lanes"] == 2
    assert counts["short_primary"]["both_empty"] == 0
    with pytest.raises(ValueError):
        stereo_counts(probes[:-1])
    probes[1]["actual_rf_hz"] = 11.75e9
    with pytest.raises(ValueError, match="chronological stereo"):
        stereo_counts(probes)


def test_empty_credit_is_nested_inside_aperture_and_respects_stereo():
    clocks = dict(lanes=10, empty_lanes=6, both_empty=2, elapsed_ns=10e9)
    assert empty_credit(clocks, "elapsed_ns", 1.) == 6.
    assert empty_credit(clocks, "elapsed_ns", 1., pair_only=True) == 4.
    assert empty_credit(clocks, "elapsed_ns", 2., pair_only=True) == 5.
    assert empty_credit(clocks, "elapsed_ns", float("inf")) == 10.
    clocks["empty_lanes"] = 0
    assert empty_credit(clocks, "elapsed_ns", 1.) == 0.


def test_paired_median_and_summed_wall_are_independent_gates():
    cases = [dict(paid_installed_s=10, paid_candidate_s=5.),
             dict(paid_installed_s=5, paid_candidate_s=2.),
             dict(paid_installed_s=100, paid_candidate_s=90., installed_outcome="solver_failed")]
    outcome = wall_gate(cases, [0., 0., 10.])
    assert outcome["candidate_s"] == 87.
    assert outcome["individual_half_time"] == 2
    assert outcome["qualifies_median"] and not outcome["qualifies_sum"]


def test_donor_seals_enroll_same_sparse_binary_and_keep_empty_prices_separate():
    cases, repeated = donor_clocks()
    assert len(cases) == 4 and set(repeated) == {"DS30-0008", "DS30-0016"}
    pair = cases["DS30-0016"]["short_primary"]
    assert pair["empty"]["samples"] == 808 and pair["positive"]["samples"] == 432
    assert pair["empty"]["wall_ns"]["mean"] < pair["positive"]["wall_ns"]["mean"]
    assert len(repeated["DS30-0008"]) == 4
