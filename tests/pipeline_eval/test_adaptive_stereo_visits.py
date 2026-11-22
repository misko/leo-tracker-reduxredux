from tools.pipeline_eval.variants.experimental.adaptive_stereo_visits import (
    RATE,
    AdaptiveStereo,
    optimistic_skip_limit,
)


def metadata(counter, *, channel=3, rf=12_100_000_000):
    return tuple(dict(receiver_id=lane, channel=channel, actual_rf_hz=rf,
                      valid_start_counter=counter) for lane in (0, 1))


def factor(hz=1_000., *, margin=.12, rank=0):
    return dict(candidate_rank=rank, fractional_margin=margin, fractional_tracking_cfo_hz=hz)


def test_stereo_skip_uses_only_measured_donors_and_measures_immediate_follow_up():
    policy = AdaptiveStereo()
    decisions, calls = [], []
    for i in range(11):
        pair = metadata(i * RATE // 2)

        def measure(i=i):
            calls.append(i)
            return (factor(),), (factor(hz=-1000.),)

        skipped, observed, chosen, _ = policy.visit(pair, measure)
        if skipped:
            assert observed == ((), ()) and not any(row["candidates"] for row in chosen)
            for lane in (0, 1):
                key = lane, pair[lane]["channel"], pair[lane]["actual_rf_hz"]
                assert policy.continuation.by_lane[key][-1] == (i * RATE // 2, ())
        if i == 5:
            assert all(row["candidates"] for row in chosen)
        decisions.append(skipped)

    assert decisions == [False] * 4 + [True, False, True, False, True, False, True]
    assert calls == [0, 1, 2, 3, 5, 7, 9]


def test_weak_onset_on_either_antenna_restarts_full_rate_and_rf_state_is_separate():
    policy = AdaptiveStereo()

    def full():
        return (factor(),), (factor(),)

    def new_secondary():
        return (factor(), factor(hz=-6000., margin=.04, rank=1)), (factor(),)

    skips = []
    for i in range(10):
        pair = metadata(i * RATE // 2)
        measure = new_secondary if i == 5 else full
        skips.append(policy.visit(pair, measure)[0])
    assert skips == [False] * 4 + [True] + [False] * 5
    assert not policy.visit(metadata(6 * RATE, rf=12_450_000_000), full)[0]


def test_timestamp_ceiling_respects_forecast_age_span_and_nonconsecutive_paths():
    medium = [metadata(i * RATE // 2) for i in range(11)]
    sparse = [metadata(2 * i * RATE) for i in range(11)]
    too_close = [metadata(i * RATE // 200) for i in range(30)]
    assert optimistic_skip_limit(medium) == dict(
        timestamp_eligible_visits=7, maximum_nonconsecutive_skips=4,
    )
    for panel in (sparse, too_close):
        assert optimistic_skip_limit(panel) == dict(
            timestamp_eligible_visits=0, maximum_nonconsecutive_skips=0,
        )
