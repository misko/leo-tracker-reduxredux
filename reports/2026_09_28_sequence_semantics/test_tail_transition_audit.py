import numpy as np
from tail_transition_audit import rectangle_boundary, sign_agreement


def test_rectangle_boundary_ignores_both_coordinate_signs():
    values = np.r_[np.full(400, 0.2 + 0.7j), np.full(600, 0.7 + 0.2j)]
    rng = np.random.default_rng(11)
    scrambled = values.real * rng.choice([-1, 1], len(values)) + 1j * values.imag * rng.choice(
        [-1, 1], len(values)
    )
    for allowed in (0, 2):
        assert rectangle_boundary(values, [0.7, 0.2], allowed) == 400 - allowed
        assert rectangle_boundary(scrambled, [0.7, 0.2], allowed) == 400 - allowed


def test_sign_agreement_accepts_qam_and_excludes_ambiguous_decisions():
    result = sign_agreement(
        np.array([0.7 + 0.2j, -0.7 - 0.2j, 0.01j, np.nan]), np.array([1, -1, 1, 1])
    )
    assert result == dict(support=2, errors=0, agreement=1.0, marginal_agreement=0.5)


def test_constant_sign_baseline_does_not_imply_information():
    result = sign_agreement(np.full(240, 0.7 + 0.2j), np.ones(240))
    assert result["agreement"] == result["marginal_agreement"] == 1
