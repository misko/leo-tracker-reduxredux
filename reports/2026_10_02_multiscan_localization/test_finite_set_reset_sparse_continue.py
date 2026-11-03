from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import finite_set_reset_sparse_continue as runner
import numpy as np
import pytest


def state(objective, *, success=False, value=0.0, bank=(0, 1), captures=2):
    penalty = 7.0
    return {
        "parameters": np.array([value, 0, 0, 0, 0, 0, 0, 0], dtype=float),
        "capture_jumps_hz": np.zeros((captures, 2)),
        "success": success,
        "message": "projected_gradient" if success else "budget_exhausted",
        "status": "converged" if success else "nonconverged",
        "convergence_reason": "projected_gradient" if success else "budget_exhausted",
        "algorithm_version": "complete-data-fisher-capture-reset-gn/v1",
        "gn_semantics": "complete-data-fisher-gn/v2",
        "satellite_indices": np.asarray(bank),
        "satellite_count": len(bank),
        "objective": float(objective),
        "initial_objective": float(objective),
        "selection_score": float(objective + penalty),
        "model_penalty": {"total_penalty": penalty},
        "satellite_weights": np.ones(len(bank)),
    }


def source_fit(*, captures=2):
    bank = (0, 1)
    baseline = state(10, value=10, bank=bank, captures=captures)
    fresh = state(20, value=20, bank=bank, captures=captures)
    nested = {
        "capture_jumps_hz": np.zeros((captures, 2)),
        "group_count": 100,
        "objective": 30.0,
    }
    selected = copy.deepcopy(baseline)
    return {
        "full_bank": list(bank),
        "trials": [selected],
        "attempts": [
            {
                "satellite_indices": list(bank),
                "satellite_count": len(bank),
                "nested_parent": nested,
                "baseline_refinement": baseline,
                "fresh_child_refinement": fresh,
                "baseline_branch_complete": False,
                "fresh_branch_complete": False,
                "selected_multistart_branch": "baseline_refinement",
            }
        ],
    }


def reconstructed_source_fit(*, captures=2):
    fit = source_fit(captures=captures)
    fit["attempts"][0]["nested_parent"] = state(
        30, value=30, bank=(0, 1), captures=captures
    )
    return fit


def source_record(tmp_path, unit_id="DS10-D02"):
    inherited = tmp_path / "inherited.py"
    bound = tmp_path / "bundle.npz"
    inherited.write_text("inherited")
    bound.write_text("bound")
    fit = source_fit(captures=2 if "-D" in unit_id else 4)
    fit.update(
        optimizer="complete-data-fisher-capture-reset-gn/v1",
        refinements_per_bank=2,
        budget_s_per_refinement=15.0,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        slope_bound_hz_s=50.0,
        all_refinement_branches_complete=False,
    )
    size = 2 if "-D" in unit_id else 4
    unit = {
        "unit_id": unit_id,
        "size": size,
        "session_ids": [f"s{index}" for index in range(size)],
    }
    upstream_path = (
        tmp_path / "runs" / "finite-set-grouped-cohort-v1" / unit_id / "fit.json"
    )
    upstream_path.parent.mkdir(parents=True)
    upstream_trial = state(30, value=30, bank=(0, 1), captures=size)
    upstream_trial["catalog_numbers"] = np.array([10, 20])
    upstream = {
        "schema": "finite-set-grouped-cohort/v1",
        "run_id": "finite-set-grouped-cohort-v1",
        "unit": unit,
        "dataset": unit_id[:4],
        "sealed_utc": "2026-10-02T00:00:00+00:00",
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "fit": {"trials": [upstream_trial]},
    }
    upstream_path.write_text(json.dumps(upstream, default=lambda value: value.tolist()))
    upstream_digest = runner._digest(upstream_path)
    return {
        "schema": runner.SOURCE_SCHEMA,
        "run_id": runner.SOURCE_RUN,
        "unit": unit,
        "dataset": unit_id[:4],
        "source_run_id": "finite-set-grouped-cohort-v1",
        "source_fit_sha256": upstream_digest,
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed": True,
        "sealed_utc": "2026-10-02T00:00:00+00:00",
        "source_hashes": {
            str(inherited.resolve()): runner._digest(inherited),
            str(upstream_path.resolve()): upstream_digest,
        },
        "bound_input_hashes": {str(bound.resolve()): runner._digest(bound)},
        "fit": fit,
    }


