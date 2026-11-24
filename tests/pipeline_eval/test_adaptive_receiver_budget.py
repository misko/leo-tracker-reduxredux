import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from adaptive_receiver_budget import exact_case_report, matched_budget, receiver_budget, routed_case_report


def test_publication_includes_the_tail_and_charges_unsplit_runs():
    # A 10 s fix has 4 s downstream. At 2x downstream, 60 MB may use
    # 3 s for the median gate. Two such fixes and a 2 s unsplit failure
    # leave 5 s for 120 MB on the summed gate.
    fix = dict(stages=[6, 1, 3], compressed_MB=60)
    failure = dict(stages=[0, 0, 2], compressed_MB=0)
    assert receiver_budget([fix, fix, failure], 2) == pytest.approx(
        dict(median_MB_s=20, summed_MB_s=24, both_MB_s=24))


def test_infeasible_post_detector_clock_has_no_finite_acquisition_rate():
    fix = dict(stages=[4, 4, 2], compressed_MB=40)
    assert receiver_budget([fix], 1) == dict(median_MB_s=None, summed_MB_s=None, both_MB_s=None)


def test_matched_saving_transfers_only_the_difference_of_saved_clocks():
    raw = dict(stages=[20, 9, 1], compressed_MB=120)
    # Both saved processes carry 2 s of launch work outside the raw downstream stage.
    clocks = dict(named=dict(elapsed_s=12), candidate=dict(elapsed_s=9))
    result = matched_budget(raw, clocks)
    assert result["modeled_downstream_s"] == 7
    assert result["acquisition_budget_s"] == 8
    assert result["required_MB_s"] == 15


def test_saved_slowdown_is_charged_and_can_make_half_time_unreachable():
    raw = dict(stages=[5, 4, 1], compressed_MB=120)
    clocks = dict(named=dict(elapsed_s=7), candidate=dict(elapsed_s=8))
    assert matched_budget(raw, clocks)["required_MB_s"] is None


def test_fourth_signed_case_exceeds_half_time_even_with_free_acquisition():
    report = exact_case_report(4)
    assert set(report["cases"]) == {"DS30-0160", "DS30-0316", "DS30-0374", "DS30-0402"}
    expensive = report["cases"]["DS30-0402"]
    assert expensive["acquisition_budget_s"] == pytest.approx(-2.82947, abs=0.00001)
    assert expensive["required_MB_s"] is None
    assert report["median_ratio_at_verify_only_rate"] > 0.5
    assert report["summed_ratio_at_verify_only_rate"] > 0.5


def test_routed_panel_charges_admission_and_prices_each_timing_gate():
    report = routed_case_report()
    assert report["cases"]["DS30-0160"]["acquisition_budget_s"] == pytest.approx(7.4301, abs=0.0001)
    assert report["median_gate_MB_s"] == pytest.approx(442.25, abs=0.01)
    assert report["summed_gate_MB_s"] == pytest.approx(405.69, abs=0.01)
