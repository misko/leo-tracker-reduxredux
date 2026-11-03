from types import SimpleNamespace

import numpy as np
import profile_bank_selection as subject


def test_bank_refinement_preserves_masses_resets_omitted_tau_and_retains_incumbent(monkeypatch):
    data = SimpleNamespace(
        measured=np.zeros(4), times=np.arange(4), group=np.arange(4),
        rf=np.ones(4), receiver=np.zeros(4), channel=np.ones(4),
    )
    source = {"anchors": [], "trials": [
        {"satellite_indices": [0], "identity_masses": {"tag": 1},
         "selection_score": 1, "objective": 1, "success": False},
        {"satellite_indices": [0, 1], "identity_masses": {"tag": 2},
         "selection_score": 10, "objective": 10, "success": True},
    ]}
    calls = []

    def refiner(data, parameters, satellites, support, likelihood, **options):
        calls.append(parameters.copy())
        likelihood.last_result = {}
        return {"selection_score": 2, "objective": 2, "success": True,
                "satellite_indices": satellites, "parameters": parameters}

    monkeypatch.setattr(subject, "refine_gauss_newton", refiner)
    seed = np.arange(8, dtype=float)
    result = subject.refine_profile_banks(data, source, {"selected": {"fit": {"parameters": seed}}})
    assert calls[0][7] == 0
    np.testing.assert_array_equal(calls[1], seed)
    assert result["attempts"][0]["identity_masses"] == {"tag": 1}
    assert result["trials"][0]["selection_score"] == 1
    assert result["trials"][1]["selection_score"] == 2
    assert not result["selection_resolved"]
    np.testing.assert_array_equal(seed, np.arange(8))
