from reports.ALGO08.v3 import held_short_cfo_shrink_south as trial


def opportunity(counter, radio, channel=2, *, positive=True):
    return dict(counter=counter, factor={} if positive else None,
                row=dict(receiver_id=radio, edge="falling", channel=channel, actual_rf_hz=11_900_000_000))


def test_spacing_bound_keeps_lanes_distinct_and_respects_the_frozen_product():
    s = trial.odd.ADC
    rows = [
        opportunity(0, 0), opportunity(s, 0), opportunity(3*s, 0),
        opportunity(3*s//2, 1), opportunity(5*s//2, 1),
        opportunity(7*s//4, 0, positive=False),
    ]
    def target(counter, radio, channel=2):
        row = opportunity(counter, radio, channel)
        return dict(counter=counter, lane=tuple(row["row"][key] for key in trial.odd.LANE))

    held = dict(exact=target(s//2, 0), over=target(2*s, 0), other_radio=target(2*s, 1),
                absent_channel=target(s//2, 0, channel=3), no_right=target(2*s, 2))
    assert trial.spacing_ceiling(held, dict(enumerate(rows))) == {
        "exact": "passes", "over": "spacing", "other_radio": "passes",
        "absent_channel": "not_bracketed", "no_right": "not_bracketed",
    }


def test_no_shrink_has_zero_changes_and_unavailable_error_not_zero_error():
    result = trial.shrink.evaluate([], 0)
    assert result["eligible"] == result["scored"] == result["installed_empty"] == 0
    assert result["original"] is result["shrunk"] is None
    assert set(result["windows"]) == {"250Hz_2samples", "2250Hz_6samples"}
    assert all(row["joint_before"] == row["joint_after"] == row["joint_restored"] == row["joint_spoiled"] == 0
               for row in result["windows"].values())
