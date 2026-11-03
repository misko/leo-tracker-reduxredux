from types import SimpleNamespace

import numpy as np

import quadratic_drift_fit


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
    def __init__(self, target):
        self.target = np.asarray(target, dtype=float)
        self.group_values = np.arange(len(target))

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


def _gradient_fixture():
    data = SimpleNamespace(
        numbers=np.arange(2),
        times=np.array([0.0, 150.0, 300.0]),
        receiver=np.array([0, 1, 0]),
        reference_time_s=150.0,
    )
    satellites = np.array([0, 1])
    initial = np.array([0.2, -0.1, 30.0, 0.4, -20.0, -0.3, 0.2, -0.4])
    matrix = np.arange(48.0).reshape(6, 8) / 100.0
    visible = np.ones(6, dtype=bool)
    prepared = QuadraticPrepared(np.arange(6.0).reshape(3, 2) / 10.0)
    active, scales, _, _ = quadratic_drift_fit._specification(2, satellites)
    vector = np.r_[initial[active], [40.0, -30.0]] / scales
    return data, satellites, initial, prepared, active, scales, vector, LinearPlan(matrix, visible)


def test_joint_gradient_matches_centered_finite_difference():
    data, satellites, initial, prepared, active, scales, vector, plan = _gradient_fixture()
    design = quadratic_drift_fit.quadratic_time_basis(data)

    def evaluate(candidate):
        return quadratic_drift_fit._evaluate_joint(
            candidate,
            data=data,
            initial_parameters=initial,
            satellites=satellites,
            prepared=prepared,
            masses={},
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


def test_centered_basis_has_fixed_capture_gauge_and_no_rf_dependency():
    data = SimpleNamespace(
        times=np.array([0.0, 150.0, 300.0]),
        receiver=np.array([0, 0, 1]),
        rf=np.array([10e9, 11e9, 12e9]),
        reference_time_s=150.0,
    )
    design = quadratic_drift_fit.quadratic_time_basis(data)
    np.testing.assert_allclose(design[:, 0], [2 / 3, -1 / 3, 0.0])
    np.testing.assert_allclose(design[:, 1], [0.0, 0.0, 2 / 3])
    changed_rf = SimpleNamespace(**vars(data))
    changed_rf.rf = data.rf * 100
    np.testing.assert_array_equal(
        quadratic_drift_fit.quadratic_time_basis(changed_rf), design
    )


def test_endpoint_constraints_apply_to_total_instantaneous_slope():
    satellites = np.array([0])
    active, scales, bounds, constraint = quadratic_drift_fit._specification(1, satellites)
    parameters = np.zeros(7)
    parameters[3] = 46.0
    parameters[5] = -44.0
    coefficients = np.array([300.0, -400.0])
    vector = np.r_[parameters[active], coefficients] / scales
    expected = quadratic_drift_fit.endpoint_slopes(parameters, coefficients).ravel()
    np.testing.assert_allclose(constraint @ vector, expected)
    assert quadratic_drift_fit._constraint_violation(vector, bounds, constraint) == 0.0
    coefficients[0] = 500.0
    vector = np.r_[parameters[active], coefficients] / scales
    assert quadratic_drift_fit._constraint_violation(vector, bounds, constraint) > 0.0


def test_quadratic_fit_uses_no_reference_inputs(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "truth" in name or "reference" in name or "known_site" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    data = Data(
        numbers=np.arange(12),
        measured=np.zeros(2),
        group=np.arange(2),
        times=np.array([0.0, 300.0]),
        receiver=np.array([0, 1]),
        channel=np.zeros(2),
        rf=np.full(2, 11.3e9),
        child_sessions=("scan",),
    )
    ladder = [(np.arange(count), np.ones(count)) for count in (4, 8, 12)]
    source = {
        "rough": {"assignments": []},
        "anchors": [],
        "full_bank": np.arange(12),
        "trials": [
            {
                "satellite_indices": satellites,
                "parameters": np.zeros(18),
                "identity_masses": {},
                "objective": 1.0,
                "status": "converged",
            }
            for satellites, _ in ladder
        ],
    }
    monkeypatch.setattr(quadratic_drift_fit, "candidate_ladder", lambda *args, **kwargs: ladder)
    monkeypatch.setattr(quadratic_drift_fit, "frozen_row_weights", lambda data: np.ones(2))
    monkeypatch.setattr(
        quadratic_drift_fit,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(quadratic_drift_fit, "frozen_identity_masses", lambda *args: {})

    def fake_trial(data, source_trial, prepared, **options):
        count = len(source_trial["satellite_indices"])
        return {
            "satellite_count": count,
            "selection_score": float(20 - count),
            "success": True,
        }

    monkeypatch.setattr(quadratic_drift_fit, "fit_quadratic_trial", fake_trial)
    result = quadratic_drift_fit.fit_quadratic_drift(data, source, budget_s=1.0)
    assert result["selection_resolved"]
    assert [trial["satellite_count"] for trial in result["trials"]] == [4, 8, 12]