def test_supports_only_the_four_sealed_balanced_pilots():
    assert runner.SUPPORTED_UNITS == (
        "DS10-D02",
        "DS11-D02",
        "DS10-Q02",
        "DS11-Q02",
    )
    assert runner.parse_args(["--unit", "DS11-Q02"]).unit == "DS11-Q02"
    with pytest.raises(SystemExit):
        runner.parse_args(["DS11-Q02"])


def test_source_dependency_closure_precedes_validation(tmp_path):
    root = tmp_path / "reports" / "2026_10_02_multiscan_localization"
    root.mkdir(parents=True)
    for name in runner.DIRECT_DEPENDENCIES:
        (root / name).write_text(name)
    benchmark = root / runner.SPARSE_BENCHMARK.name
    benchmark.write_text("benchmark")
    source_path = root / "source.json"
    source_path.write_text("source")
    inherited = root / "inherited.py"
    inherited.write_text("inherited")
    bound = root / "input.npz"
    bound.write_text("bound")
    upstream = root / "runs" / "upstream-v1" / "DS10-D02" / "fit.json"
    upstream.parent.mkdir(parents=True)
    upstream.write_text("upstream")
    bundle = root.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("bundle")
    source = {
        "source_run_id": "upstream-v1",
        "unit": {"unit_id": "DS10-D02"},
        "source_hashes": {str(inherited): "a" * 64, str(upstream): "c" * 64},
        "bound_input_hashes": {str(bound): "b" * 64},
    }
    original_benchmark = runner.SPARSE_BENCHMARK
    try:
        runner.SPARSE_BENCHMARK = benchmark
        paths = runner.source_dependency_paths(source, source_path, root=root)
    finally:
        runner.SPARSE_BENCHMARK = original_benchmark
    names = {path.name for path in paths}
    assert {
        "finite_set_reset_cohort.py",
        "finite_set_reset_multistart.py",
        "capture_reset_gn.py",
        "finite_set_sparse.py",
        "finite_set_tau_continue.py",
        "inherited.py",
        "input.npz",
        "fit.json",
        "source.json",
        "bundle.py",
    } <= names


def test_source_validation_preserves_failed_branch_truth(tmp_path):
    source = source_record(tmp_path)
    assert runner.validate_source_record(source, "DS10-D02", root=tmp_path) is source
    changed = copy.deepcopy(source)
    changed["fit"]["attempts"][0]["baseline_branch_complete"] = True
    with pytest.raises(ValueError, match="completion flags"):
        runner.validate_source_record(changed, "DS10-D02", root=tmp_path)
    with pytest.raises(ValueError, match="four frozen"):
        runner.validate_source_record(source, "DS10-D03", root=tmp_path)


@pytest.mark.parametrize("unit_id", runner.SUPPORTED_UNITS)
def test_actual_source_receipts_validate_and_reconstruct_nested_incumbents(unit_id):
    source_path = runner.ROOT / "runs" / runner.SOURCE_RUN / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    runner.validate_source_record(source, unit_id)
    assert set(source["fit"]["attempts"][0]["nested_parent"]) == {
        "capture_jumps_hz",
        "group_count",
        "objective",
    }
    upstream_path = runner.upstream_source_path(source)
    assert runner._digest(upstream_path) == source["source_fit_sha256"]
    reconstructed = runner.reconstruct_nested_incumbents(
        source, json.loads(upstream_path.read_text())
    )
    for attempt in reconstructed["attempts"]:
        nested = attempt["nested_parent"]
        assert nested["algorithm_version"] == "continuous-incumbent-in-reset-model/v1"
        assert nested["success"] is False
        assert np.array_equal(nested["satellite_indices"], attempt["satellite_indices"])


