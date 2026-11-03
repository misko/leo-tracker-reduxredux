from types import SimpleNamespace

import finite_set_quadratic
import numpy as np
import pytest


class RecordingFiniteSet:
    def __init__(self):
        self.calls = []

    def evaluate(self, predicted, visible, **options):
        self.calls.append(options)
        return {
            "group_values": np.array([2, 5]),
            "total_log_likelihood": -4.0,
            "prediction_gradient": np.ones_like(predicted),
            "prediction_precision": np.full_like(predicted, 0.25),
            "satellite_support": np.array([1.5, 0.5]),
            "expected_clutter_count": np.array([0.2, 0.3]),
            "raw_peak_count": np.array([2, 3]),
            "unique_peak_count": np.array([2, 2]),
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "null_support": 0.5,
        }


def masses(count=2, full=4):
    return {
        "raw_satellite_mass": np.full(count, 0.8 / full),
        "raw_background_mass": 1.0 - count * 0.8 / full,
        "anchor_satellite_mass": np.empty((0, count)),
        "anchor_unknown_mass": np.empty(0),
    }


def test_adapter_translates_existing_quadratic_contract_without_changing_masses():
    finite = RecordingFiniteSet()
    frozen = masses()
    adapter = finite_set_quadratic.FiniteSetQuadraticLikelihoodAdapter(finite, frozen)
    predicted = np.zeros((3, 2))
    result = adapter.evaluate(
        predicted,
        np.ones_like(predicted, dtype=bool),
        sigma_hz=200.0,
        **frozen,
        track_contamination=0.2,
        return_gradient=True,
        return_precision=True,
    )

    call = finite.calls[0]
    np.testing.assert_array_equal(call["satellite_weights"], frozen["raw_satellite_mass"])
    assert call["background_mass"] == frozen["raw_background_mass"]
    assert call["sigma_hz"] == 200.0
    assert call["return_gradient"] is True
    assert call["return_precision"] is True
    assert result["quadratic_mass_contract_translated"] is True
    assert result["track_unknown_responsibility"].size == 0


def test_adapter_rejects_mass_or_anchor_changes():
    frozen = masses()
    adapter = finite_set_quadratic.FiniteSetQuadraticLikelihoodAdapter(
        RecordingFiniteSet(), frozen
    )
    changed = {**frozen, "raw_background_mass": frozen["raw_background_mass"] + 0.1}
    with pytest.raises(ValueError, match="raw_background_mass"):
        adapter.evaluate(
            np.zeros((2, 2)),
            np.ones((2, 2), dtype=bool),
            sigma_hz=200.0,
            **changed,
            track_contamination=0.2,
        )
    anchored = {**frozen, "anchor_unknown_mass": np.array([0.1])}
    adapter = finite_set_quadratic.FiniteSetQuadraticLikelihoodAdapter(
        RecordingFiniteSet(), anchored
    )
    with pytest.raises(ValueError, match="raw-only"):
        adapter.evaluate(
            np.zeros((2, 2)),
            np.ones((2, 2), dtype=bool),
            sigma_hz=200.0,
            **anchored,
            track_contamination=0.2,
        )


def test_empty_serialized_anchor_masses_preserve_raw_only_contract():
    assert finite_set_quadratic._same_numeric([], np.empty((0, 4)))


def source_receipt(data, counts=(1, 2)):
    full_bank = np.arange(max(counts))
    trials = []
    for count in counts:
        bank = np.arange(count)
        raw_masses = finite_set_quadratic.frozen_raw_masses(count, len(full_bank))
        trials.append(
            {
                "arm": "finite_set",
                "satellite_indices": bank,
                "satellite_count": count,
                "parameters": np.zeros(6 + len(data.numbers)),
                "objective": float(100 - count),
                "selection_score": float(105 - count),
                "success": True,
                "status": "converged",
                "convergence_reason": "source",
                "raw_masses": raw_masses,
                "per_satellite_probability": 0.8 / len(full_bank),
            }
        )
    return {
        "schema": "finite-set-raw-control-continuation/v1",
        "stage": "finite_set_raw_control_continuation",
        "unit": {"unit_id": "DS10-S01"},
        "reference_read_before_seal": False,
        "v1_evaluation_read": False,
        "evaluation_written": False,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "fit": {
            "full_bank": full_bank,
            "finite_set_trials": trials,
            "anchors_used_by_either_arm": 0,
            "finite_set_clutter_rate": 2.0,
            "geometry": data.geometry_receipt,
        },
    }


