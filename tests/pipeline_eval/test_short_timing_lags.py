from reports.ALGO08.v3.short_timing_lags import close_factor, oracle_species, strongest


def test_published_pick_and_numerical_tolerance_are_separate():
    a, b = (0, 13332, 0.7, -3000, .3, .1), (1, 5, .5, -6000, .4, .1)
    assert strongest([a, b]) == b
    equivalent = (0, 0, -.2, -2900, .4, .1)
    assert close_factor(a, equivalent)
    assert not close_factor(a, (1, *equivalent[1:]))


def test_timing_census_splits_published_and_empty_lane_rows():
    sample = 240000
    factor = (0, 40, 0., -1000., .5, .1)
    options = dict(kind="short", scheduled="short", key="case:0", sample=sample, edge="upper",
                   generation="capture", rf=120., scopes=[[[10, 20], [10, 20]]])
    rows = [dict(options, antenna=0, factors=[factor]), dict(options, antenna=1, factors=[])]
    fields = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
              "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score")
    publication = dict(actual_rf_hz=120., edge="upper", channel=1)
    probes = {(sample, 0): dict(publication, candidates=[dict(zip(fields, factor, strict=True))]),
              (sample, 1): dict(publication, candidates=[])}
    found = oracle_species({"dense": {"rows": rows}}, probes)
    assert found["published/4/missed"] == 1
    assert found["other_on_positive/total"] == 1
    assert found["empty/total"] == 2
    assert found["empty/4/missed"] == 1
