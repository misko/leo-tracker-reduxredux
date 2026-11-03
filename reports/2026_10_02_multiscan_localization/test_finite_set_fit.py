from types import SimpleNamespace

import finite_set_fit
import numpy as np
import pytest


def geometry_data():
    return SimpleNamespace(
        times=np.array([1.0, 1.002, 2.0, 2.004]),
        measured=np.array([10.0, 20.0, 30.0, 40.0]),
        rf=np.array([11.0, 11.0, 12.0, 12.0]),
        receiver=np.array([0, 0, 1, 1]),
        group=np.array([5, 5, 8, 8]),
        channel=np.ones(4, dtype=int),
        numbers=np.array([101, 202, 303, 404]),
    )


def test_group_median_geometry_is_candidate_independent_and_shared():
    source = geometry_data()
    adapted = finite_set_fit.GroupMedianGeometryData(source)

    np.testing.assert_allclose(adapted.times, [1.001, 1.001, 2.002, 2.002])
    np.testing.assert_array_equal(adapted.rf, source.rf)
    np.testing.assert_array_equal(adapted.receiver, source.receiver)
    np.testing.assert_array_equal(adapted.measured, source.measured)
    assert adapted.geometry_receipt["unequal_source_time_group_count"] == 2
    assert adapted.geometry_receipt["applied_to_both_arms"] is True
    assert adapted.geometry_receipt["measurements_changed"] is False


def test_geometry_rejects_peak_dependent_rf_or_receiver():
    source = geometry_data()
    source.rf[1] = 99.0
    with pytest.raises(ValueError, match="unequal RF, receiver, or channel"):
        finite_set_fit.GroupMedianGeometryData(source)


def test_adapted_geometry_produces_group_constant_predictions(monkeypatch):
    data = finite_set_fit.GroupMedianGeometryData(geometry_data())

    class Plan:
        def __init__(self, data, satellites):
            self.data = data
            self.satellites = np.asarray(satellites)

        def predict(self, parameters):
            prediction = self.data.times[:, None] + self.satellites[None, :] * 100.0
            visible = np.ones_like(prediction, dtype=bool)
            return prediction.ravel(), visible.ravel(), None

    monkeypatch.setattr(finite_set_fit, "SharedPredictionPlan", Plan)
    receipt = finite_set_fit.prediction_geometry_preflight(
        data,
        np.zeros(10),
        np.array([0, 1]),
    )

    assert receipt["maximum_group_prediction_circular_spread_hz"] == 0.0
    assert receipt["conflicting_group_visibility_count"] == 0
    assert receipt["groupwise_prediction_contract_satisfied"] is True


class RecordingPrepared:
    def __init__(self):
        self.options = None

    def evaluate(self, predicted, visible, **options):
        self.options = options
        return {
            "group_values": np.array([1, 2]),
            "total_log_likelihood": -3.0,
            "prediction_gradient": np.full_like(predicted, 2.5),
            "prediction_precision": np.full_like(predicted, 0.25),
            "satellite_support": np.ones(predicted.shape[1]),
            "expected_clutter_count": np.array([0.2, 0.3]),
        }


def test_finite_set_adapter_preserves_gradient_contract_and_detection_scale():
    prepared = RecordingPrepared()
    adapter = finite_set_fit.FiniteSetLikelihoodAdapter(
        prepared,
        detection_probability=0.8 / 20,
        clutter_rate=2.0,
    )
    predicted = np.zeros((4, 3))
    result = adapter.evaluate(
        predicted,
        np.ones_like(predicted, dtype=bool),
        sigma_hz=200.0,
        satellite_weights=np.ones(3) / 3,
        background_mass=0.2,
        return_gradient=True,
        return_precision=True,
    )

    np.testing.assert_array_equal(result["prediction_gradient"], 2.5)
    np.testing.assert_array_equal(result["prediction_precision"], 0.25)
    np.testing.assert_allclose(prepared.options["detection_probability"], 0.04)
    assert prepared.options["clutter_rate"] == 2.0
    assert prepared.options["implementation"] == "batched"
    assert result["null_support"] == 0.5


