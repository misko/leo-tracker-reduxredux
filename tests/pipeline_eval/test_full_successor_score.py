import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image

from full_successor_score import (PINS, calibration_segment_error_km, compare_centers, outcomes_summary, paired_rows,
                                  paired_timing, roster, score_arms, shared_position_moments, squared_error_influence,
                                  time_accounting, write_report)


def arms(point):
    return {name: {"latlon": point, "rf_rms_hz": 100 if point is not None else None}
            for name in ("c0", "fitted_c")}


def test_all_ds30_and_historical_subset_are_identified_independently():
    assigned = roster()
    assert len(assigned) == 455
    assert sum(r["release_100"] for r in assigned.values()) == 100
    assert sum(r["recording_state"] == "incomplete" for r in assigned.values()) == 44
    assert all(r["reference"] is not None for r in assigned.values())


def test_cli_checks_expected_export_before_scoring(tmp_path):
    receipts = tmp_path / "unverified.jsonl"
    receipts.write_text("unverified export")
    script = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/full_successor_score.py"
    report = tmp_path / "report"
    result = subprocess.run([sys.executable, str(script), str(receipts), str(report), "--expected-sha256", "0"*64],
                            capture_output=True, text=True)
    assert result.returncode == 2 and "differs from the expected SHA-256" in result.stderr
    assert not report.exists()


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


def test_cpu_and_residual_contributions_add_to_wall_savings():
    pairs = [({"elapsed_s": 10, "cpu_s": 7}, {"elapsed_s": 6, "cpu_s": 4}),
             ({"elapsed_s": 2, "cpu_s": 2}, {"elapsed_s": 2, "cpu_s": 2.1})]
    t = time_accounting(pairs)
    assert t["cpu_saved_s"] == pytest.approx(2.9)
    assert t["residual_saved_s"] == pytest.approx(1.1)
    assert t["cpu_fraction_of_wall_savings"] == pytest.approx(2.9 / 4)
    assert t["removing_positive_candidate_wall_minus_cpu"] == {
        "pairs": 2, "summed_speedup": 2, "median_paired_speedup": 1 / .7}
    assert time_accounting(pairs[1:])["cpu_fraction_of_wall_savings"] is None
    assert time_accounting([])["removing_positive_candidate_wall_minus_cpu"]["pairs"] == 0


def test_squared_error_influence_uses_identical_fixes_and_can_exceed_net():
    pairs = [({"case": case, "c0_error_km": a}, {"case": case, "c0_error_km": b})
             for case, a, b in [("A", 1, 3), ("B", 2, 1), ("C", None, 25)]]
    report = squared_error_influence(pairs, "c0")
    assert (report["shared"], report["worse"], report["remaining_shared"]) == (2, 1, 1)
    assert report["largest"] == {"case": "A", "squared_excess_km2": 8, "fraction_of_net_excess": 8/5}
    assert report["remaining_rms_km"] == {"installed": 2, "successor": 1}
    assert squared_error_influence(pairs[:1], "c0")["remaining_rms_km"] is None
    assert squared_error_influence(pairs[1:], "c0")["largest"] is None
    assert squared_error_influence([], "c0")["shared"] == 0


def test_calibration_segment_treats_clipped_endpoints_and_antimeridian_as_geography():
    degree = 111.1950802335
    assert calibration_segment_error_km([1, 180], [0, 179], [0, -179]) == pytest.approx(degree)
    assert calibration_segment_error_km([0, 180], [0, -179], [0, 179]) == pytest.approx(0, abs=1e-8)
    assert calibration_segment_error_km([0, 3], [0, 1], [0, 2]) == pytest.approx(degree)
    assert calibration_segment_error_km([0, 0], [0, 1], [0, 1]) == pytest.approx(degree)
    assert calibration_segment_error_km([5, 1], [0, 0], [0, 180]) is None
    assert calibration_segment_error_km([0, 0], None, None) is None


