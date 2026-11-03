from types import SimpleNamespace

import numpy as np
import pytest
from grouped_likelihood import prepare_grouped_likelihood

import margin_weighted_fit


def _data(measured, group, margin, *, permutation=None):
    count = len(measured)
    data = SimpleNamespace(
        measured=np.asarray(measured, dtype=float),
        group=np.asarray(group, dtype=int),
        margin=np.asarray(margin, dtype=float),
        times=np.arange(count, dtype=float),
        rf=np.full(count, 11.3e9),
        receiver=np.zeros(count, dtype=int),
        channel=np.zeros(count, dtype=int),
    )
    if permutation is not None:
        for name in ("measured", "group", "margin", "times", "rf", "receiver", "channel"):
            setattr(data, name, getattr(data, name)[permutation])
    return data


def _likelihood(data, predicted):
    prepared = prepare_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=margin_weighted_fit.margin_row_weights(data),
    )
    return prepared.evaluate(
        np.asarray(predicted, dtype=float).reshape(-1, 1),
        np.ones((len(data.measured), 1), dtype=bool),
        sigma_hz=200.0,
        satellite_weights=np.ones(1),
        background_mass=0.2,
    )["total_log_likelihood"]


def test_equal_margin_recovers_baseline_grouped_likelihood():
    data = SimpleNamespace(
        measured=np.array([0.0, 0.0, 100.0, 200.0]),
        group=np.array([1, 1, 1, 2]),
        margin=np.full(4, 4.0),
        times=np.array([0.0, 0.0, 1.0, 2.0]),
        rf=np.full(4, 11.3e9),
        receiver=np.zeros(4, dtype=int),
        channel=np.zeros(4, dtype=int),
    )
    predicted = np.array([10.0, 10.0, 20.0, 190.0])
    margin_prepared = prepare_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=margin_weighted_fit.margin_row_weights(data),
    )
    baseline_prepared = prepare_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=margin_weighted_fit.frozen_row_weights(data),
    )
    options = {
        "sigma_hz": 200.0,
        "satellite_weights": np.ones(1),
        "background_mass": 0.2,
    }
    one = margin_prepared.evaluate(predicted[:, None], np.ones((4, 1), bool), **options)
    two = baseline_prepared.evaluate(predicted[:, None], np.ones((4, 1), bool), **options)
    np.testing.assert_allclose(one["log_likelihood"], two["log_likelihood"], atol=1e-12)


def test_duplicate_and_permutation_invariance_uses_feature_maximum_margin():
    original = _data([0.0, 100.0], [7, 7], [2.0, 5.0])
    duplicate = SimpleNamespace(
        measured=np.array([0.0, 0.0, 100.0]),
        group=np.array([7, 7, 7]),
        margin=np.array([2.0, 1.0, 5.0]),
        times=np.array([0.0, 0.0, 1.0]),
        rf=np.full(3, 11.3e9),
        receiver=np.zeros(3, dtype=int),
        channel=np.zeros(3, dtype=int),
    )
    expected = _likelihood(original, [10.0, 90.0])
    actual = _likelihood(duplicate, [10.0, 10.0, 90.0])
    permuted = np.array([2, 0, 1])
    shuffled = SimpleNamespace(
        **{
            name: getattr(duplicate, name)[permuted]
            for name in ("measured", "group", "margin", "times", "rf", "receiver", "channel")
        }
    )
    shuffled_value = _likelihood(shuffled, np.array([90.0, 10.0, 10.0]))
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    np.testing.assert_allclose(shuffled_value, expected, atol=1e-12)


def test_higher_margin_increases_frozen_alternative_prior():
    data = _data([0.0, 100.0], [3, 3], [1.0, 3.0])
    prepared = prepare_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=margin_weighted_fit.margin_row_weights(data),
    )
    np.testing.assert_allclose(np.exp(prepared.log_row_weights), [0.25, 0.75])


@pytest.mark.parametrize("margins", [[0.0], [-1.0], [np.nan], [np.inf]])
def test_margin_weights_reject_nonpositive_or_nonfinite_values(margins):
    data = _data([0.0], [1], margins)
    with pytest.raises(ValueError, match="positive and finite"):
        margin_weighted_fit.margin_row_weights(data)


def test_margin_weighted_fit_uses_no_reference_inputs(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "truth" in name or "reference" in name or "known_site" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    data = Data(
        numbers=np.arange(12),
        measured=np.zeros(2),
        group=np.arange(2),
        margin=np.ones(2),
        times=np.arange(2.0),
        rf=np.full(2, 11.3e9),
        receiver=np.array([0, 1]),
        channel=np.zeros(2),
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
    monkeypatch.setattr(margin_weighted_fit, "candidate_ladder", lambda *args, **kwargs: ladder)
    monkeypatch.setattr(
        margin_weighted_fit,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(margin_weighted_fit, "frozen_identity_masses", lambda *args: {})
    monkeypatch.setattr(margin_weighted_fit, "frozen_row_weights", lambda data: np.ones(2))
    monkeypatch.setattr(margin_weighted_fit, "FixedBankLikelihood", lambda *args: SimpleNamespace(last_result={}))

    def fake_refine(data, initial, satellites, support, likelihood, **options):
        likelihood.last_result = {}
        return {
            "parameters": initial,
            "satellite_weights": np.ones(len(satellites)) / len(satellites),
            "satellite_indices": satellites,
            "satellite_count": len(satellites),
            "selection_score": float(20 - len(satellites)),
            "success": True,
            "status": "converged",
        }

    monkeypatch.setattr(margin_weighted_fit, "refine_gauss_newton", fake_refine)
    result = margin_weighted_fit.fit_margin_weighted(data, source, budget_s=1.0)
    assert result["selection_resolved"]
    assert [trial["satellite_count"] for trial in result["trials"]] == [4, 8, 12]
