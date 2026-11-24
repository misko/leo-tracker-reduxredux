import csv
import json

import pytest

from full_successor_score import outcomes_summary, paired_rows, paired_timing, roster, score_arms, write_report


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
                 requested_raw_authority_sha256="a"*64, authority_sha256="b"*64,
                 attempt_result_sha256="e"*64, timing_scope="raw_launcher_through_exit_plus_common_publication_verification",
                 child_elapsed_s=.95, child_cpu_s=.86, validator_elapsed_s=.05, validator_cpu_s=.04,
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


def test_records_a_timed_failed_attempt_without_implying_observed_receiver_data():
    rows, assigned = matching_pair()
    rows[1].update(outcome="worker_failed", raw_authority_sha256=None, arms=arms(None),
                   timing_scope="raw_launch_to_exit")
    _, candidate = paired_rows(rows, assigned)[0]
    assert candidate["elapsed_s"] == 1 and candidate["raw_authority_sha256"] is None
    rows[1]["outcome"] = "solver_failed"
    with pytest.raises(ValueError, match="Observed input"):
        paired_rows(rows, assigned)


def test_sealed_rows_reach_figures_tables_and_machine_report(tmp_path):
    assigned = roster()
    template, _ = matching_pair()
    rows = []
    for i, (case, item) in enumerate(assigned.items()):
        for role in template:
            fix = role["algorithm"] == "installed" or i > 0
            rows.append({**role, "case": case, "case_id": item["case_id"],
                         "first": "installed" if i % 2 else "successor",
                         "outcome": "complete" if fix else "withheld",
                         "arms": arms([48., 7.] if fix else None)})
    pairs = paired_rows(rows, assigned)
    write_report(pairs, tmp_path, {case: r["release_100"] for case, r in assigned.items()}, "c"*64)
    report = json.loads((tmp_path / "summary.json").read_bytes())
    assert report["cohorts"]["All DS30 recordings"]["wall"]["pairs"] == 455
    assert report["paired_error_changes"]["fitted_c"]["lost"] == 1
    assert len(list(csv.DictReader((tmp_path / "recordings.csv").read_text().splitlines()))) == 910
    for figure in ("runtime.png", "position-error.png"):
        assert (tmp_path / figure).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert figure in (tmp_path / "README.md").read_text()