def test_full_ladder_uses_only_same_bank_finite_set_seeds_and_retains_linear_incumbents():
    source_data = SimpleNamespace(
        times=np.array([1.0, 1.002, 2.0, 2.004]),
        measured=np.array([10.0, 20.0, 30.0, 40.0]),
        rf=np.array([11.0, 11.0, 12.0, 12.0]),
        receiver=np.array([0, 0, 1, 1]),
        group=np.array([5, 5, 8, 8]),
        channel=np.ones(4, dtype=int),
        numbers=np.arange(2),
    )
    data = finite_set_quadratic.GroupMedianGeometryData(source_data)
    source = source_receipt(data)
    calls = []

    class Prepared:
        pass

    def fake_trial(data, source_trial, prepared, *, budget_s):
        count = source_trial["satellite_count"]
        calls.append(
            {
                "count": count,
                "parameters": source_trial["parameters"].copy(),
                "budget_s": budget_s,
                "identity_masses": source_trial["identity_masses"],
            }
        )
        prepared.last_result = {
            "group_values": np.array([5, 8]),
            "satellite_support": np.ones(count),
            "expected_clutter_count": np.ones(2),
            "raw_peak_count": np.array([2, 2]),
            "unique_peak_count": np.array([2, 2]),
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
        }
        source_objective = source_trial["objective"]
        return {
            "parameters": source_trial["parameters"].copy(),
            "satellite_indices": source_trial["satellite_indices"].copy(),
            "satellite_count": count,
            "objective": source_objective - count,
            "initial_objective": source_objective,
            "selection_score": source_trial["selection_score"] + 10.0,
            "success": True,
            "status": "converged",
            "convergence_reason": "test",
            "curvature_coefficients_hz": np.zeros(2),
        }

    def finite_builder(prepared, detection_probability, clutter_rate):
        wrapper = Prepared()
        wrapper.evaluate = lambda *args, **kwargs: None
        return wrapper

    original = finite_set_quadratic.FiniteSetLikelihoodAdapter
    finite_set_quadratic.FiniteSetLikelihoodAdapter = finite_builder
    try:
        result = finite_set_quadratic.fit_finite_set_quadratic(
            data,
            source,
            budget_s=7.0,
            trial_fitter=fake_trial,
            likelihood_preparer=lambda *args: object(),
        )
    finally:
        finite_set_quadratic.FiniteSetLikelihoodAdapter = original

    assert [call["count"] for call in calls] == [1, 2]
    assert all(call["budget_s"] == 7.0 for call in calls)
    assert result["same_bank_finite_set_v2_seed_only"] is True
    assert result["zero_curvature_initialization"] is True
    assert result["baseline_linear_v2_incumbent_retained"] is True
    assert result["combined_penalized_selection"]["score_leader"]["model"] == (
        "finite_set_linear_v2"
    )
    assert [row["model"] for row in result["per_bank_penalized_incumbents"]] == [
        "finite_set_linear_v2",
        "finite_set_linear_v2",
    ]


def test_fit_reads_no_reference_or_truth_inputs(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "truth" in name or "reference" in name or "known" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    raw = Data(
        times=np.array([1.0, 1.0]),
        measured=np.array([10.0, 20.0]),
        rf=np.array([11.0, 11.0]),
        receiver=np.array([0, 0]),
        group=np.array([5, 5]),
        channel=np.ones(2, dtype=int),
        numbers=np.arange(1),
    )
    data = finite_set_quadratic.GroupMedianGeometryData(raw)
    source = source_receipt(data, counts=(1,))

    class Adapter:
        last_result = {
            "group_values": np.array([5]),
            "satellite_support": np.ones(1),
            "expected_clutter_count": np.ones(1),
            "raw_peak_count": np.ones(1),
            "unique_peak_count": np.ones(1),
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
        }

    monkeypatch.setattr(
        finite_set_quadratic,
        "FiniteSetLikelihoodAdapter",
        lambda *args, **kwargs: Adapter(),
    )

    def fake_trial(data, source_trial, prepared, **options):
        prepared.last_result = prepared.finite_set.last_result
        return {
            "parameters": source_trial["parameters"],
            "satellite_indices": source_trial["satellite_indices"],
            "satellite_count": 1,
            "objective": 98.0,
            "initial_objective": 99.0,
            "selection_score": 104.0,
            "success": True,
            "status": "converged",
            "convergence_reason": "test",
        }

    result = finite_set_quadratic.fit_finite_set_quadratic(
        data,
        source,
        budget_s=1.0,
        trial_fitter=fake_trial,
        likelihood_preparer=lambda *args: object(),
    )
    assert result["anchors_used"] == 0
    assert result["quadratic_trials"][0]["zero_curvature_initialization"] is True


def test_source_validation_rejects_reference_tainted_or_other_arm():
    data = SimpleNamespace(geometry_receipt={}, numbers=np.arange(1))
    source = source_receipt(data, counts=(1,))
    source["reference_read_before_seal"] = True
    with pytest.raises(ValueError, match="sealed before reference"):
        finite_set_quadratic._validate_source(source, "DS10-S01")
    source["reference_read_before_seal"] = False
    source["fit"]["finite_set_trials"][0]["arm"] = "categorical_control"
    with pytest.raises(ValueError, match="another arm"):
        finite_set_quadratic._validate_source(source, "DS10-S01")
