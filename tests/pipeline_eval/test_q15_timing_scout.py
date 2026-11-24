import pytest

from reports.ALGO08.v3.q15_timing_scout import comparison, overlay, summarize


def test_overlay_retains_the_exact_scout_and_only_swaps_the_detect_port():
    source = ("static void find_times(TimingFirst *w, int *out) {}\n"
              "static double bin_hz(const TimingFirst *w, int i) {return i;}\n"
              "    find_times(w, epochs);\n    Seed seeds[2 * clocks];\n")
    candidate = overlay(source, "research implementation")
    assert "static void find_times(TimingFirst *w, int *out) {}" in candidate
    assert "research implementation\n\nstatic double bin_hz" in candidate
    assert "find_times_trial(w, epochs);" in candidate
    with pytest.raises(ValueError, match="checked receiver source differs"):
        overlay(source + source, "research implementation")


def test_comparison_distinguishes_order_fallback_and_signed_factor_changes():
    a = dict(epochs=[1, 2, 3], tentative=[1, 2, 3], ns=5, fallback=0)
    b = dict(a, epochs=[2, 1, 3], tentative=[2, 1, 3])
    stock = dict(scouts=[a, a], factors=[(0, 128, 3.75), (1, 768, -41.25)], native_bytes="aa")
    trial = dict(scouts=[b, dict(a, tentative=[1, 2, 4], fallback=2)],
                 factors=[(0, 128, 3.75), (1, 768, 41.25)], native_bytes="ab")
    counts = comparison(stock, trial)
    assert counts["primary_ordered_peak_changes"] == 1
    assert counts["primary_unordered_peak_changes"] == 0
    assert counts["residual_exact_fallback"] == counts["residual_ambiguous_tentative_peak_changes"] == 1
    assert counts["secondary_factor_changes"] == counts["any_factor_bytes_changed"] == 1
    assert counts["primary_factor_changes"] == 0


def test_rollup_charges_primary_and_residual_to_the_same_lane():
    a = dict(epochs=[1, 2, 3], tentative=[1, 2, 3], ns=5, fallback=0)
    b = dict(a, ns=10)
    case = dict(scouts=[a, b], factors=[], cpu_ns=20, native_bytes="")
    arms = dict(exact=case, speculative=dict(case, cpu_ns=30), guarded=dict(case, cpu_ns=40))
    total = summarize([dict(kind="full", tests=[arms] * 4)])
    assert total["all"]["lanes"] == 1
    assert total["full"]["arms"]["exact"]["scout_cpu_ns"] == 15
    assert total["full"]["arms"]["guarded"]["lane_cpu_ns"] == 40
