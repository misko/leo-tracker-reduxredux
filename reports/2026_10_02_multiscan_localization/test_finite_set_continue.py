import copy

import finite_set_continue
import numpy as np
import pytest


def trial(arm, bank, marker, *, success, objective):
    return {
        "arm": arm,
        "parameters": np.array([marker, marker + 1.0]),
        "satellite_indices": np.asarray(bank),
        "satellite_count": len(bank),
        "objective": float(objective),
        "selection_score": float(objective + len(bank)),
        "success": success,
        "status": "converged" if success else "nonconverged",
        "source_parameters": np.array([-marker]),
        "source_parameters_sha256": f"source-{marker}",
        "full_bank_count": 4,
        "per_satellite_probability": 0.2,
        "raw_masses": {},
        "anchors_used": 0,
        "likelihood_diagnostics": {"old": marker},
    }


class Likelihood:
    def __init__(self, arm, bank_size):
        self.arm = arm
        self.bank_size = bank_size
        self.last_result = None


def builder(data, selected_count, full_bank_count):
    assert full_bank_count == 4
    return {
        "finite_set": Likelihood("finite_set", selected_count),
        "categorical_control": Likelihood("categorical_control", selected_count),
    }


def diagnostics(likelihood):
    if likelihood.arm == "finite_set":
        return {
            "satellite_detection_probability": np.zeros((1, likelihood.bank_size)),
            "expected_clutter_count": np.zeros(1),
            "raw_peak_count": np.ones(1),
            "unique_peak_count": np.ones(1),
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
        }
    return {"group_count": 1}


def test_routes_only_nonconverged_same_arm_same_bank_incumbents():
    source = [
        trial("finite_set", [0], 10, success=True, objective=100),
        trial("finite_set", [0, 1], 20, success=False, objective=80),
    ]
    original = copy.deepcopy(source)
    calls = []

    def refiner(data, initial, satellites, support, likelihood, **options):
        calls.append((initial.copy(), satellites.copy(), likelihood.arm, options["budget_s"]))
        likelihood.last_result = diagnostics(likelihood)
        return {
            "parameters": initial - 0.5,
            "satellite_indices": satellites,
            "satellite_count": len(satellites),
            "objective": 70.0,
            "initial_objective": 80.0,
            "selection_score": 72.0,
            "success": True,
            "status": "converged",
            "convergence_reason": "test",
            "elapsed_s": 1.0,
        }

    retained, attempts, selection = finite_set_continue.continue_arm_trials(
        object(),
        source,
        "finite_set",
        4,
        budget_s=30.0,
        refiner=refiner,
        likelihood_builder=builder,
    )

    assert len(calls) == 1
    np.testing.assert_array_equal(calls[0][0], original[1]["parameters"])
    np.testing.assert_array_equal(calls[0][1], original[1]["satellite_indices"])
    assert calls[0][2:] == ("finite_set", 30.0)
    assert finite_set_continue.serializable(retained[0]) == finite_set_continue.serializable(
        original[0]
    )
    assert attempts[0]["attempted"] is False
    assert attempts[1]["selected_branch"] == "continuation_candidate"
    assert selection["score_leader"]["satellite_count"] == 2


def test_higher_or_failed_candidate_retains_incumbent_verbatim():
    incumbent = trial("categorical_control", [1, 2], 30, success=False, objective=50)

    def worse(data, initial, satellites, support, likelihood, **options):
        likelihood.last_result = diagnostics(likelihood)
        return {
            "parameters": initial + 10,
            "satellite_indices": satellites,
            "satellite_count": len(satellites),
            "objective": 55.0,
            "initial_objective": 50.0,
            "selection_score": 57.0,
            "success": False,
            "status": "nonconverged",
            "convergence_reason": "worse",
            "elapsed_s": 2.0,
        }

    retained, attempts, _ = finite_set_continue.continue_arm_trials(
        object(),
        [incumbent],
        "categorical_control",
        4,
        refiner=worse,
        likelihood_builder=builder,
    )
    assert finite_set_continue.serializable(retained[0]) == finite_set_continue.serializable(
        incumbent
    )
    assert attempts[0]["selected_branch"] == "verbatim_v1_incumbent"

    def failing(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    retained, attempts, _ = finite_set_continue.continue_arm_trials(
        object(),
        [incumbent],
        "categorical_control",
        4,
        refiner=failing,
        likelihood_builder=builder,
    )
    assert finite_set_continue.serializable(retained[0]) == finite_set_continue.serializable(
        incumbent
    )
    assert attempts[0]["error_type"] == "RuntimeError"


def test_rejects_cross_arm_trial_before_refiner_call():
    source = [trial("finite_set", [0], 10, success=False, objective=10)]
    calls = []

    with pytest.raises(ValueError, match="different arm"):
        finite_set_continue.continue_arm_trials(
            object(),
            source,
            "categorical_control",
            4,
            refiner=lambda *args, **kwargs: calls.append(args),
            likelihood_builder=builder,
        )
    assert calls == []


def test_v1_binding_detects_source_hash_mutation(tmp_path):
    source = tmp_path / "source.py"
    artifact = tmp_path / "expanded.json"
    fit_path = tmp_path / "fit.json"
    source.write_text("stable\n")
    artifact.write_text("stable\n")
    fit_path.write_text("sealed\n")
    receipt = {
        "schema": "finite-set-raw-control-fit/v1",
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "source_hashes_prefit": finite_set_continue.snapshot_files([source]),
        "bound_artifact_hashes_prefit": finite_set_continue.snapshot_files([artifact]),
    }

    finite_set_continue.validate_v1_bindings(receipt, fit_path)
    source.write_text("changed\n")

    with pytest.raises(RuntimeError, match="provenance changed"):
        finite_set_continue.validate_v1_bindings(receipt, fit_path)
