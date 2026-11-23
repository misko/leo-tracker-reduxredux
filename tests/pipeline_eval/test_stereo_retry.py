from reports.ALGO08.v3.stereo_retry import rate_bounds, stereo_rules, tally


def factor(epoch, cfo, score=0.25):
    return ((0, epoch, 0.0, cfo, score, 0.0),)


def test_wrap_and_margin_ties_in_bilateral_rule():
    short = (factor(13332, 100.0, 0.050), factor(0, 280.0))
    rules = stereo_rules(short)
    assert all(decision == (False, False) for decision in rules.values())
    assert stereo_rules((short[0], factor(0, 400.0)))["bilateral"] == (True, True)


def test_paired_margin_restarts_both_but_stereo_oracle_is_separate():
    first = (factor(4, 100.0), ())
    long = (factor(8, 100.0), ())
    result = tally([("simultaneous", first, long)])
    assert result["counts"]["frozen_independent"]["missed_lanes"] == 1
    assert result["counts"]["oracle_independent"]["retry_lanes"] == 1
    assert result["counts"]["oracle_stereo"]["retry_lanes"] == 2
    assert result["counts"]["paired_margin"]["missed_lanes"] == 0


def test_oracle_pricing_uses_actual_independent_cost_plus_only_added_partners():
    result = tally([("simultaneous", (factor(4, 100.0), ()), (factor(8, 100.0), ()))])
    clock = {"lanes": 2, "effects": {"restarts": 1, "necessary_restarts": 1, "missed_restarts": 1},
             "repeats_ns": [{"direct_native_ns": 60, "eight_native_ns": 20, "ideal_native_ns": 50,
                             "candidate_ns": 53, "direct_ns": 61}]}
    price, = rate_bounds(result["counts"], clock)
    assert price["oracle_stereo_bounds_ns"] == [50, 80]
    assert price["oracle_stereo_equal_mean_ns"] == 80
    assert price["oracle_partner_break_even_average_ns"] == 10
