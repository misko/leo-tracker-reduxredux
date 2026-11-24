import pytest

from reports.ALGO08.v3.empty_lane_arrival import PERIOD, hits, phases


def lane(counter, phase):
    offset = (phase-(3*counter % 40_000)/3) % PERIOD
    return dict(counter=counter, factor=dict(integer_epoch_sample=int(offset),
                                            fractional_epoch_offset_samples=offset-int(offset)))


def test_physical_frame_wrap_large_counters_and_unequal_bracket():
    start = 2**54+1
    result = phases(lane(start, PERIOD-1), start+300, lane(start+900, 2))
    assert min(result["interpolated"], PERIOD-result["interpolated"]) == pytest.approx(0., abs=1e-9)
    assert result["left_only"] == pytest.approx(PERIOD-1)
    assert result["quarter_period_control"] == pytest.approx(PERIOD/4)
    with pytest.raises(ValueError, match="bracket"):
        phases(lane(1, 0.), 4, lane(4, 1.))


def test_two_bad_brackets_cannot_collectively_pass_a_joint_gate():
    def bracket(hz, phase):
        return dict(centers_hz=hz, phase=dict(interpolated=phase, left_only=phase, quarter_period_control=phase))
    proposals = [bracket([100.], 74.), bracket([400., 990.], PERIOD-1.)]
    assert hits(proposals, 100., .1, 250., 2.) == dict(carrier_only=True, interpolated=False,
                                                       left_only=False, quarter_period_control=False)
    assert hits(proposals, 401., .1, 250., 2.)["interpolated"]
    assert not any(hits([], 100., .1, 250., 2.).values())
