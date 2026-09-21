from pathlib import Path

import numpy as np


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    import study_causal_orbit_phase_prior

    return study_causal_orbit_phase_prior


def test_predictor_classes_do_not_consult_target_values(monkeypatch):
    module = _module(monkeypatch)
    assert module.predict_rate({"name": "zero"}, 4.0) == 0.0
    assert module.predict_rate({"name": "median", "intercept_s_h": -0.2}, 4.0) == -0.2
    assert module.predict_rate({"name": "persistence"}, 4.0) == 4.0
    assert (
        module.predict_rate({"name": "robust_ar1", "intercept_s_h": 0.1, "slope": 0.25}, 4.0) == 1.1
    )


def test_robust_affine_recovers_history_relation_despite_outlier(monkeypatch):
    module = _module(monkeypatch)
    x = np.linspace(-2, 2, 101)
    y = 0.2 + 0.4 * x
    y[50] = 100
    answer = module.robust_affine(x, y)
    np.testing.assert_allclose(answer, [0.2, 0.4], atol=0.01)


def test_causal_sequence_rejects_later_collection_and_epoch(monkeypatch):
    module = _module(monkeypatch)
    records = [
        {"text": "a", "epoch_utc_ns": 10, "first_collected_utc_ns": 11},
        {"text": "b", "epoch_utc_ns": 20, "first_collected_utc_ns": 21},
        {"text": "future collection", "epoch_utc_ns": 22, "first_collected_utc_ns": 31},
        {"text": "future epoch", "epoch_utc_ns": 32, "first_collected_utc_ns": 22},
    ]
    assert [row["text"] for row in module.sequence_before(records, 30)] == ["a", "b"]


def test_candidate_selection_preserves_ridge_hyperparameter(monkeypatch):
    module = _module(monkeypatch)
    candidates = [
        {
            "name": "ridge_features",
            "alpha": 0.1,
            "validation_median_absolute_rate_error_s_h": 2.0,
        },
        {
            "name": "ridge_features",
            "alpha": 10.0,
            "validation_median_absolute_rate_error_s_h": 1.0,
        },
    ]
    assert module.select_candidate(candidates)["alpha"] == 10.0
