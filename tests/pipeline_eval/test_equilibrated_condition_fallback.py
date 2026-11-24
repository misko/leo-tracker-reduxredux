from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
import equilibrated_condition_fallback as study
from leo.analysis.localization_v3.hierarchical import hierarchical_bound


def test_power_two_scaling_keeps_unscaled_posterior_and_determinant():
    middle = np.array([[2.0, 0.45, 0.25], [0.45, 3.0, -0.5], [0.25, -0.5, 4.0]])
    diagonal = np.array([2.**16, 2.**-4, 2.**4])
    gram = middle * diagonal[:, None] * diagonal
    rhs = np.array([-2, 1.5, 9]) * diagonal
    (mean, cov, _), errors, logdet = study.equilibrated(gram, rhs, np.ones(3), True)
    expected, expected_cov, expected_logdet = study.original_factor(gram, rhs, True)
    np.testing.assert_allclose(mean, expected, atol=1e-14)
    np.testing.assert_allclose(cov, expected_cov, atol=1e-14)
    assert abs(logdet - expected_logdet) < 2e-14
    assert errors["mean_error"] < 1e-14
    assert errors["factor_error"] < 1e-14
    assert errors["covariance_error"] < 1e-14


def test_uncertified_factor_reexecutes_original_dense():
    original = study.DenseAlternative(hierarchical_bound)
    inputs = (np.array([3., 1., 4.]), np.ones((3, 1)), 2., [0, 0, 1])
    with patch.object(study, "equilibrated", side_effect=study.UncertainArithmetic("forced check")):
        result = original(*inputs)
    control = hierarchical_bound(*inputs)
    assert original.counts["retry_original"] == 1
    assert original.counts["accepted_dense_alternative"] == 0
    for key, value in control.items():
        np.testing.assert_array_equal(value, result[key])


@pytest.mark.frozen_v5_numerics
def test_deterministic_width_refusal_preserves_a_fresh_dense_output():
    from leo.analysis.localization_v4.native_bound import NativeBound

    path = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets/native/native_bound.so")
    owner = NativeBound(path)
    operation, metadata = study.exact_unsupported_layout(owner.__call__)
    u = np.eye(5)
    groups = np.zeros(5, dtype=int)
    for bias in (1, 2):
        data = np.arange(5.) + bias, u, 2., groups
        value = operation(*data)
        for k, result in hierarchical_bound(*data).items():
            np.testing.assert_array_equal(value[k], result)
    assert metadata == {"hits": 1, "remembered": 1}
    assert owner.counts["fallback_unsupported"] == 2
    owner.clear()