def test_incumbent_tie_prefers_converged_but_real_improvement_wins():
    failed = state(10.0, success=False)
    tied = state(10.0 + 5e-8, success=True)
    name, _ = runner.choose_incumbent((("failed", failed), ("tied", tied)))
    assert name == "tied"
    lower = state(9.999, success=False)
    name, _ = runner.choose_incumbent((("tied", tied), ("lower", lower)))
    assert name == "lower"


def test_likelihood_pair_separates_omission_bound_from_roundoff():
    class Plan:
        def predict(self, parameters):
            return np.array([1.0, 2.0]), np.array([True, True]), None

    class Adapter:
        def __init__(self, total, gradient, precision, sparse=False):
            self.total = total
            self.gradient = gradient
            self.precision = precision
            self.sparse = sparse

        def evaluate(self, predicted, visible, **options):
            result = {
                "total_log_likelihood": self.total,
                "log_likelihood": np.array([self.total]),
                "prediction_gradient": np.full((1, 2), self.gradient),
                "prediction_precision": np.full((1, 2), self.precision),
            }
            if self.sparse:
                result.update(
                    total_omitted_log_likelihood_upper_bound=2e-14,
                    packed_satellite_count=1,
                    retained_satellite_count_per_group=np.array([1]),
                )
            return result

    data = SimpleNamespace(
        times=np.array([0.0]),
        numbers=np.array([1, 2]),
        capture_index=np.array([0]),
        receiver=np.array([0]),
        child_sessions=("first", "second"),
        child_origins_utc_ns=np.array([0, 1], dtype=np.int64),
    )
    candidate = state(0, bank=(0, 1))
    candidate["parameters"][6:] = [0.5, -0.5]
    receipt = runner.evaluate_likelihood_pair(
        data,
        candidate,
        np.array([0, 1]),
        Adapter(-10.0, 1.0, 2.0),
        Adapter(-10.0 - 3e-10, 1.0 + 4e-16, 2.0 + 2e-18, sparse=True),
        plan=Plan(),
    )
    assert receipt["theoretical_omission_log_likelihood_upper_bound"] == 2e-14
    assert abs(receipt["observed_total_log_likelihood_roundoff_difference"]) > 2e-14
    assert receipt["maximum_absolute_prediction_gradient_difference"] == pytest.approx(4e-16)
    assert receipt["parity_within_tolerance"] is True


def test_every_branch_continues_from_own_state_and_sparse_success_is_not_inherited():
    fit = reconstructed_source_fit()
    calls = []

    class Adapter:
        def __init__(self, kind):
            self.kind = kind

    def dense_factory(selected, full):
        assert (selected, full) == (2, 2)
        return Adapter("dense")

    def sparse_factory(dense):
        assert dense.kind == "dense"
        return Adapter("sparse")

    def evaluator(data, candidate, satellites, dense, sparse, *, plan):
        objective = float(candidate["objective"])
        result = {"dense_objective": objective}
        if sparse is not None:
            result.update(
                sparse_objective=objective,
                theoretical_omission_log_likelihood_upper_bound=1e-14,
                observed_total_log_likelihood_roundoff_difference=2e-10,
                parity_within_tolerance=True,
            )
        return result

    def refiner(data, parameters, jumps, satellites, support, adapter, **options):
        start = float(parameters[0])
        calls.append((adapter.kind, start, options["budget_s"]))
        if adapter.kind == "sparse":
            result = state(start - 1, success=True, value=start - 1)
            result["initial_objective"] = start
            return result
        success = start < 15
        result = state(start - 1, success=success, value=start - 1)
        result["initial_objective"] = start
        return result

    result = runner.continue_reset_sparse_branches(
        SimpleNamespace(numbers=np.array([1, 2])),
        fit,
        dense_factory=dense_factory,
        sparse_factory=sparse_factory,
        refiner=refiner,
        evaluator=evaluator,
        plan_factory=lambda data, satellites: object(),
    )
    assert calls == [
        ("sparse", 10.0, 30.0),
        ("dense", 9.0, 5.0),
        ("sparse", 20.0, 30.0),
        ("dense", 19.0, 5.0),
    ]
    attempt = result["attempts"][0]
    assert attempt["baseline_refinement"]["endstate_success_dense_checked_only"] is True
    assert attempt["fresh_child_refinement"]["sparse_gn"]["success"] is True
    assert attempt["fresh_child_refinement"]["endstate_success_dense_checked_only"] is False
    assert result["all_branch_endstates_converged"] is False
    assert result["selection"]["selection_resolved"] is False
    assert result["trials"][0]["success"] is True


