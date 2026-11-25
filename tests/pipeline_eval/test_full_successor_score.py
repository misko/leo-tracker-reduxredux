import csv
import gzip
import json
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image

from full_successor_score import (PINS, calibration_segment_error_km, capture_day_sensitivity, capture_pace, compare_centers, empirical_accuracy_gap,
                                  field_stage_history, frozen_stage_order, half_time_outcomes, outcomes_summary, paired_rf_and_error, paired_rows,
                                  paired_timing, roster, score_arms, shared_position_moments, squared_error_influence,
                                  time_accounting, write_report)


def arms(point):
    return {name: {"latlon": point, "rf_rms_hz": 100 if point is not None else None}
            for name in ("c0", "fitted_c")}


def test_joint_half_time_cells_keep_signed_failures_ties_and_launch_order():
    rows = []
    for wall, cpu, order, error in [(5, 3, "installed", None), (5, 5, "successor", 1.),
                                    (7, 3, "installed", 2.), (7, 5, "successor", .5)]:
        a = dict(elapsed_s=10, cpu_s=6, first=order, outcome="complete", c0_error_km=1., fitted_c_error_km=1.)
        b = dict(elapsed_s=wall, cpu_s=cpu, first=order, outcome="solver_failed" if error is None else "complete",
                 c0_error_km=error, fitted_c_error_km=None if error is None else error + .25)
        rows.append((a, b))
    stats = half_time_outcomes(rows)
    assert {k: g["pairs"] for k, g in stats.items()} == dict(wall_and_cpu=1, wall_only=1, cpu_only=1, neither=1)
    assert stats["wall_and_cpu"]["outcomes"]["successor"] == {"solver_failed": 1}
    assert stats["wall_and_cpu"]["accuracy"]["fitted_c"]["shared"] == 0
    assert stats["wall_only"]["first"] == {"installed": 0, "successor": 1}
    assert stats["wall_only"]["accuracy"] == {"c0": {"shared": 1, "equal_or_closer": 1},
                                              "fitted_c": {"shared": 1, "equal_or_closer": 0}}
    assert stats["neither"]["accuracy"]["fitted_c"] == {"shared": 1, "equal_or_closer": 1}


def test_all_ds30_and_historical_subset_are_identified_independently():
    assigned = roster()
    assert len(assigned) == 455
    assert sum(r["release_100"] for r in assigned.values()) == 100
    assert sum(r["recording_state"] == "incomplete" for r in assigned.values()) == 44
    assert all(r["reference"] is not None for r in assigned.values())
    assert all(r["capture_span_s"] > 0 for r in assigned.values())
    assert sum(r["scheduled_edge"] == "lower" for r in assigned.values()) == 233
    assert sum(r["scheduled_edge"] == "upper" for r in assigned.values()) == 222


def test_capture_pace_charges_each_recording_and_distinguishes_timely_withholds_and_accurate_fixes():
    def row(case, state, seconds, zero, fitted):
        return dict(case=case, recording_state=state, elapsed_s=seconds,
                    c0_error_km=zero, fitted_c_error_km=fitted)
    pairs = [(row("short", "incomplete", 1., None, None), row("short", "incomplete", 2., .1, .1)),
             (row("long", "complete", 60., 1.1, 1.), row("long", "complete", 30., .9, 1.2))]
    assigned = {"short": dict(capture_span_s=1.), "long": dict(capture_span_s=60.)}
    stats = capture_pace(pairs, assigned)
    assert stats["all"]["installed"]["finished_within_span"] == 2
    assert stats["all"]["successor"]["finished_within_span"] == 1
    assert stats["all"]["successor"]["wall_over_span"]["p50"] == 1.25
    assert stats["all"]["installed"]["within_1km_and_span"] == {"c0": 0, "fitted_c": 1}
    assert stats["complete"]["successor"]["within_1km_and_span"] == {"c0": 1, "fitted_c": 0}
    assert stats["interrupted"]["successor"]["within_1km_and_span"] == {"c0": 0, "fitted_c": 0}


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


def test_frequency_and_geographic_changes_use_the_same_available_pairs():
    def row(hz, km):
        return dict(c0_rf_rms_hz=hz, c0_error_km=km)

    changes = [row(9,1), row(9,3), row(11,1), row(11,3), row(11,2), row(10,3), row(None,1), row(9,None)]
    result = paired_rf_and_error([(row(10,2), changed) for changed in changes], "c0")
    assert result == dict(comparable=6, rf_lower_closer=1, rf_lower_farther=1, rf_higher_closer=1,
                          rf_higher_farther=1, tied=2)


