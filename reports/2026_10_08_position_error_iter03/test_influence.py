from types import SimpleNamespace

import numpy as np
from influence import groups, subset_objective
from influence_policy import choose

from leo.analysis.hard60_score import Hard60Objective
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_score import synthetic_inputs


def test_subset_preserves_parameter_meaning_baseline_and_satellite_bank():
    obs, bank, prior = synthetic_inputs()
    base = Hard60Objective(
        obs,
        bank,
        prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.arange(len(obs.window_ids), dtype=float),
    )
    keep = np.arange(len(obs.window_ids)) % 3 != 0
    model = subset_objective(base, keep)
    assert model.bank is base.bank
    assert model.prior is base.prior
    np.testing.assert_array_equal(model.design, base.design[keep])
    np.testing.assert_array_equal(model.baseline, base.baseline[keep])
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    _, _, before = base.evaluate(vector)
    _, _, after = model.evaluate(vector)
    np.testing.assert_allclose(after.residual_hz, before.residual_hz[keep], atol=1e-12)
    np.testing.assert_allclose(after.responsibilities, before.responsibilities[keep], atol=1e-12)


def test_groups_use_disjoint_supported_rows_and_rank_without_reference(monkeypatch):
    obs, bank, prior = synthetic_inputs()
    base = Hard60Objective(obs, bank, prior, HARD60_SCORE)
    probability = np.zeros((len(obs.window_ids), 3))
    probability[:20, 0] = 0.9
    probability[20:50, 1] = 0.9
    probability[50:, 2] = 0.7  # Ambiguous rows must not be removed.
    monkeypatch.setattr(
        base, "evaluate", lambda _: (0, None, SimpleNamespace(responsibilities=probability))
    )
    vector = np.zeros(base.size)
    selected = groups(base, vector)
    assert [index for index, _, _ in selected] == [1, 0]
    total = np.zeros(len(obs.window_ids), int)
    masses = []
    for index, removed, mass in selected:
        assert removed.sum() >= 14
        assert 0 <= index < len(bank.numbers)
        total += removed
        masses.append(mass)
    assert np.max(total) <= 1
    assert masses == sorted(masses, reverse=True)


def test_frozen_rule_uses_movement_not_reference_error_and_requires_both_arms():
    control = [
        dict(arm=arm, removed_satellite=None, converged=True, error_km=1)
        for arm in ("fitted-c", "zero-c")
    ]
    deletion = [
        dict(arm=arm, removed_satellite=123, converged=True, displacement_km=3, error_km=100)
        for arm in ("fitted-c", "zero-c")
    ]
    doc = dict(candidates=control + deletion)
    assert choose(doc)["fitted-c"]["removed_satellite"] == 123
    deletion[0]["displacement_km"] = 2
    assert choose(doc)["fitted-c"]["removed_satellite"] is None
    deletion[0]["displacement_km"] = 3
    deletion[1]["converged"] = False
    assert choose(doc)["fitted-c"]["removed_satellite"] is None
    deletion[0]["converged"] = False
    assert choose(doc)["fitted-c"]["removed_satellite"] is None
