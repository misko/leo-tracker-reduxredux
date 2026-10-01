from __future__ import annotations

import hashlib
import json

from timing_diagnostics import diagnose


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return str(path)


def _digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_phases_and_joint_acceptance_do_not_reward_early_timeout(tmp_path):
    rows = []
    for arm, unit, accepted, runtime, receipt in (
        ("A1", "u1", True, 10., {"status": "converged_local_mode", "acquisition_seconds": 4.,
                                  "fits": [{"fit_seconds": 2.}], "cpu_seconds": 8.}),
        ("B1", "u1", True, 20., {"status": "converged_local_mode", "acquisition_seconds": 5.,
                                  "fits": [{"fit_seconds": 7.}], "cpu_seconds": 18.}),
        ("A1", "u2", False, 2., {"status": "error", "exception": {
            "message": "global acquisition proposal reached its wall budget"}}),
        ("B1", "u2", False, 3., {"status": "unresolved",
                                  "fits": [{"fit_seconds": 1., "reason": "wall_budget"}]}),
    ):
        receipt_path = tmp_path / arm / f"{unit}.json"
        launch_path = tmp_path / arm / f"{unit}.launch.json"
        _write(receipt_path, receipt)
        _write(launch_path, {"status": "complete", "returncode": 0})
        rows.append({"arm": arm, "unit_id": unit, "attempted": True,
                     "accepted": accepted, "runtime_s": runtime,
                     "receipt_path": str(receipt_path), "launch_path": str(launch_path)})
    evaluator = tmp_path / "evaluation.json"
    _write(evaluator, {"rows": rows})
    result = diagnose(evaluator, repository_root=tmp_path)
    assert result["coverage"] == {
        "planned_units_per_arm": 64,
        "attempted_by_arm": {"A1": 2, "B1": 2},
        "partial": True,
    }
    assert result["primary_phase_counts"]["A1"]["acquisition_timeout"] == 1
    assert result["primary_phase_counts"]["B1"]["optimizer_unresolved"] == 1
    assert result["all_attempt_paired_runtime"]["paired_count"] == 2
    assert result["jointly_accepted_paired_runtime"]["paired_count"] == 1
    assert result["jointly_accepted_paired_runtime"]["ratio_of_medians_b1_over_a1"] == 2.


def test_worker_timeout_is_separate_from_optimizer_state(tmp_path):
    receipt = tmp_path / "receipt.json"
    launch = tmp_path / "launch.json"
    _write(receipt, {"status": "unresolved", "fits": [{"reason": "iteration_limit"}]})
    _write(launch, {"status": "timeout", "timed_out": True})
    evaluator = tmp_path / "evaluation.json"
    _write(evaluator, {"rows": [{"arm": "A1", "unit_id": "u", "attempted": True,
        "accepted": False, "runtime_s": 90., "receipt_path": str(receipt),
        "launch_path": str(launch)}]})
    result = diagnose(evaluator, repository_root=tmp_path)
    assert result["primary_phase_counts"]["A1"]["worker_timeout"] == 1


def test_continuation_counts_only_resumed_fits_not_copied_parent_fits(tmp_path):
    copied = {"seed_index": 0, "seed": {"east_km": 1., "north_km": 2.},
              "fit_seconds": 3., "reason": "objective_stable", "converged": True}
    unresolved = {"seed_index": 1, "seed": {"east_km": 4., "north_km": 5.},
                  "fit_seconds": 7., "reason": "wall_budget", "converged": False}
    parent_path = tmp_path / "primary.json"
    _write(parent_path, {"fits": [copied, unresolved], "cpu_seconds": 12.})
    resumed = {**unresolved, "fit_seconds": 2., "reason": "objective_stable", "converged": True}
    child_path = tmp_path / "continuation.json"
    _write(child_path, {
        "parent": {"path": str(parent_path), "sha256": _digest(parent_path)},
        "fits": [copied, resumed], "cpu_seconds": 4.,
    })
    primary_eval = tmp_path / "primary-eval.json"
    final_eval = tmp_path / "final-eval.json"
    primary_row = {"arm": "A1", "unit_id": "u", "attempted": True, "accepted": False,
                   "runtime_s": 12., "receipt_path": str(parent_path)}
    final_row = {**primary_row, "accepted": True, "runtime_s": 16.,
                 "receipt_path": str(child_path)}
    _write(primary_eval, {"rows": [primary_row]})
    _write(final_eval, {"rows": [final_row]})
    result = diagnose(primary_eval, final_eval, repository_root=tmp_path)
    assert result["optimizer_fit_seconds_sum"]["A1"] == 12.
    assert result["native_cpu_seconds"]["A1"]["sum_s"] == 16.
