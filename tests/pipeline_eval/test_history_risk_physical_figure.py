import pytest

from reports.ALGO08.v3.history_risk_physical_figure import cairo_times, plot_values


def test_physical_plot_counts_withhold_in_time_and_only_fixes_in_error():
    def outcome(elapsed, error):
        return {"clock": {"elapsed_s": elapsed}, "arms": {
            arm: {"horizontal_error_km": error} for arm in ("c0", "fitted_c")}}

    cohort = {"cases": {"DS30-0107": {"stock": outcome(2, None), "candidate": outcome(1, None)},
                        "DS30-0016": {"stock": outcome(10, 1.5), "candidate": outcome(8, 0.5)}}}
    times, errors = plot_values(cohort)
    assert times["candidate"] == [1, 8]
    assert errors["stock"] == [1500, 1500]
    cohort["cases"]["DS30-0107"]["candidate"]["arms"]["c0"]["horizontal_error_km"] = 0
    with pytest.raises(ValueError, match="withheld"):
        plot_values(cohort)


def test_optional_renderer_times_require_the_same_measured_baseline():
    decisions = {"DS30-0107": "withheld", "DS30-0016": "complete"}
    runs = {case: {"stock": {"elapsed_s": 2.0}, "candidate": {"elapsed_s": 1.0}} for case in decisions}
    cairo = dict(qualified=True, decisions=decisions, verification_0016={"cal_arms": True}, clocks=runs)
    cohort = {"cases": {case: {"stock": {"clock": {"elapsed_s": 2.0}}} for case in decisions}}
    assert cairo_times(cohort, cairo) == [1.0, 1.0]
    runs["DS30-0016"]["stock"]["elapsed_s"] = 3.0
    with pytest.raises(ValueError, match="comparator"):
        cairo_times(cohort, cairo)
