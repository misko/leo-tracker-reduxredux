from types import SimpleNamespace

import numpy as np
import pytest
import synthetic_recovery


class LayoutData:
    def __init__(self):
        self.times = np.arange(6, dtype=float)
        self.measured = np.full(6, 123.0)
        self.group = np.array([0, 0, 1, 1, 2, 2])
        self.rf = np.full(6, 11.0e9)
        self.receiver = np.array([0, 0, 1, 1, 0, 0])
        self.channel = np.ones(6, dtype=int)
        self.numbers = np.array([101, 202, 303])

    def predict(self, parameters, rows=None, satellites=None):
        if rows is None:
            rows = np.arange(len(self.times))[:, None]
            satellites = np.arange(len(self.numbers))[None, :]
        rows = np.asarray(rows)
        satellites = np.asarray(satellites)
        predicted = 1000.0 * satellites + 10.0 * rows + parameters[6:][satellites]
        return predicted, np.ones_like(predicted, dtype=bool)


def fixture_inputs():
    data = LayoutData()
    parameters = np.zeros(9)
    satellites = np.array([0, 1, 2])
    masses = {
        "raw_satellite_mass": np.array([0.0, 0.0, 0.8]),
        "raw_background_mass": 0.2,
        "anchor_satellite_mass": np.array([[0.0, 0.8, 0.0]]),
        "anchor_unknown_mass": np.array([0.2]),
    }
    anchors = [np.array([0, 1])]
    return data, parameters, satellites, masses, anchors


def test_conditional_realization_uses_one_alternative_and_one_anchor_identity():
    data, parameters, satellites, masses, anchors = fixture_inputs()
    original = data.measured.copy()
    realization = synthetic_recovery.conditional_noiseless_realization(
        data,
        parameters,
        satellites,
        masses,
        anchors,
        row_weights=np.ones(6),
        seed=17,
    )

    np.testing.assert_array_equal(data.measured, original)
    assert realization.data.source is data
    assert realization.anchor_identities.tolist() == [1]
    assert realization.selected_satellites.tolist() == [1, 1, 2]
    assert len(np.unique(realization.selected_rows)) == 3
    for group_index, selected_row in enumerate(realization.selected_rows):
        rows = np.flatnonzero(data.group == realization.group_values[group_index])
        assert selected_row in rows
        candidate = realization.selected_satellites[group_index]
        predicted, _ = data.predict(
            parameters,
            rows=np.array([selected_row]),
            satellites=np.array([satellites[candidate]]),
        )
        residual = (
            realization.data.measured[selected_row]
            - predicted[0]
            + synthetic_recovery.DEFAULT_ALIAS_HZ / 2
        ) % synthetic_recovery.DEFAULT_ALIAS_HZ - synthetic_recovery.DEFAULT_ALIAS_HZ / 2
        assert abs(residual) < 1e-10
    assert realization.metadata["row_alternatives_are_categorical"] is True
    assert realization.metadata["unconditional_generative_claim"] is False
    assert realization.metadata["signal_group_count"] == 3


def test_invisible_component_becomes_explicit_null_only_group():
    data, parameters, satellites, masses, anchors = fixture_inputs()
    original_predict = data.predict

    def partly_invisible(parameters, rows=None, satellites=None):
        predicted, visible = original_predict(parameters, rows, satellites)
        rows = np.asarray(rows)
        satellites = np.asarray(satellites)
        visible = visible & ~((rows >= 4) & (satellites == 2))
        return predicted, visible

    data.predict = partly_invisible
    realization = synthetic_recovery.conditional_noiseless_realization(
        data,
        parameters,
        satellites,
        masses,
        anchors,
        row_weights=np.ones(6),
        seed=3,
    )

    assert realization.selected_rows[-1] == -1
    assert realization.selected_satellites[-1] == -1
    assert realization.metadata["null_only_group_count"] == 1


def test_recovery_result_is_measured_instead_of_assumed(monkeypatch):
    data, parameters, satellites, masses, anchors = fixture_inputs()
    realization = synthetic_recovery.conditional_noiseless_realization(
        data,
        parameters,
        satellites,
        masses,
        anchors,
        row_weights=np.ones(6),
        seed=7,
    )

    def failed_refiner(data, initial, satellites, support, likelihood, **options):
        fitted = initial.copy()
        fitted[:2] += [2.0, -1.0]
        return {
            "parameters": fitted,
            "objective": 1.0,
            "initial_objective": 2.0,
            "success": True,
            "elapsed_s": 0.0,
        }

    monkeypatch.setattr(
        synthetic_recovery,
        "timing_prior_profile",
        lambda *args, **kwargs: {
            "profile": [],
            "timing_prior_shifts_generating_map_along_shrink_path": False,
        },
    )
    result = synthetic_recovery.run_recovery_audit(
        realization,
        parameters,
        satellites,
        masses,
        anchors,
        np.ones(6),
        offsets_km=((0.1, 0.0), (-0.1, 0.1)),
        per_start_budget_s=1.0,
        total_fit_budget_s=2.0,
        recovery_tolerance_km=0.2,
        refiner=failed_refiner,
    )

    assert result["completed_trial_count"] == 2
    assert result["recovered_trial_count"] == 0
    assert result["all_completed_positions_recovered"] is False
    assert result["recovery_was_measured_not_assumed"] is True
    assert all(not trial["position_recovered"] for trial in result["trials"])


def test_timing_prior_shift_requires_likelihood_tradeoff(monkeypatch):
    data, parameters, satellites, masses, anchors = fixture_inputs()
    parameters[6:] = [1.0, -2.0, 0.5]
    prepared = SimpleNamespace()
    likelihood = SimpleNamespace()
    objectives = {
        1.0: {"likelihood_nll": 10.0, "timing_prior": 2.625, "objective": 12.625},
        0.9: {"likelihood_nll": 10.1, "timing_prior": 2.12625, "objective": 12.22625},
    }

    def objective(data, candidate, satellites, likelihood, tau_sigma_s=1.0):
        scale = round(candidate[6] / parameters[6], 1)
        return {**objectives[scale], "tau_l2_s": float(np.linalg.norm(candidate[6:]))}

    monkeypatch.setattr(synthetic_recovery, "objective_components", objective)
    result = synthetic_recovery.timing_prior_profile(
        data, parameters, satellites, likelihood, scales=(1.0, 0.9)
    )

    assert prepared is not likelihood
    assert result["timing_prior_shifts_generating_map_along_shrink_path"] is True


def test_recovery_budget_is_bounded_and_requires_several_offsets():
    data, parameters, satellites, masses, anchors = fixture_inputs()
    realization = synthetic_recovery.conditional_noiseless_realization(
        data,
        parameters,
        satellites,
        masses,
        anchors,
        row_weights=np.ones(6),
    )
    with pytest.raises(ValueError, match="several"):
        synthetic_recovery.run_recovery_audit(
            realization,
            parameters,
            satellites,
            masses,
            anchors,
            np.ones(6),
            offsets_km=((0.1, 0.0),),
        )
    with pytest.raises(ValueError, match="at most 60"):
        synthetic_recovery.run_recovery_audit(
            realization,
            parameters,
            satellites,
            masses,
            anchors,
            np.ones(6),
            total_fit_budget_s=61,
        )
