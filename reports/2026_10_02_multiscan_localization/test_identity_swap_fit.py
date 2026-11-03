from types import SimpleNamespace

import numpy as np

import identity_swap_fit


def test_swap_preserves_incumbent_global_parameters_and_zeros_inserted_tau():
    data = SimpleNamespace(numbers=np.arange(8))
    parameters = np.arange(14.0)
    incumbent = {"satellite_indices": np.array([1, 3, 5]), "parameters": parameters}
    swap = {"removed_index": 3, "added_index": 6}
    bank, initial, slot, removed_tau = identity_swap_fit.swapped_bank_and_initial(
        data, incumbent, swap
    )
    np.testing.assert_array_equal(bank, [1, 6, 5])
    expected = parameters.copy()
    expected[12] = 0.0
    np.testing.assert_array_equal(initial, expected)
    assert slot == 1
    assert removed_tau == parameters[9]


def test_fit_uses_exact_prescribed_swap_and_common_penalty_without_reference(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "truth" in name or "reference" in name or "known_site" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    data = Data(
        numbers=np.arange(8),
        measured=np.zeros(2),
        group=np.arange(2),
        times=np.arange(2.0),
        receiver=np.array([0, 1]),
        channel=np.zeros(2),
        rf=np.full(2, 11.3e9),
    )
    incumbent = {
        "parameters": np.zeros(14),
        "satellite_indices": np.array([0, 1, 2]),
        "satellite_count": 3,
        "identity_masses": {
            "raw_satellite_mass": np.full(3, 0.8 / 3),
            "raw_background_mass": 0.2,
            "anchor_satellite_mass": np.empty((0, 3)),
            "anchor_unknown_mass": np.empty(0),
        },
        "objective": 10.0,
        "selection_score": 12.0,
        "entry_penalty": 2.0,
        "success": True,
        "status": "converged",
    }
    expanded = {
        "score_leader": incumbent,
        "anchors": [],
        "full_bank": np.array([0, 1, 2]),
    }
    diagnostic = {
        "selected_count": 3,
        "selected_indices": np.array([0, 1, 2]),
        "best_swap": {
            "removed_index": 1,
            "removed_catalog_number": 101,
            "added_index": 5,
            "added_catalog_number": 105,
            "penalized_score_improvement": 3.0,
        },
    }
    monkeypatch.setattr(identity_swap_fit, "frozen_row_weights", lambda data: np.ones(2))
    monkeypatch.setattr(
        identity_swap_fit,
        "prepare_track_grouped_likelihood",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(identity_swap_fit, "_validate_incumbent_objective", lambda *args: 10.0)
    likelihood = SimpleNamespace(last_result={})
    monkeypatch.setattr(identity_swap_fit, "FixedBankLikelihood", lambda *args: likelihood)

    def fake_refine(data, initial, satellites, support, prepared, **options):
        assert initial[11] == 0.0
        np.testing.assert_array_equal(satellites, [0, 5, 2])
        prepared.last_result = {}
        return {
            "parameters": initial,
            "satellite_indices": satellites,
            "satellite_count": 3,
            "satellite_weights": np.ones(3) / 3,
            "objective": 8.0,
            "selection_score": 10.0,
            "entry_penalty": 2.0,
            "success": True,
            "status": "converged",
        }

    monkeypatch.setattr(identity_swap_fit, "refine_gauss_newton", fake_refine)
    result = identity_swap_fit.fit_identity_swap(
        data, expanded, diagnostic, budget_s=1.0
    )
    assert result["score_leader"]["branch"] == "prescribed_single_swap"
    assert result["selection_resolved"]
    assert result["swapped_refit_count"] == 1
    assert result["greedy_search_performed"] is False
