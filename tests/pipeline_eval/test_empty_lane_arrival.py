import pytest

from reports.ALGO08.v3.empty_lane_arrival import HERTZ, PERIOD, hits, phases, prepare, score_group


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


def test_only_frozen_unique_predictions_use_authenticated_donor_epochs():
    def source(clock, hz=None):
        r = lane(clock, 102.)
        r.update(short=True, radio=0, row=dict(edge="upper", actual_rf_hz=1000, channel=1, visit_index=clock))
        if hz is None:
            r["factor"] = None
        else:
            r["factor"][HERTZ] = hz
        return r

    candidate = dict(left=source(30,50.), target=source(40), right=source(50,70.), ambiguous=source(45))
    def donor(key):
        r = candidate[key]
        return dict(observation_id=key, counter=r["counter"], signed_cfo_hz=r["factor"][HERTZ],
                    integer_epoch_sample=r["factor"]["integer_epoch_sample"],
                    fractional_epoch_offset_samples=r["factor"]["fractional_epoch_offset_samples"])
    bracket = dict(left=donor("left"), right=donor("right"), right_weight=.5, signed_centers_hz=[60.])
    plan = dict(empty_short_count=2, opportunities=dict(
        target=dict(observation_id="target", counter=40, radio=0, status="unique_signed_bracket", brackets=[bracket],
                    **candidate["target"]["row"]),
        ambiguous=dict(status="multiple_graph_pieces")))
    empty, pred, _ = prepare(plan, candidate)
    installed = dict(target=source(40,60.), ambiguous=source(45,90.))
    scored = score_group(empty, pred, installed)
    assert scored["installed_positive_denominator"] == 2
    assert scored["windows"]["primary"]["interpolated"] == 1
    assert scored["windows"]["primary"]["quarter_period_control"] == 0
    assert score_group(empty, pred, installed, {"ambiguous"})["installed_positive_queries"] == 0
    plan["opportunities"]["target"]["channel"] = 2
    with pytest.raises(ValueError, match="target window"):
        prepare(plan, candidate)
    plan["opportunities"]["target"]["channel"] = 1
    bracket["left"]["integer_epoch_sample"] += 1
    with pytest.raises(ValueError, match="phase donor"):
        prepare(plan, candidate)
