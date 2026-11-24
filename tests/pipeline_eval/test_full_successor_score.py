import pytest

from full_successor_score import outcomes_summary, paired_rows, paired_timing, roster, score_arms


def arms(point):
    return {name: {"latlon": point, "rf_rms_hz": 100 if point is not None else None}
            for name in ("c0", "fitted_c")}


def test_all_ds30_and_historical_subset_are_identified_independently():
    assigned = roster()
    assert len(assigned) == 455
    assert sum(r["release_100"] for r in assigned.values()) == 100
    assert sum(r["recording_state"] == "incomplete" for r in assigned.values()) == 44
    assert all(r["reference"] is not None for r in assigned.values())


def test_timing_gates_use_identical_recordings_and_inverse_median_ratios():
    pairs = [({"elapsed_s": a}, {"elapsed_s": b}) for a, b in [(1, .25), (9, 6.75), (20, None)]]
    assert paired_timing(pairs, "elapsed_s") == {"pairs": 2, "summed_speedup": 10/7, "median_paired_speedup": 2}
    with pytest.raises(ValueError):
        paired_timing([({"cpu_s": float("nan")}, {"cpu_s": 1.0})], "cpu_s")


def test_failed_fix_remains_in_population_and_rf_summaries_are_separate():
    rows = [{"case": "a", **score_arms(arms([48., 7.]), [48., 7.])},
            {"case": "b", **score_arms(arms(None), [48., 7.])}]
    result = outcomes_summary(rows, {"a", "b"})
    assert result["c0"]["fixes"] == result["c0"]["within_1km"] == 1
    assert result["fitted_c"]["error_km"]["p50"] == 0
    assert result["fitted_c"]["rf_rms_hz"]["p50"] == 100
    with pytest.raises(ValueError, match="every assigned"):
        outcomes_summary(rows[:1], {"a", "b"})


def matching_pair():
    assigned = {"DS30-test": dict(case_id="original", reference=[48., 7.], release_100=True,
                                  recording_state="complete")}
    rows = [dict(case="DS30-test", case_id="original", algorithm=k, build_sha256=str(i)*64,
                 raw_authority_sha256="a"*64, first="installed", elapsed_s=1., cpu_s=.9,
                 outcome="complete", arms=arms([48., 7.])) for i, k in enumerate(("installed", "successor"), 1)]
    return rows, assigned


def test_requires_complete_matched_pair_and_keeps_two_different_outcomes():
    rows, assigned = matching_pair()
    with pytest.raises(ValueError, match="measured arms"):
        paired_rows(rows[1:], assigned)
    rows[1].update(outcome="withheld", arms=arms(None))
    a, b = paired_rows(rows, assigned)[0]
    assert (a["c0_error_km"], b["c0_error_km"], b["fitted_c_fix"]) == (0., None, False)
    with pytest.raises(ValueError, match="Duplicate"):
        paired_rows(rows + rows[:1], assigned)


@pytest.mark.parametrize(("field", "value"), [("first", "successor"), ("case_id", "other"),
                         ("raw_authority_sha256", "b"*64), ("cpu_s", None), ("outcome", "pending"),
                         ("outcome", "worker_failed"), ("build_sha256", "unset")])
def test_unpaired_and_unmeasured_rows_cannot_produce_full_distribution(field, value):
    rows, assigned = matching_pair()
    rows[1][field] = value
    with pytest.raises(ValueError):
        paired_rows(rows, assigned)
