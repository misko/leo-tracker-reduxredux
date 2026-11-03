from types import SimpleNamespace

import numpy as np

import rf_calibration_polish


class LinearJacobian:
    def __init__(self, matrix):
        self.matrix = matrix

    def transpose_multiply(self, weights):
        return self.matrix.T @ weights


class LinearPlan:
    def __init__(self, matrix, visible):
        self.matrix = matrix
        self.visible = visible

    def predict(self, parameters):
        return self.matrix @ parameters, self.visible, LinearJacobian(self.matrix)


class QuadraticPrepared:
    def __init__(self, target, groups=3):
        self.target = np.asarray(target, dtype=float)
        self.group_values = np.arange(groups)

    def evaluate(self, predicted, visible, **options):
        residual = np.asarray(predicted) - self.target
        return {
            "group_values": self.group_values,
            "total_log_likelihood": -0.5 * float(np.sum(residual**2)),
            "prediction_gradient": -residual,
            "satellite_support": np.sum(visible, axis=0, dtype=float),
            "null_support": 0.0,
            "track_unknown_responsibility": np.empty(0),
        }


def _fixture():
    data = SimpleNamespace(numbers=np.arange(2), times=np.arange(3.0))
    satellites = np.array([0, 1])
    initial = np.array([0.2, -0.1, 30.0, 0.4, -20.0, -0.3, 0.2, -0.4])
    matrix = np.arange(48.0).reshape(6, 8) / 100.0
    visible = np.ones(6, dtype=bool)
    design = np.array([[-0.2, 0.0], [0.1, 0.0], [0.0, 0.3]])
    prepared = QuadraticPrepared(np.arange(6.0).reshape(3, 2) / 10.0)
    masses = {}
    active, scales, _ = rf_calibration_polish._specification(2, satellites)
    vector = np.r_[initial[active], [40.0, -30.0]] / scales
    return data, satellites, initial, design, prepared, masses, active, scales, vector, LinearPlan(matrix, visible)


def test_joint_gradient_matches_centered_finite_difference():
    data, satellites, initial, design, prepared, masses, active, scales, vector, plan = _fixture()

    def evaluate(candidate):
        return rf_calibration_polish._evaluate_joint(
            candidate,
            data=data,
            initial_parameters=initial,
            satellites=satellites,
            prepared=prepared,
            masses=masses,
            design=design,
            plan=plan,
            active=active,
            scales=scales,
        )

    value, gradient, *_ = evaluate(vector)
    assert np.isfinite(value)
    numerical = np.empty_like(vector)
    for index in range(len(vector)):
        step = 1e-6 * max(1.0, abs(vector[index]))
        upper = vector.copy()
        lower = vector.copy()
        upper[index] += step
        lower[index] -= step
        numerical[index] = (evaluate(upper)[0] - evaluate(lower)[0]) / (2 * step)
    np.testing.assert_allclose(gradient, numerical, rtol=2e-6, atol=2e-6)


def test_joint_polish_descends_and_respects_tau_and_coefficient_bounds(monkeypatch):
    data, satellites, initial, design, prepared, masses, _, _, _, plan = _fixture()
    source_trial = {
        "satellite_indices": satellites,
        "parameters": initial,
        "coefficients_hz_ghz": np.array([1500.0, -1500.0]),
        "identity_masses": masses,
    }
    monkeypatch.setattr(rf_calibration_polish, "SharedPredictionPlan", lambda *args: plan)
    result = rf_calibration_polish.polish_joint(
        data, source_trial, prepared, design, budget_s=2.0
    )
    assert result["objective"] <= result["initial_objective"]
    assert np.all(np.abs(result["coefficients_hz_ghz"]) <= 1000.0)
    assert np.all(np.abs(result["parameters"][6 + satellites]) <= 3.0)
    assert result["evaluations"] >= 2


def test_fit_polish_uses_sealed_banks_masses_centers_and_no_reference(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "truth" in name or "reference" in name or "known_site" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    data = Data(
        numbers=np.arange(12),
        times=np.arange(2.0),
        measured=np.zeros(2),
        group=np.arange(2),
        receiver=np.array([0, 1]),
        rf=np.array([11.0e9, 11.2e9]),
    )
    source = {
        "rough": {},
        "anchors": [],
        "full_bank": np.arange(12),
        "rf_centers_hz": np.array([11.0e9, 11.2e9]),
        "trials": [
            {
                "satellite_indices": np.arange(count),
                "parameters": np.zeros(18),
                "coefficients_hz_ghz": np.zeros(2),
                "identity_masses": {},
            }
            for count in (4, 8, 12)
        ],
    }
    monkeypatch.setattr(rf_calibration_polish, "frozen_row_weights", lambda data: np.ones(2))
    monkeypatch.setattr(
        rf_calibration_polish,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(rf_calibration_polish, "frozen_identity_masses", lambda *args: {})
    seen = []

    def fake_polish(data, trial, prepared, design, **options):
        seen.append((trial["satellite_indices"].copy(), design.copy()))
        count = len(trial["satellite_indices"])
        return {
            "selection_score": float(20 - count),
            "success": True,
            "satellite_count": count,
        }

    monkeypatch.setattr(rf_calibration_polish, "polish_joint", fake_polish)
    result = rf_calibration_polish.fit_rf_calibration_polish(data, source, bank_budget_s=1.0)
    assert result["selection_resolved"]
    assert [len(item[0]) for item in seen] == [4, 8, 12]
    np.testing.assert_array_equal(result["rf_centers_hz"], source["rf_centers_hz"])
