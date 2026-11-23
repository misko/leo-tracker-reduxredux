from itertools import product
from types import SimpleNamespace

from reports.ALGO08.v3.active_doppler import ARMS, buy, separation, strict_support, summarize


def test_equal_budget_reserves_one_exploration_call():
    for trigger in product((False, True), repeat=8):
        paid, bought = 0, []
        for ordinal, fires in enumerate(trigger):
            reason = buy(ordinal, paid, fires)
            if reason is not None:
                bought.append((ordinal, reason))
                paid += reason != "explore"
        assert len(bought) == 3
        assert (4, "explore") in bought


def test_only_strictly_past_counter_blocks_can_nominate():
    rows = [SimpleNamespace(lane=SimpleNamespace(time=time)) for time in (0.99, 1., 5., 9., 9.01)]
    assert list(strict_support(rows, 9.)) == rows[1:3]
    a, b = dict(lower_hz=-8_000, upper_hz=-4_000), dict(lower_hz=-100, upper_hz=2_000)
    assert separation([b, a]) == 3900
    assert separation([a]) is None
    assert separation([a, dict(b, lower_hz=-4500)]) == -500


def test_hindsight_bound_charges_exploration_and_preserves_tail_denominator():
    owned = {arm: {(i, 0) for i in (0, 1, 6, 8)} for arm in ARMS}
    metadata = {arm: {slot: (100, 7) for slot in owner} for arm, owner in owned.items()}
    rows = [dict(lane=(0, "lower", 3, 10.), block=i//8, slot=(i, 0), offers=[], gap_hz=None,
                 bought={mode: "explore" if i == 4 else "trigger" for mode in ("active", "recent", "uniform")}
                        if i in (1, 4, 6) else {}) for i in range(9)]
    result = summarize(rows, owned["c0"], owned, metadata, .001)
    assert result["possible"]["c0"] == 4
    assert result["oracle"]["c0"] == dict(any_three=3, with_exploration=2)
    assert result["modes"]["active"]["owners"]["c0"]["owned"] == 2
