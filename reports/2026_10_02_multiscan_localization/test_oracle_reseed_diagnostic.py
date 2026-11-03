from types import SimpleNamespace

import numpy as np
import pytest

import oracle_reseed_diagnostic


def receipts():
    satellite_indices = np.arange(12)
    parameters = np.zeros(20)
    source = {
        "fit": {
            "score_leader": {
                "satellite_indices": satellite_indices,
                "parameters": parameters.copy(),
                "identity_masses": {"frozen": True},
            },
            "anchors": [{"groups": np.array([1, 2])}],
        }
    }
    zoom_parameters = parameters.copy()
    zoom_parameters[2] = 11.0
    zoom = {
        "fit": {
            "selected": {
                "fit": {
                    "parameters": zoom_parameters,
                    "satellite_indices": satellite_indices,
                    "objective": 90.0,
                }
            }
        }
    }
    prior_parameters = parameters.copy()
    prior_parameters[2] = 22.0
    prior = {
        "oracle_position_km": np.array([3.0, -4.0]),
        "selected_satellite_indices": satellite_indices,
        "fixed_objective": 100.0,
        "fixed_fit": {"parameters": prior_parameters},
    }
    return source, zoom, prior


def test_oracle_reseeds_use_two_sealed_starts_and_only_fixed_position(monkeypatch):
    source, zoom, prior = receipts()
    data = SimpleNamespace(
        numbers=np.arange(14),
        measured=np.zeros(2),
        group=np.array([1, 2]),
        times=np.arange(2),
        rf=np.ones(2),
        receiver=np.zeros(2),
        channel=np.zeros(2),
    )
    prepared = object()
    observed = []

    monkeypatch.setattr(
        oracle_reseed_diagnostic,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: prepared,
    )
    monkeypatch.setattr(
        oracle_reseed_diagnostic,
        "frozen_row_weights",
        lambda data: np.ones(len(data.times)),
    )
    monkeypatch.setattr(
        oracle_reseed_diagnostic,
        "FixedBankLikelihood",
        lambda current_prepared, masses: SimpleNamespace(
            prepared=current_prepared, masses=masses
        ),
    )

    def fake_refine(data_arg, initial, satellites, support, likelihood, **options):
        observed.append((initial.copy(), satellites.copy(), options.copy(), likelihood))
        parameters = initial.copy()
        parameters[:2] = options["fixed_position_km"]
        return {"parameters": parameters, "objective": float(initial[2])}

    monkeypatch.setattr(oracle_reseed_diagnostic, "refine_gauss_newton", fake_refine)
    monkeypatch.setattr(
        oracle_reseed_diagnostic,
        "_evaluate_diagnostics",
        lambda data, prepared, masses, satellites, parameters: {
            "objective": float(parameters[2]),
            "fixed_position_gradient": np.zeros(2),
        },
    )

    result = oracle_reseed_diagnostic.fit_oracle_reseeds(
        data, source, zoom, prior, budget_s=44.0
    )

    assert len(observed) == 2
    np.testing.assert_array_equal(observed[0][0], zoom["fit"]["selected"]["fit"]["parameters"])
    np.testing.assert_array_equal(observed[1][0], prior["fixed_fit"]["parameters"])
    for _, satellites, options, likelihood in observed:
        np.testing.assert_array_equal(satellites, np.arange(12))
        np.testing.assert_array_equal(options["fixed_position_km"], [3.0, -4.0])
        assert options["budget_s"] == 44.0
        assert likelihood.prepared is prepared
        assert likelihood.masses == {"frozen": True}
    assert result["best_initialization"] == "sealed_profile_zoom_selected"
    assert result["fit_calls"] == 2
    assert result["eligible_for_cohort"] is False


def test_oracle_reseed_budget_is_bounded():
    source, zoom, prior = receipts()
    data = SimpleNamespace(numbers=np.arange(14))
    with pytest.raises(ValueError, match="budget_s"):
        oracle_reseed_diagnostic.fit_oracle_reseeds(
            data, source, zoom, prior, budget_s=45.01
        )