def test_all_dense_branch_endstates_are_required_for_resolution():
    fit = reconstructed_source_fit()

    class Adapter:
        def __init__(self, kind):
            self.kind = kind

    def evaluator(data, candidate, satellites, dense, sparse, *, plan):
        result = {"dense_objective": float(candidate["objective"])}
        if sparse is not None:
            result.update(
                sparse_objective=float(candidate["objective"]),
                parity_within_tolerance=True,
            )
        return result

    def refiner(data, parameters, jumps, satellites, support, adapter, **options):
        start = float(parameters[0])
        result = state(start - 1, success=True, value=start - 1)
        result["initial_objective"] = start
        return result

    result = runner.continue_reset_sparse_branches(
        SimpleNamespace(numbers=np.array([1, 2])),
        fit,
        dense_factory=lambda selected, full: Adapter("dense"),
        sparse_factory=lambda dense: Adapter("sparse"),
        refiner=refiner,
        evaluator=evaluator,
        plan_factory=lambda data, satellites: object(),
    )
    assert result["all_branch_endstates_converged"] is True
    assert result["selection"]["selection_resolved"] is True
    assert result["selection"]["success"] is True


def test_parity_failure_forces_dense_success_to_remain_unresolved():
    fit = reconstructed_source_fit()

    class Adapter:
        pass

    calls = 0

    def evaluator(data, candidate, satellites, dense, sparse, *, plan):
        nonlocal calls
        result = {"dense_objective": float(candidate["objective"])}
        if sparse is not None:
            calls += 1
            result.update(
                sparse_objective=float(candidate["objective"]),
                parity_within_tolerance=calls != 2,
            )
        return result

    def refiner(data, parameters, jumps, satellites, support, adapter, **options):
        start = float(parameters[0])
        result = state(start - 1, success=True, value=start - 1)
        result["initial_objective"] = start
        return result

    result = runner.continue_reset_sparse_branches(
        SimpleNamespace(numbers=np.array([1, 2])),
        fit,
        dense_factory=lambda selected, full: Adapter(),
        sparse_factory=lambda dense: Adapter(),
        refiner=refiner,
        evaluator=evaluator,
        plan_factory=lambda data, satellites: object(),
    )
    baseline = result["attempts"][0]["baseline_refinement"]
    assert baseline["dense_success_before_parity_gate"] is True
    assert baseline["endstate_success_dense_checked_only"] is False
    assert baseline["sparse_dense_parity_resolved"] is False
    assert result["selection"]["selection_resolved"] is False


def test_snapshot_detects_corruption(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"value": 1}))
    snapshot = runner._snapshot_files((path,))
    runner._assert_snapshot_unchanged(snapshot)
    path.write_text(json.dumps({"value": 2}))
    with pytest.raises(RuntimeError, match="changed before seal"):
        runner._assert_snapshot_unchanged(snapshot)
