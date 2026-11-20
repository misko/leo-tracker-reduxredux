import pytest

from tools.pipeline_eval.qualification.retry_cadence_trial import opportunities, schedules
from tools.pipeline_eval.variants.retry_cadence import RetryCadence


@pytest.mark.parametrize(("after", "hit"), [("hit", True), ("miss", False)])
def test_timer_is_per_physical_key_and_expires_at_its_boundary(after, hit):
    timer = RetryCadence(after, 20)
    key = (0, 100)
    assert timer.allows(key, 100)
    timer.observed(key, 100, hit)
    assert not timer.allows(key, 119)
    assert timer.allows((1, 100), 102)
    assert timer.allows((0, 105), 102)
    with pytest.raises(ValueError, match="unexecuted"):
        timer.observed(key, 119, not hit)
    assert timer.allows(key, 120)
    timer.observed(key, 120, not hit)
    assert timer.allows(key, 121)


def test_cadence_rejects_an_unknown_policy_or_negative_time_interval():
    with pytest.raises(ValueError, match="interval"):
        RetryCadence("guess")
    with pytest.raises(ValueError, match="interval"):
        RetryCadence("hit", -1)


def test_rejected_or_future_measurements_cannot_change_a_causal_choice():
    ns = 1_000_000_000
    first = (0, (0, 100), 0, False)
    last = (2, (0, 100), 2 * ns, True)
    for skipped_label in (False, True):
        events = [first, (1, (0, 100), ns, skipped_label), last]
        modes = dict(schedules(events, "same manifest"))
        assert modes["miss"] == {0, 2}
        assert (1 in modes["oracle"]) == skipped_label
        assert dict(schedules([first], "same manifest"))["hit"] == modes["hit"] & {0}


def test_hash_control_is_reproducible_and_matches_each_physical_key():
    keys = [(0, 100), (1, 100), (0, 200)]
    events = [(i, k, i * 100_000_000, i % 5 == 1) for i, k in enumerate(keys * 10)]
    modes = dict(schedules(events, "recording"))
    for policy in ("miss", "hit"):
        for key in keys:
            ids = {v for v, k, _, _ in events if k == key}
            assert len(modes[policy] & ids) == len(modes[policy + "_control"] & ids)
        assert (
            modes[policy + "_control"] == dict(schedules(events, "recording"))[policy + "_control"]
        )


def test_eligibility_preserves_antenna_identity_and_double_miss_measurements():
    def probe(lane, hit):
        return dict(
            receiver_id=lane, actual_rf_hz=100, candidates=[dict(passed_fractional_margin_gate=hit)]
        )

    primary = {0: (probe(0, True), probe(1, False)), 1: (probe(0, False), probe(1, False))}
    full = {0: (probe(0, True), probe(1, True)), 1: primary[1]}
    clocks = {0: dict(monotonic_ns=10), 1: dict(monotonic_ns=20)}
    assert opportunities(full, primary, clocks) == [(0, (1, 100), 10, True)]
    with pytest.raises(ValueError, match="without a retry"):
        opportunities(full | {1: full[0]}, primary, clocks)
    with pytest.raises(ValueError, match="antenna"):
        opportunities({0: full[0][::-1], 1: full[1]}, primary, clocks)
