import json

import pytest

from reports.ALGO08.v3 import sparse8_native_profile as profile


def result():
    return json.loads((profile.HERE / "measurements/sparse8-native-profile.json").read_text())


def test_trace_edits_require_one_original_boundary():
    assert profile.one("start work end", "work", "work; tick") == "start work; tick end"
    with pytest.raises(ValueError, match="boundary changed"):
        profile.one("start end", "work", "work; tick")
    with pytest.raises(ValueError, match="boundary changed"):
        profile.one("work work", "work", "work; tick")


def test_sealed_clocks_are_exclusive_and_bounded_by_every_exact_call():
    sealed = result()
    for name, n, positive in (("DS30-0163", 36, 10), ("DS30-0419", 6, 4)):
        rows = sealed["cases"][name]["rows"]
        assert len(rows) == n
        assert sum(bool(row["factor_hex"]) for row in rows) == positive
        for row in rows:
            for trial in row["rounds"]:
                assert trial["clock_on"][0] >= sum(trial["clock_on"][1:]) > 0
                assert sum(trial["clock_off"][1:]) == 0
        assert profile.summarize(rows) == sealed["cases"][name]["summary"]
    assert sealed["build"]["exact_sha256"] == profile.ORIGINAL
    assert sealed["build"]["train_sha256"] == profile.TRAIN_ROWS


def test_field_reweight_preserves_distinct_cpu_and_elapsed_denominators():
    sealed = result()
    projection = profile.priced_stages(sealed)
    assert projection == sealed["pricing"]
    assert projection["verifier_reached"] == {"empty": 11, "positive": 14}
    assert projection["field_short_combined_cpu_share"] == pytest.approx(0.678211047)
    assert projection["field_short_combined_elapsed_share"] == pytest.approx(0.688123570)
    joint = projection["ceilings"]["lag_carrier_and_refinement"]
    assert joint["donor_replacement_ns_before_first30_complete_gate"] == pytest.approx(12912.314)


def test_separate_donor_allowances_charge_replacement_on_empty_and_positive_lanes():
    prices = profile.individual_donor_budgets(result())
    for case, budget in (("DS30-0163", 12682.506), ("DS30-0419", 5562.286)):
        scopes = prices[case]
        assert scopes["lag_timing+carrier_grid"]["summed_gate_replacement_ns_per_lane"] is None
        three = scopes["lag_timing+carrier_grid+full_rate_refine"]
        assert three["summed_gate_replacement_ns_per_lane"] == pytest.approx(budget)
        assert three["free_summed_speedup"] > 2
        assert three["median_speedup_at_summed_cap"] > 2
