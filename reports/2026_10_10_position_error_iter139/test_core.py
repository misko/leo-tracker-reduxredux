import numpy as np
import pytest
from core import diagnostic


def evaluate(z, r=None):
    z = np.asarray(z, float)
    if z.ndim == 1:
        z = z[:, None]
    if r is None:
        r = np.ones_like(z)
    ids = [str(i) for i in range(len(z))]
    pairs = [
        dict(
            first_window_id=str(i),
            second_window_id=str(i + 1),
            group=[0, 1, 100, "upper"],
            alternating_block=(i // 2) % 2,
        )
        for i in range(0, len(z), 2)
    ]
    return diagnostic(r, z, pairs, ids, list(range(z.shape[1])))


def test_constant_bias_explains_product():
    result = evaluate([2, 3, 2, 3])
    assert result["weighted_product_sum"] == 12
    assert result["crossprediction_centered_product_sum"] == 0
    assert result["crossprediction_mass"] == 2


def test_zero_mean_shared_fluctuations_survive_centering():
    result = evaluate([1, 1, 1, 1, -1, -1, -1, -1])
    assert result["weighted_product_sum"] == 4
    assert result["crossprediction_centered_product_sum"] == 4


def test_soft_mixture_and_zero_mass_preserved_without_hardlabels():
    result = evaluate([[2, 5], [3, 7], [2, 5], [3, 7]], np.array([[0.25, 0.5]] * 4))
    assert result["shared_label_mass"] == 0.625
    assert result["weighted_product_sum"] == 2 * (0.0625 * 6 + 0.25 * 35)
    assert len(result["group_satellite_records"]) == 2
    zero = evaluate([1, 1, 1, 1], np.zeros((4, 1)))
    assert zero["crossprediction_mass"] == 0
    assert zero["group_satellite_records"][0]["blocks"][0]["mean_x"] is None


def test_missing_training_mass_does_not_zero_fill_target():
    result = evaluate([2, 3])
    assert result["weighted_product_sum"] == 6
    assert result["crossprediction_raw_product_sum"] == 0
    assert result["excluded_crossprediction_mass"] == 1


def test_asymmetric_crossprediction_matches_direct_products():
    result = evaluate([1, 2, 3, 5, 2, 4, 7, 11])
    expected = (1 - 5) * (2 - 8) + (2 - 5) * (4 - 8) + (3 - 1.5) * (5 - 3) + (7 - 1.5) * (11 - 3)
    assert result["crossprediction_centered_product_sum"] == expected


def test_invalid_weights_rejected():
    with pytest.raises(ValueError, match="invalid"):
        evaluate([1, 2], np.array([[1.1], [1]]))
