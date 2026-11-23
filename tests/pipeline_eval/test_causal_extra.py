from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from causal_extra import choose
from causal_extra_exterior import inspect_all


def rows(gap=10_000_000, slope=0.):
    return [dict(visit_index=i, receiver_id=r, channel=1, actual_rf_hz=10., edge="lower",
                 valid_start_counter=i*gap, candidates=[dict(candidate_rank=0, passed_fractional_margin_gate=True,
                                                            fractional_margin=.8, fractional_tracking_cfo_hz=i*slope)])
            for i in range(30) for r in (0, 1)]


def test_queries_are_causal_capped_and_cannot_recruit_queries_from_their_own_results():
    stream = rows()
    picks, s = choose(stream, [1e9]*len(stream))
    assert s["base_lanes"] == 20 and 0 < s["extra_lanes"] <= 10
    assert s["extra_native_cpu_s"] == s["extra_lanes"]
    for i, r in enumerate(stream):
        if r["visit_index"] % 3:
            r["candidates"] = [] if picks[i] else [None]
    after, t = choose(stream, [1e9]*len(stream))
    assert t["mask_sha256"] == s["mask_sha256"] and s["anchor_sha256"] == t["anchor_sha256"]
    assert sum(map(bool, after)) == 20


def test_impossible_slope_and_expired_donors_cannot_add_calls():
    for stream in (rows(slope=9001.), rows(gap=40_000_000)):
        assert choose(stream, [0]*len(stream))[1]["extra_lanes"] == 0


def test_interior_fit_still_obeys_the_actual_probe_result():
    endpoints = dict(c0=[0., 1.], fitted_c=[0., 1.])
    for veto in (False, True):
        result = inspect_all(endpoints, 25., lambda: dict(would_withhold=veto), terminal_only=True)
        assert result == dict(bound_arms=[], evaluated=True, would_withhold=veto)
