from types import SimpleNamespace

import numpy as np
from track_likelihood import prepare_track_grouped_likelihood

import rf_calibration_fit


def test_rf_design_is_centered_per_receiver_with_expected_sign():
    data = SimpleNamespace(
        receiver=np.array([0, 0, 0, 1, 1, 1]),
        rf=np.array([10e9, 11e9, 12e9, 20e9, 21e9, 22e9]),
    )
    centers = rf_calibration_fit.receiver_rf_centers(data)
    design = rf_calibration_fit.receiver_rf_design(data, centers)
    np.testing.assert_array_equal(centers, [11e9, 21e9])
    np.testing.assert_array_equal(design[:, 0], [-1.0, 0.0, 1.0, 0.0, 0.0, 0.0])
    np.testing.assert_array_equal(design[:, 1], [0.0, 0.0, 0.0, -1.0, 0.0, 1.0])
    np.testing.assert_array_equal(
        rf_calibration_fit.rf_correction_hz(design, [100.0, -50.0]),
        [-100.0, 0.0, 100.0, 50.0, 0.0, -50.0],
    )


def test_coefficient_likelihood_is_invariant_to_duplicate_alternatives():
    masses = {
        "raw_satellite_mass": np.array([0.8]),
        "raw_background_mass": 0.2,
        "anchor_satellite_mass": np.empty((0, 1)),
        "anchor_unknown_mass": np.empty(0),
    }
    single = prepare_track_grouped_likelihood(
        np.array([25.0]), np.array([7]), row_weights=np.array([1.0]), anchors=[]
    )
    duplicate = prepare_track_grouped_likelihood(
        np.array([25.0, 25.0]),
        np.array([7, 7]),
        row_weights=np.array([0.5, 0.5]),
        anchors=[],
    )
    one = rf_calibration_fit._coefficient_value_gradient(
        np.zeros((1, 1)),
        np.ones((1, 1), dtype=bool),
        np.array([[1.0, 0.0]]),
        np.array([10.0, 0.0]),
        single,
        masses,
    )
    two = rf_calibration_fit._coefficient_value_gradient(
        np.zeros((2, 1)),
        np.ones((2, 1), dtype=bool),
        np.array([[1.0, 0.0], [1.0, 0.0]]),
        np.array([10.0, 0.0]),
        duplicate,
        masses,
    )
    np.testing.assert_allclose(one[0], two[0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(one[1], two[1], rtol=0, atol=1e-12)


class QuadraticPrepared:
    def __init__(self, target):
        self.target = np.asarray(target)

    def evaluate(self, predicted, visible, **options):
        residual = predicted - self.target
        return {
            "total_log_likelihood": -0.5 * float(np.sum(residual**2)),
            "prediction_gradient": -residual,
        }


def test_coefficient_fit_has_correct_sign_prior_and_bounds():
    fitted = rf_calibration_fit.fit_coefficients(
        np.zeros((2, 1)),
        np.ones((2, 1), dtype=bool),
        np.array([[1.0, 0.0], [0.0, 1.0]]),
        np.zeros(2),
        QuadraticPrepared(np.array([[5000.0], [-5000.0]])),
        {},
        budget_s=2.0,
    )
    np.testing.assert_allclose(fitted["coefficients_hz_ghz"], [1000.0, -1000.0])
    assert fitted["coefficient_prior"] == 16.0
    assert fitted["success"]


def test_rf_calibration_uses_no_reference_inputs(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "truth" in name or "reference" in name or "known_site" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    data = Data(
        numbers=np.arange(12),
        receiver=np.array([0, 1]),
        rf=np.array([10e9, 20e9]),
        measured=np.zeros(2),
        group=np.array([1, 2]),
        times=np.array([0.0, 1.0]),
        child_sessions=("scan",),
        provenance={"reference_truth_read": False},
    )
    ladder = [(np.arange(4), np.ones(4)), (np.arange(8), np.ones(8)), (np.arange(12), np.ones(12))]
    proposal = {
        "rough": {"assignments": []},
        "full_bank": np.arange(12),
        "anchors": [],
        "trials": [
            {
                "satellite_indices": satellites,
                "identity_masses": {},
            }
            for satellites, _ in ladder
        ],
    }
    seed = {
        "trials": [
            {"satellite_indices": satellites, "parameters": np.zeros(18)}
            for satellites, _ in ladder
        ]
    }
    monkeypatch.setattr(rf_calibration_fit, "candidate_ladder", lambda *args, **kwargs: ladder)
    monkeypatch.setattr(rf_calibration_fit, "frozen_row_weights", lambda data: np.ones(2))
    monkeypatch.setattr(
        rf_calibration_fit,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: SimpleNamespace(group_values=np.array([1, 2])),
    )
    monkeypatch.setattr(
        rf_calibration_fit,
        "frozen_identity_masses",
        lambda *args: {},
    )
    monkeypatch.setattr(
        rf_calibration_fit,
        "refine_gauss_newton",
        lambda data, initial, satellites, support, likelihood, **options: {
            "parameters": initial,
            "success": True,
            "status": "converged",
            "convergence_reason": "synthetic",
            "objective": 10.0,
            "evaluations": 1,
            "iterations": 1,
            "damping": 1.0,
        },
    )
    monkeypatch.setattr(
        rf_calibration_fit,
        "SharedPredictionPlan",
        lambda data, satellites: SimpleNamespace(
            predict=lambda parameters: (
                np.zeros(2 * len(satellites)),
                np.ones(2 * len(satellites), dtype=bool),
                None,
            )
        ),
    )
    monkeypatch.setattr(
        rf_calibration_fit,
        "fit_coefficients",
        lambda *args, **kwargs: {
            "coefficients_hz_ghz": np.zeros(2),
            "success": True,
            "status": "converged",
            "message": "synthetic",
            "projected_gradient_inf_norm": 0.0,
            "evaluations": 1,
            "iterations": 1,
        },
    )
    monkeypatch.setattr(
        rf_calibration_fit,
        "_evaluate_combined",
        lambda *args, **kwargs: {
            "objective": 10.0,
            "coefficient_prior": 0.0,
            "tau_prior": 0.0,
            "total_log_likelihood": -10.0,
            "satellite_support": np.zeros(len(args[3])),
            "null_support": 2.0,
        },
    )
    monkeypatch.setattr(rf_calibration_fit, "FixedBankLikelihood", lambda *args: object())

    result = rf_calibration_fit.fit_rf_calibration(
        data, proposal, seed, case_budget_s=10.0, max_cycles=1
    )
    assert len(result["trials"]) == 3
    assert data.provenance["reference_truth_read"] is False