def matching_pair():
    assigned = {"DS30-test": dict(case_id="original", raw_authority="a"*64, reference=[48., 7.], release_100=True,
                                  recording_state="complete")}
    rows = [dict(case="DS30-test", case_id="original", algorithm=k, build_sha256=PINS[k],
                 historical_first100=True, manifest_raw_authority_sha256="a"*64,
                 raw_authority_sha256="a"*64, first="installed", elapsed_s=1., cpu_s=.9,
                 requested_raw_authority_sha256="a"*64, authority_sha256="b"*64,
                 attempt_result_sha256="e"*64, timing_scope="raw_launcher_through_exit_plus_common_publication_verification",
                 generation=1, same_lease=True, child_started_unix_ns=1 if k == "installed" else 3,
                 child_finished_unix_ns=2 if k == "installed" else 4,
                 child_elapsed_s=.95, child_cpu_s=.86, validator_elapsed_s=.05, validator_cpu_s=.04,
                 outcome="complete", arms=arms([48., 7.])) for k in ("installed", "successor")]
    return rows, assigned


def test_requires_complete_matched_pair_and_keeps_two_different_outcomes():
    rows, assigned = matching_pair()
    with pytest.raises(ValueError, match="measured arms"):
        paired_rows(rows[1:], assigned)
    rows[1].update(outcome="withheld", arms=arms(None))
    rows[0].update(input_blocks=0, output_blocks=32)
    a, b = paired_rows(rows, assigned)[0]
    assert (a["input_blocks"], a["output_blocks"], b["input_blocks"]) == (0, 32, None)
    assert (a["c0_error_km"], b["c0_error_km"], b["fitted_c_fix"]) == (0., None, False)
    assert b["between_children_s"] == 1e-9
    with pytest.raises(ValueError, match="Duplicate"):
        paired_rows(rows + rows[:1], assigned)


@pytest.mark.parametrize(("field", "value"), [("first", "successor"), ("case_id", "other"),
                         ("raw_authority_sha256", "b"*64), ("cpu_s", None), ("outcome", "pending"),
                         ("outcome", "worker_failed"), ("build_sha256", "unset"),
                         ("child_started_unix_ns", 1), ("generation", 2)])
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


def test_relocation_requires_matched_proofs_and_enrolled_content_in_both_arms():
    rows, assigned = matching_pair()
    fields = dict(historic_raw_authority_sha256="1"*64, canonical_reopened_inventory_sha256="2"*64,
                  relocation_proof_sha256="3"*64, prior_preflight_sha256="4"*64)
    assigned["DS30-test"]["physical_content"] = "5"*64
    for r in rows:
        r.update(**fields, verified_pair=True, raw_identity_sha256="5"*64)
    a, b = paired_rows(rows, assigned)[0]
    assert a["relocation_proof_sha256"] == b["relocation_proof_sha256"] == "3"*64
    rows[1]["raw_identity_sha256"] = "6"*64
    with pytest.raises(ValueError, match="enrolled physical"):
        paired_rows(rows, assigned)
    rows[1]["raw_identity_sha256"] = "5"*64
    rows[1]["relocation_proof_sha256"] = "7"*64
    with pytest.raises(ValueError, match="Unmatched"):
        paired_rows(rows, assigned)