@pytest.mark.parametrize("installed,candidate,deficit,at,radius", [
    ([1., 1., 2., None], [4., 1., .5, 3.], 1, 2., 1.),
    ([1., 2., None], [None, None, 1.], 1, 2., None),
    ([None, 1.], [1., None], 0, None, 0.),
    ([None], [None], 0, None, 0.),
])
def test_curve_shortfall_and_displacement_allow_reranking(installed, candidate, deficit, at, radius):
    pairs = [(dict(c0_error_km=a), dict(c0_error_km=b)) for a, b in zip(installed, candidate, strict=True)]
    actual = empirical_accuracy_gap(pairs, "c0")
    assert actual["largest_coverage_deficit"] == deficit
    assert actual["first_threshold_km"] == at
    assert actual["maximum_displacement_lower_bound_km"] == radius


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


def test_field_stages_follow_original_membership_and_defer_pairs_beyond_a_hole():
    assigned = roster()
    order = frozen_stage_order({k: (r["case_id"], r["physical_content"]) for k, r in assigned.items()})
    assert order[:8] == ["DS30-0107", "DS30-0049", "DS30-0178", "DS30-0019",
                         "DS30-0274", "DS30-0330", "DS30-0397", "DS30-0452"]
    def pair(case):
        base = dict(case=case, elapsed_s=2., cpu_s=2., c0_fix=True, fitted_c_fix=True,
                    c0_error_km=.2, fitted_c_error_km=1.)
        return base, dict(base, elapsed_s=1., cpu_s=1., c0_error_km=2.)
    actual = field_stage_history([pair(case) for case in reversed(order[:4] + order[5:8])], order)
    assert actual["completed_prefix"] == 4 and actual["measured_beyond_prefix"] == 3
    last = actual["stages"][-1]
    assert last["newly_added"]["pairs"] == 2 and last["cumulative"]["pairs"] == 4
    assert last["cumulative"]["at_or_under_half_wall"] == 4
    assert last["newly_added"]["successor"]["c0"]["within_1km"] == 0
    assert last["newly_added"]["successor"]["fitted_c"]["within_1km"] == 2


