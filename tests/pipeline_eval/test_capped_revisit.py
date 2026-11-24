"""Exercise the streaming revisit budget without installed labels or waveforms."""

from reports.ALGO08.v3.capped_revisit import (
    HERTZ, SAMPLE_RATE, StreamBudget, compare, first_with_same_short_status, forecast, owner_bounds, target_sets,
)


def detection(hz, epoch=0):
    return {HERTZ: hz, "integer_epoch_sample": epoch, "fractional_epoch_offset_samples": 0.}


def observation(i, hz=None, *, short=True):
    return dict(id=str(i), counter=i*SAMPLE_RATE//4, short=short,
                factor=detection(hz) if hz is not None else None)


def test_same_stream_forecast_requires_recent_consistent_signed_history():
    history = [(0, -300.), (SAMPLE_RATE, -100.), (2*SAMPLE_RATE, 100.)]
    assert forecast(history, 3*SAMPLE_RATE) == (300., 0.)
    assert forecast(history, 5*SAMPLE_RATE) is None
    assert forecast(history[1:], 3*SAMPLE_RATE) is None
    assert forecast([(0, -300.), (SAMPLE_RATE, 600.), (2*SAMPLE_RATE, 100.)], 3*SAMPLE_RATE) is None


def test_prefix_budget_and_deadline_ignore_anchors_and_pending_tail():
    stream = StreamBudget()
    credits = []
    for i in range(1, 37):
        opened, _ = stream.consider(observation(i, short=i != 20), False)
        if opened is not None:
            credits.append(opened)
        assert sum(bool(r["chosen"]) for r in credits) <= stream.short_count//16
    first, last = credits
    assert first["lanes"][0] == "16" and first["chosen"] == "32" and len(first["lanes"]) == 16
    assert last["lanes"][0] == "33" and last["chosen"] is None
    result, policy, baseline = compare(credits, {"combined": {"16", "33"}})
    assert policy == {"32"} and baseline == {"16"}
    assert result["n"] == 1 and result["independent_periodic_n"] == 2
    assert result["uniform_expected_hits"] == {"combined": 1./16}


def test_seeded_missing_and_disagreeing_use_only_prior_and_current_values():
    for hz, reason in ((None, "expected_missing"), (5_000., "forecast_departure")):
        stream = StreamBudget()
        for i in range(1, 16):
            assert stream.consider(observation(i, i*20.), False) == (None, None)
        credit, trigger = stream.consider(observation(16, hz), False)
        assert trigger == reason
        assert credit == dict(lanes=["16"], chosen="16", reason=reason)
        stream.consider(observation(17, -50_000.), True)
        assert credit["chosen"] == "16"


def test_installed_scoring_distinguishes_disjoint_joint_oracle_classes():
    original = {"empty": observation(1, 900.), "changed": observation(2, 1_000.),
                "close": observation(3, 1_000.), "anchor": observation(4, 1_000., short=False),
                "only_sparse": observation(5)}
    mixed = {"empty": observation(1), "changed": observation(2, 1_251.), "close": observation(3, 1_250.),
             "anchor": observation(4, 99_000., short=False), "only_sparse": observation(5, 50.)}
    assert target_sets(original, mixed) == dict(missing={"empty"}, disagreeing={"changed"}, combined={"empty", "changed"})
    assert owner_bounds(20, 100, 90) == [10, 20]
    assert owner_bounds(80, 100, 30) == [10, 30]


def test_posthoc_control_matches_each_spent_credits_observation_type():
    lanes = {str(i): observation(i, None if i in (2, 4) else 11.) for i in range(1, 7)}
    credits = [dict(lanes=["1", "2", "3", "4"], chosen="4"), dict(lanes=["5", "6"], chosen=None)]
    assert first_with_same_short_status(credits, lanes) == {"2"}