def test_matched_control_is_raw_only_and_uses_full_bank_mass_scale():
    data = finite_set_fit.GroupMedianGeometryData(geometry_data())
    arms = finite_set_fit.build_likelihood_arms(data, selected_count=2, full_bank_count=4)

    assert arms["control_anchor_count"] == 0
    assert arms["categorical_control"].prepared.anchor_count == 0
    np.testing.assert_allclose(arms["masses"]["raw_satellite_mass"], [0.2, 0.2])
    assert arms["masses"]["raw_background_mass"] == pytest.approx(0.6)
    assert arms["detection_probability"] == pytest.approx(0.2)


def test_both_arms_receive_identical_seed_and_budget(monkeypatch):
    data = finite_set_fit.GroupMedianGeometryData(geometry_data())
    full_bank = [0, 1]
    small_parameters = np.arange(10.0)
    full_parameters = np.arange(10.0) + 100.0
    expanded = {
        "fit": {
            "full_bank": full_bank,
            "anchors": [{"groups": [5]}],
            "trials": [
                {
                    "satellite_indices": [0],
                    "parameters": small_parameters,
                    "identity_masses": finite_set_fit.frozen_raw_masses(1, len(full_bank)),
                },
                {
                    "satellite_indices": [0, 1],
                    "parameters": full_parameters,
                    "identity_masses": finite_set_fit.frozen_raw_masses(2, len(full_bank)),
                },
            ],
        }
    }
    calls = []

    def refiner(data, initial, satellites, support, likelihood, **options):
        calls.append((initial.copy(), options["budget_s"], likelihood))
        satellite_count = len(satellites)
        likelihood.last_result = (
            {
                "satellite_detection_probability": np.zeros((2, satellite_count)),
                "expected_clutter_count": np.zeros(2),
                "raw_peak_count": np.ones(2),
                "unique_peak_count": np.ones(2),
                "conditioned_nonempty": True,
                "density_convention": "unlabeled_finite_set",
            }
            if isinstance(likelihood, finite_set_fit.FiniteSetLikelihoodAdapter)
            else {"group_count": 2}
        )
        return {
            "parameters": initial.copy(),
            "satellite_indices": np.asarray(satellites),
            "satellite_count": len(satellites),
            "selection_score": 1.0,
            "objective": 0.0,
            "success": True,
        }

    fitted = finite_set_fit.fit_raw_only_controls(
        data,
        expanded,
        budget_s_per_arm=7.0,
        refiner=refiner,
        prediction_preflight=lambda *args: {"groupwise_prediction_contract_satisfied": True},
    )

    assert len(calls) == 4
    np.testing.assert_array_equal(calls[0][0], calls[1][0])
    np.testing.assert_array_equal(calls[0][0], small_parameters)
    np.testing.assert_array_equal(calls[2][0], calls[3][0])
    np.testing.assert_array_equal(calls[2][0], full_parameters)
    assert all(call[1] == 7.0 for call in calls)
    assert fitted["anchors_used_by_either_arm"] == 0
    assert fitted["expanded_anchor_count_ignored"] == 1
    assert fitted["fitted_bank_sizes"] == [1, 2]
    assert fitted["all_expanded_ladder_banks_fitted_in_both_arms"] is True
    assert fitted["full_bank_trial_used_only_for_prediction_geometry_preflight"] is True
    assert fitted["cross_arm_objective_ranking_performed"] is False
    assert "Frozen heuristic lambda=2" in fitted["finite_set_clutter_rate_semantics"]


def test_prefit_snapshot_detects_dependency_mutation(tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.json"
    first.write_text("stable\n")
    second.write_text('{"stable": true}\n')
    snapshot = finite_set_fit.snapshot_files([first, second])

    finite_set_fit.assert_snapshot_unchanged(snapshot)
    first.write_text("changed\n")

    with pytest.raises(RuntimeError, match="provenance changed before seal"):
        finite_set_fit.assert_snapshot_unchanged(snapshot)
