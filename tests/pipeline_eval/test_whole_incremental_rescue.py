import pytest

from tools.pipeline_eval.qualification.whole_incremental_results import compare_lane, compare_visits


def candidate(epoch, cfo, gate=True, rank=0):
    return dict(
        candidate_rank=rank,
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0.1,
        fractional_tracking_cfo_hz=cfo,
        fractional_margin=0.2 if gate else 0.01,
        passed_fractional_margin_gate=gate,
    )


def packet(*candidates, rx=0):
    return dict(receiver_id=rx, channel=1, candidates=list(candidates))


def test_counter_separates_stock_lost_changed_and_negative_only_gains():
    a = packet(candidate(4, 100))
    b = packet(candidate(20, 130))
    empty = packet(candidate(1, 500, gate=False))
    assert compare_lane(a, b, a)["stock_positive_packet_changed"] is False
    assert compare_lane(a, b, b)["stock_winner_changed"] is True
    assert compare_lane(a, b, empty)["stock_lost"] is True
    gained = compare_lane(empty, b, packet(candidate(21, 135, rank=2)))
    assert gained["rescue_new_and_fifth_physical_match"] is True
    assert gained["rescue_new_and_fifth_winner_exact"] is False


def test_visit_audit_checks_immutable_acquisition_even_when_no_candidates_exist():
    a = dict(visit=0, sample_start=2, status="processed", probes=[packet(rx=0), packet(rx=1)])
    b = dict(visit=1, sample_start=4, status="invalid_capture", probes=[])
    assert compare_visits([a, b], [a, b], [a, b])["invalid_visits"] == 1
    with pytest.raises(ValueError, match="delivery clock"):
        compare_visits([a], [a], [dict(a, sample_start=3)])
    with pytest.raises(ValueError, match="probe header"):
        compare_visits([a], [a], [dict(a, probes=[packet(), packet(rx=2)])])
