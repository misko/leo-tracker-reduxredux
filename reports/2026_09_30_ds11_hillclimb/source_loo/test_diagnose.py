from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ds11_source_loo_diagnose_test", HERE / "diagnose.py")
diagnose = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = diagnose
spec.loader.exec_module(diagnose)


class Quadratic:
    def __init__(self, negative_hessian, optimum, constant=0.0):
        self.hessian = np.asarray(negative_hessian, dtype=float)
        self.optimum = np.asarray(optimum, dtype=float)
        self.constant = constant

    def evaluate(self, x, gradient=True):
        displacement = np.asarray(x) - self.optimum
        return {
            "score": float(self.constant - 0.5 * displacement @ self.hessian @ displacement),
            "gradient": -self.hessian @ displacement,
        }


def test_negative_hessian_and_deletion_shift_are_exact_for_quadratics():
    retained_hessian = np.diag([4.0, 3.0, 2.0])
    source_hessian = np.diag([1.0, 0.5, 0.25])
    full_hessian = retained_hessian + source_hessian
    x = np.asarray([0.2, -0.3, 0.1])
    retained_optimum = np.asarray([0.0, 0.0, 0.0])
    # Choose the source optimum so the full gradient is exactly zero at x.
    source_gradient = retained_hessian @ x
    source_optimum = x + np.linalg.solve(source_hessian, source_gradient)
    full = Quadratic(full_hessian, x)
    source = Quadratic(source_hessian, source_optimum)
    full_h = diagnose.finite_negative_hessian(full, x, diagnose.STEPS)
    source_h = diagnose.finite_negative_hessian(source, x, diagnose.STEPS)
    result = diagnose.assess_fold(
        (full_h, full_h), (source_h, source_h), source.evaluate(x)["gradient"],
        full.evaluate(x)["gradient"], x,
    )
    assert result["available"]
    np.testing.assert_allclose(result["retained_negative_hessian"], retained_hessian, atol=1e-9)
    np.testing.assert_allclose(result["estimate"], retained_optimum, atol=1e-9)
    np.testing.assert_allclose(result["optimizer_residual_correction"], 0.0, atol=1e-12)


def test_actual_source_evaluator_decomposes_with_original_weights():
    source = diagnose.load_module("ds11_source_loo_weight_test", diagnose.HILL / "source_balance" / "model.py")

    class FakePrediction:
        def __init__(self, document, config):
            del document, config

        def prediction(self, track, x):
            coefficient = np.asarray(track["coefficient"], dtype=float)
            value = (coefficient @ np.asarray(x)) * np.ones((1, len(track["y"])))
            return value, np.ones(1, dtype=bool)

    tracks = [
        {"track_id": f"t{i}", "y": np.asarray([20.0 + i, 21.0 + i, 19.0 + i]),
         "mask": np.asarray([True, True, False]), "catalogue_size": 1,
         "coefficient": [1.0 + i, 0.5, 0.25]}
        for i in range(4)
    ]
    document = {"tracks": tracks}
    weights = np.asarray([0.25, 0.25, 0.5, 1.0])
    assignments = [{"track_id": track["track_id"]} for track in tracks]
    x = np.asarray([0.1, -0.2, 0.05])
    full = source.SourceBalancedIID(
        [document], {}, weights, assignments, model_factory=FakePrediction
    ).evaluate(x, True)
    selected = [0, 2]
    retained = [1, 3]
    source_part = source.SourceBalancedIID(
        [diagnose.subset_document(document, selected)], {}, weights[selected],
        [assignments[i] for i in selected], model_factory=FakePrediction,
    ).evaluate(x, True)
    retained_part = source.SourceBalancedIID(
        [diagnose.subset_document(document, retained)], {}, weights[retained],
        [assignments[i] for i in retained], model_factory=FakePrediction,
    ).evaluate(x, True)
    np.testing.assert_allclose(full["score"], source_part["score"] + retained_part["score"], atol=1e-10)
    np.testing.assert_allclose(full["gradient"], source_part["gradient"] + retained_part["gradient"], atol=1e-10)
    assert weights[retained].sum() != weights.sum()


def test_gate_preserves_step_halving_pd_condition_and_bounds_failures():
    identity = np.eye(3)
    mismatch = identity * 2.0
    step_failure = diagnose.assess_fold(
        (identity, mismatch), (np.zeros((3, 3)), np.zeros((3, 3))),
        np.zeros(3), np.zeros(3), np.zeros(3),
    )
    assert not step_failure["available"] and "step_halving" in step_failure["failure_reasons"]
    non_pd = diagnose.assess_fold(
        (np.diag([1.0, 1.0, -1.0]), np.diag([1.0, 1.0, -1.0])),
        (np.zeros((3, 3)), np.zeros((3, 3))), np.zeros(3), np.zeros(3), np.zeros(3),
    )
    assert not non_pd["available"] and "not_positive_definite" in non_pd["failure_reasons"]
    out = diagnose.assess_fold(
        (identity, identity), (np.zeros((3, 3)), np.zeros((3, 3))),
        np.asarray([-20.0, 0.0, 0.0]), np.zeros(3), np.zeros(3),
    )
    assert not out["available"] and "bounds" in out["failure_reasons"]


def test_selector_uses_available_rows_and_norad_ties_and_lower_median():
    rows = [
        {"available": True, "en_displacement_km": 3.0, "norad": 30},
        {"available": True, "en_displacement_km": 1.0, "norad": 20},
        {"available": True, "en_displacement_km": 3.0, "norad": 10},
        {"available": False, "en_displacement_km": None, "norad": 40},
    ]
    result = diagnose.select_extremes(rows)
    assert not result["selection_complete"]
    assert result["largest_norad"] is None and result["lower_median_norad"] is None
    assert result["exploratory_available_largest_norad"] == 10
    assert result["exploratory_available_lower_median_norad"] == 10


def test_selector_emits_formal_sources_only_when_all_folds_available():
    rows = [
        {"available": True, "en_displacement_km": 3.0, "norad": 30},
        {"available": True, "en_displacement_km": 1.0, "norad": 20},
        {"available": True, "en_displacement_km": 3.0, "norad": 10},
    ]
    result = diagnose.select_extremes(rows)
    assert result["selection_complete"]
    assert result["largest_norad"] == 10
    assert result["lower_median_norad"] == 10


def test_subset_document_preserves_track_objects_and_ignores_held_reference_fields():
    document = {"session_id": "x", "reference_position_deg": [1, 2],
                "tracks": [{"track_id": "a"}, {"track_id": "b"}]}
    changed = copy.deepcopy(document)
    changed["reference_position_deg"] = [99, 99]
    subset = diagnose.subset_document(changed, [1])
    assert [row["track_id"] for row in subset["tracks"]] == ["b"]
    assert document["tracks"][0]["track_id"] == "a"