def test_sealed_rows_reach_figures_tables_and_machine_report(tmp_path):
    assigned = roster()
    template, _ = matching_pair()
    rows = []
    for i, (case, item) in enumerate(assigned.items()):
        for role in template:
            fix = role["algorithm"] == "installed" or i > 0
            wall = 2. if role["algorithm"] == "installed" and i > 0 else 1.
            rows.append({**role, "case": case, "case_id": item["case_id"],
                         "elapsed_s": wall, "child_elapsed_s": wall - role["validator_elapsed_s"],
                         "historical_first100": item["release_100"], "manifest_raw_authority_sha256": item["raw_authority"],
                         "first": "installed" if i % 2 else "successor",
                         "child_started_unix_ns": 1 if (role["algorithm"] == "installed") == bool(i % 2) else 3,
                         "child_finished_unix_ns": 2 if (role["algorithm"] == "installed") == bool(i % 2) else 4,
                         "outcome": "complete" if fix else "withheld",
                         "arms": arms([48., 7.] if fix else None)})
            if i in (5, 6):
                lat, lon = item["reference"]
                endpoints = arms([lat + .001, lon])
                if role["algorithm"] == "successor":
                    endpoints = arms([lat + .02, lon])
                    endpoints["c0"]["latlon"] = [lat + (-.01 if i == 5 else .01), lon]
                rows[-1]["arms"] = endpoints
    failed = next(row for row in rows if row["case"] == "DS30-0397" and row["algorithm"] == "installed")
    failed.update(outcome="solver_failed", arms=arms(None), timing_scope="raw_launch_to_exit")
    pairs = paired_rows(rows, assigned)
    offer = dict(center=[48., 7.], screen_center=[48., 6.], width_km=25)
    prior = compare_centers(pairs, assigned, offer)
    write_report(pairs, tmp_path, {case: r["release_100"] for case, r in assigned.items()}, "c"*64,
                 renderer_revision="d"*40, position_moments=shared_position_moments(rows, assigned), prior=prior)
    report = json.loads((tmp_path / "summary.json").read_bytes())
    assert report["search_center_comparison"]["fixes"]["fitted_c"]["installed"]["closer_than_center"] == 2
    assert report["report_renderer_revision"] == "d"*40
    for arm in ("c0", "fitted_c"):
        for role in ("installed", "successor"):
            moments = report["position_error_moments_on_shared_fixes"][arm][role]
            assert moments["n"] == 453
            assert moments["radial_mse_km2"] == pytest.approx(moments["squared_mean_offset_km2"] + moments["centered_mse_km2"])
    assert report["cohorts"]["All DS30 recordings"]["wall"]["pairs"] == 455
    assert report["cohorts"]["All DS30 recordings"]["time_accounting"]["cpu_saved_s"] == 0
    assert report["twofold_wall_time_target"] == {
        "required_speedup": 2.0, "summed_speedup": False, "median_paired_speedup": True, "both_met": False}
    assert report["paired_error_changes"]["fitted_c"]["lost"] == 1
    assert report["paired_error_changes"]["fitted_c"]["gained"] == 1
    joint = report["position_error_on_twice_as_fast_recordings"]
    assert joint["twice_as_fast"] == 454
    assert joint["calibrations"]["both"] == {
        "shared_scored": 453, "twice_as_fast_with_shared_error": 453, "same_or_smaller_error": 451,
        "larger_error": 2, "twice_as_fast_without_shared_error": 1}
    assert report["calibration_blend_bound"] == {
        "shared_scored": 453, "tolerance_km": .001, "fitted_regressions": 2, "regressions_remaining": 1}
    assert report["paired_outcomes"] == [{"installed": "complete", "successor": "complete", "recordings": 453},
                                         {"installed": "complete", "successor": "withheld", "recordings": 1},
                                         {"installed": "solver_failed", "successor": "complete", "recordings": 1}]
    assert report["cohorts"]["Both builds reached publication verification"]["assigned"] == 454
    assert "| Solver failure | 1 | 0 | 0 | 1 |" in (tmp_path / "README.md").read_text()
    assert len(list(csv.DictReader((tmp_path / "recordings.csv").read_text().splitlines()))) == 910
    markdown = (tmp_path / "README.md").read_text()
    assert "met **1 of 2** wall-time targets" in markdown
    assert "DS30-0397 solver and publication audit" in markdown
    for figure in ("runtime.png", "position-error.png", "runtime-histogram.png", "position-error-histogram.png",
                   "paired-speed-and-error.png"):
        with Image.open(tmp_path / figure) as png:
            assert png.format == "PNG"
            png.verify()
        assert f"]({figure})" in markdown
    assert "including withheld and failed attempts" in markdown
    assert "assigned totals and the numbers withheld, failed or fixed without a scored reference" in markdown
