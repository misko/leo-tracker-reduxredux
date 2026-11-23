from pathlib import Path

import pytest

from reports.ALGO08.v3.mixed_aperture_receiver import FULL_RULE, StereoSchedule


def test_full_coverage_keeps_stereo_opportunities_and_tail():
    schedule = StereoSchedule(full_coverage=True)
    target = dict(edge="lower", channel=6, lnb_lo_hz=9_750_000_000)
    primary = [schedule.visit("lower", target, dict(actual_if_center_hz=1.6e9, sample_start=index))
               for index in range(10)]
    assert primary == list(enumerate((*FULL_RULE, *FULL_RULE[:2])))
    other_rf = dict(actual_if_center_hz=1.7e9, sample_start=4)
    assert schedule.visit("lower", target, other_rf) == (0, "full")


@pytest.fixture
def scoring(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    from reports.ALGO08.v3 import full_short_score

    return full_short_score


def test_one_to_one_match_uses_wrapped_timing_and_signed_cfo(scoring):
    def peak(rank, epoch, hz):
        return dict(candidate_rank=rank, integer_epoch_sample=epoch, fractional_epoch_offset_samples=.25,
                    fractional_tracking_cfo_hz=hz, passed_fractional_margin_gate=True)

    def doc(candidates):
        probes = [dict(visit_index=2, receiver_id=rx, valid_start_counter=200000, channel=1, actual_rf_hz=11.12e9,
                       edge="lower", candidates=[factor]) for rx, factor in enumerate(candidates)]
        return dict(source=dict(session_id="fast-1", probes=probes))

    before = doc([peak(1, 13332, -2000), peak(0, 5, -1000)])
    after = doc([peak(0, 0, -1800), peak(0, 5, 1000)])
    lanes = scoring.compare_lanes(before, after)
    measured = scoring.counts(list(lanes.values()))
    assert measured["stock_selected"] == measured["candidate_selected"] == measured["both_selected"] == 2
    assert measured["matched"] == 1 and measured["matched_same_rank"] == 0
    assert measured["errors"]["tolerance_matched"]["wrapped_timing_samples"]["median_signed"] == 1.
    assert measured["errors"]["tolerance_matched"]["signed_cfo_change_hz"]["median_signed"] == 200.


def test_omitted_startup_added_only_to_projected_elapsed(scoring):
    rows = [dict(stages=(5., 3., 2.), compressed_MB=2.)]
    assert scoring.gates(rows, 2., .5) == (.45, .45)
    assert scoring.gates(rows, 2., .5, startup_s=1.) == (.55, .55)
    assert scoring.minimum_rate(rows, .5, 0, startup_s=1.) == pytest.approx(4.)