def test_sealed_rows_reach_figures_tables_and_machine_report(tmp_path):
    from reports.ALGO08.v3.ds30_repeatability import frozen_stage_order, score_neighbors
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
                 renderer_revision="d"*40, position_moments=shared_position_moments(rows, assigned), prior=prior,
                 capture_days=capture_day_sensitivity(pairs, assigned), pace=capture_pace(pairs, assigned),
                 nearby=score_neighbors(frozen_stage_order({case: (r["case_id"], r["physical_content"])
                                                            for case, r in assigned.items()}), assigned, rows))
    report = json.loads((tmp_path / "summary.json").read_bytes())
    for arm in ("c0", "fitted_c"):
        nearby = report["nearby_scan_separations"][arm]
        assert nearby["pairs"] == len(nearby["recordings"]) == 204
        assert len({r[k] for r in nearby["recordings"] for k in ("first_enrolled", "second_enrolled")}) == 408
        assert 0 < nearby["shared"] <= min(nearby["paired_fixes"].values()) <= 204
    assert "Position repeatability on nearby recordings" in (tmp_path / "README.md").read_text()
    deadlines = report["accurate_fixes_by_deadline"]
    assert len(deadlines) == 12 and all(r["assigned"] == 455 for r in deadlines)
    for r in deadlines:
        for role in ("installed", "successor"):
            assert r[role] == report["cohorts"]["All DS30 recordings"][role][r["calibration"]][
                f"within_{r['radius_km']}km"]
    assert "Candidate by 60 s" in (tmp_path / "README.md").read_text()
    for role in ("installed", "successor"):
        for arm in ("c0", "fitted_c"):
            for metric in ("within_1km", "within_2km", "fixes"):
                cohorts = report["cohorts"]
                assert sum(cohorts[f"Scheduled {edge} edge"][role][arm][metric]
                           for edge in ("lower", "upper")) == cohorts["All DS30 recordings"][role][arm][metric]
    assert report["runtime_relative_to_observing_span"]["interrupted"]["pairs"] == 44
    assert "Replay time compared with recording duration" in (tmp_path / "README.md").read_text()
    stages = report["field_stages"]["stages"]
    assert [r["last_position"] for r in stages] == [2, 8, 30, 100, 455]
    assert [r["newly_added"]["pairs"] for r in stages] == [2, 6, 22, 70, 355]
    assert stages[-1]["cumulative"]["wall"] == report["cohorts"]["All DS30 recordings"]["wall"]
    budgets = report["accuracy_repair_budget"]
    assert len(budgets) == 10 and all(item["pairs"] == 455 for item in budgets)
    assert {item["tolerance_km"] for item in budgets} == {0., .25}
    days = report["capture_day_sensitivity"]
    assert len(days) == 8 and days["2026-11-13"]["on_day"]["pairs"] == 44
    assert sum(row["on_day"]["pairs"] for row in days.values()) == 455
    for row in days.values():
        measured, remaining = row["on_day"], row["omitting_day"]
        assert measured["pairs"] + remaining["pairs"] == 455
        for arm in ("c0", "fitted_c"):
            for role in ("installed", "successor"):
                assert measured["within_1km"][arm][role] + remaining["within_1km"][arm][role] == (
                    report["cohorts"]["All DS30 recordings"][role][arm]["within_1km"])
    assert days["2026-11-13"]["omitting_day"]["wall"]["summed_speedup"] == 2.
    assert days["2026-11-14"]["omitting_day"]["wall"]["summed_speedup"] < 2.
    for arm in ("c0", "fitted_c"):
        for radius in (1, 2):
            label = f"within_{radius}km"
            limit = report["paired_error_changes"][arm]["paired_distance_coverage"][label]
            totals = report["cohorts"]["All DS30 recordings"]
            assert sum(limit.values()) == 455
            assert limit["both"] + limit["gained"] == totals["successor"][arm][label]
            assert limit["both"] + limit["lost"] == totals["installed"][arm][label]
    assert report["search_center_comparison"]["fixes"]["fitted_c"]["installed"]["closer_than_center"] == 2
    assert report["report_renderer_revision"] == "d"*40
    for arm in ("c0", "fitted_c"):
        for role in ("installed", "successor"):
            moments = report["position_error_moments_on_shared_fixes"][arm][role]
            assert moments["n"] == 453
            assert moments["radial_mse_km2"] == pytest.approx(moments["squared_mean_offset_km2"] + moments["centered_mse_km2"])
    assert report["cohorts"]["All DS30 recordings"]["wall"]["pairs"] == 455
    assert report["cohorts"]["All DS30 recordings"]["time_accounting"]["cpu_saved_s"] == 0
    assert sum(v["pairs"] for v in report["per_recording_half_time_outcomes"].values()) == 455
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
    assert "Recordings needing repair for 2×" in markdown and "| 100% | Unreachable | Unreachable |" in markdown
    assert "| 2026-11-13 | 44 |" in markdown
    receipts = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements"
    prefix = json.loads(gzip.decompress((receipts / "installed-receiver-first30.json.gz").read_bytes()))["aggregate"]
    assert f"**{1 / prefix['twice_as_fast_prefix']['summed']:.2f}× summed**" in markdown
    assert f"**{prefix['prefix_speedup']['required_rate']:.2f}×**" in markdown
    agreement = json.loads(gzip.decompress((receipts / "first30-native-agreement.json.gz").read_bytes()))
    assert f"{agreement['counts']['short']['matched']:,} short-aperture peaks" in markdown
    radio = agreement["held"]["cfo_hz"]["radio"]
    assert f"{radio['rms_before']:.3f} to {radio['rms_after']:.3f} Hz RMS" in markdown
    first = json.loads(gzip.decompress((receipts / "ds30-0049-saved-crossover.json.gz").read_bytes()))
    errors = [first["cells"][cell]["arms"]["fitted_c"]["error_m"] / 1000 for cell in
              ("installed-installed", "successor-installed", "installed-successor", "successor-successor")]
    assert "| DS30-0049 | " + " | ".join(f"{value:.3f}" for value in errors) + " |" in markdown
    for case in ("0086", "0220"):
        path = receipts / f"field-receiver-solver-cross-{case}.json.gz"
        receipt = json.loads(gzip.decompress(path.read_bytes()))
        measured = receipt["score"]["arms"]["fitted_c"]["error_km"]
        values = [measured[k] for k in ("installed/full", "charted/full", "installed/mixed", "charted/mixed")]
        assert f"| DS30-{case} | " + " | ".join(f"{value:.3f}" for value in values) + " |" in markdown
    assert "field-receiver-solver-cross-0086.md)" in markdown
    masked = json.loads((receipts / "held-shrink-0019-ram.json").read_bytes())
    for before, after in masked["scientific"]["position_error_m"].values():
        assert f"{before:.0f} m | {after:.0f} m |" in markdown
    before, after = masked["scientific"]["conditional_rf_rms_hz"]["fitted_c"]
    assert f"{before:.2f} to {after:.2f} Hz" in markdown
    other = json.loads((receipts / "held-shrink-0274.json").read_bytes())
    for arm in ("c0", "fitted_c"):
        values = [other[r]["error_m"][arm] for r in ("installed_raw", "ordinary_saved", "half_blend_saved")]
        assert " | ".join(f"{v:.0f} m" for v in values) in markdown
    assert f"{masked['timing']['through_exit_wall_s']:.2f} and {other['half_blend_saved']['wall_s']:.2f} seconds" in markdown
    assert "held-shrink-0019-ram.md)" in markdown and "held-shrink-0274.md)" in markdown
    grid = json.loads(gzip.decompress((receipts / "grid-time-ceiling-first62.json.gz").read_bytes()))["groups"]["all_62"]
    assert f"{grid['seconds']['grid']:.2f} seconds of the {grid['measured']['seconds_above_half']:.2f} seconds" in markdown
    bound = grid["native_1p5_free_grid"]
    assert f"{bound['summed_speedup']:.3f}× summed and {bound['paired_median_speedup']:.3f}× at the paired median" in markdown
    pair = json.loads((receipts / "profiled-grid-export-0138-pair.json").read_bytes())["new_cells"]
    cells = [pair[k] for k in ("ordinary", "profiled")]
    old, new = [c["receipt"]["grid_audit"]["exact"]["cpu_ns"] / 1e9 for c in cells]
    assert f"Grid CPU time fell from {old:.3f} to {new:.3f} seconds" in markdown
    old, new = [c["internal_solve"]["cpu_s"] for c in cells]
    assert f"Whole-solve CPU time went from {old:.3f} to {new:.3f} seconds" in markdown
    south = json.loads(gzip.decompress((receipts / "profiled-grid-export-south.json.gz").read_bytes()))
    inside = south["offers"]["containing"]["readback"]
    assert not inside["accept"] and south["offers"]["omitted"]["readback"]["accept"]
    assert f"grid score changed by {inside['worst_nodes']['c0']['absolute_delta']:.5f}" in markdown
    assert "both exporters returned the same false fix" in markdown
    complement = json.loads((receipts / "held-cfo-complement-score.json").read_bytes())
    for case, study in complement["cases"].items():
        scored = study["even_eligible"]
        tight = scored["windows"]["250Hz_2samples"]
        assert f"from {tight['joint_before']} to {tight['joint_after']} of {scored['scored']} on {case}" in markdown
        loose = scored["windows"]["2250Hz_6samples"]
        assert loose["joint_before"] == loose["joint_after"]
    feature = json.loads(gzip.decompress((receipts / "held-cfo-features-timing.json.gz").read_bytes()))
    for row in feature["results"]:
        result = row["result"]
        assert f"{result['additional_feature']['wall_s']:.3f} s on {result['case']}" in markdown
    assert "3258963eb3aa9c134c0081ae4ab40287a9c16668" in markdown
    assert "met **1 of 2** wall-time targets" in markdown
    assert "| Restore all 104 installed detections on empty short lanes | 4.148 | 3.663 |" in markdown
    assert "| Restore those 104 detections and replace the 72 disagreeing winners | 3.532 | 3.204 |" in markdown
    assert "ds30-0086-joint-recovery.md)" in markdown
    ownership = json.loads((receipts / "missed-owner-support.json").read_bytes())["cases"]
    counts, losses = [], []
    for case in ("DS30-0049", "DS30-0086"):
        arm = ownership[case]["arms"]["fitted_c"]
        missing = arm["class_counts"]["missing"]
        counts.append((missing["installed_owner"], missing["installed_owner"] + missing["installed_nonowner"]))
        series = arm["time"]["metrics"]
        losses.append(1 - series["without_missing_shorts"]["quadratic_design_s4"] / series["original"]["quadratic_design_s4"])
    assert f"{counts[0][0]} of the {counts[0][1]} missing measurements" in markdown
    assert f"{counts[1][0]} of the {counts[1][1]} on DS30-0086" in markdown
    assert f"Doppler curvature fell by {losses[0]:.1%} and {losses[1]:.1%}" in markdown
    assert "missed-owner-support.md)" in markdown
    arrival = json.loads((receipts / "empty-lane-arrival-score.json").read_bytes())["cases"]["DS30-0086"]
    owned = arrival["owners"]["fitted_c"]
    assert f"{owned['windows']['primary']['interpolated']} of the {owned['installed_positive_denominator']}" in markdown
    assert f"proposed {arrival['queries']:,} windows, including {arrival['installed_empty_queries']:,}" in markdown
    assert "empty-lane-arrival.md)" in markdown
    assert "recovered 41 of the 44 missing installed assignments" in markdown
    assert "DS30-0397 solver and publication audit" in markdown
    assert "DS30-0210 solver and publication audit" not in markdown
    for figure in ("runtime.png", "position-error.png", "runtime-histogram.png", "position-error-histogram.png",
                   "paired-speed-and-error.png"):
        with Image.open(tmp_path / figure) as png:
            assert png.format == "PNG"
            png.verify()
        assert f"]({figure})" in markdown
    assert "including withheld and failed attempts" in markdown
    assert "assigned totals and the numbers withheld, failed or fixed without a scored reference" in markdown
