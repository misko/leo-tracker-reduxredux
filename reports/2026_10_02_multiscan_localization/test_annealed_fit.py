from types import SimpleNamespace

import annealed_fit
import gauss_newton
import numpy as np
import pytest


@pytest.mark.parametrize("optimizer", ["lbfgs", "gauss-newton"])
def test_continuation_uses_only_final_sigma_for_selection_and_clears_omitted_taus(
    monkeypatch, optimizer
):
    calls = []

    def fake_refine(
        data,
        initial,
        satellites,
        support,
        likelihood,
        *,
        sigma_hz,
        budget_s,
        share_predictions=None,
    ):
        assert share_predictions == (True if optimizer == "lbfgs" else None)
        calls.append((sigma_hz, budget_s, initial.copy(), satellites.copy()))
        parameters = initial.copy()
        parameters[6 + satellites] = 0.25
        likelihood.last_result = {"group_count": 10}
        return {
            "parameters": parameters,
            "satellite_weights": support / support.sum(),
            "selection_score": -sigma_hz,
            "success": True,
        }

    monkeypatch.setattr(annealed_fit, "refine_bank", fake_refine)
    monkeypatch.setattr(gauss_newton, "refine_gauss_newton", fake_refine)
    ladder = [(np.array([2]), np.ones(1)), (np.array([2, 0]), np.ones(2))]
    initial = np.zeros(9)
    warmup, warmed, trials = annealed_fit.continue_banks(
        SimpleNamespace(), initial, ladder, None, [], share_predictions=True, optimizer=optimizer
    )
    assert [call[0] for call in calls] == [2000, 1000, 500, 200, 200]
    assert [call[1] for call in calls] == [10, 10, 10, 45, 45]
    assert len(warmup) == 3
    assert [trial["sigma_hz"] for trial in trials] == [200, 200]
    assert calls[3][2][6] == 0
    assert calls[3][2][8] == 0.25
    assert warmed[6] == 0.25
    np.testing.assert_array_equal(initial, np.zeros(9))
