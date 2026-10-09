import runpy
from pathlib import Path

import numpy as np
import pytest

diagnose = runpy.run_path(str(Path(__file__).with_name("observability.py")))["diagnose"]
streamed = runpy.run_path(str(Path(__file__).with_name("observability.py")))["streamed_diagnose"]


@pytest.mark.parametrize("case", ["ordinary", "confounded", "rankdeficient", "rescaled", "zero"])
def test_streamed_dense_equivalence(case):
    rng = np.random.default_rng(42)
    x = rng.normal(size=(37, 2))
    z = rng.normal(size=(37, 4))
    w = rng.uniform(size=37)
    if case == "confounded":
        z[:, :2] = x
    elif case == "rankdeficient":
        z[:, 3] = z[:, 0]
    elif case == "rescaled":
        z *= np.array([1e-100, -1e100, 3, 1])
    elif case == "zero":
        w[:] = 0
    dense = diagnose(x, z, w)
    compressed = streamed(x, z, w, chunk_rows=7)
    assert compressed["rtol"] == dense["rtol"]
    assert compressed["nuisance_rank"] == dense["nuisance_rank"]
    for key in ("raw", "projected"):
        assert compressed[key]["rank"] == dense[key]["rank"]
        np.testing.assert_allclose(
            compressed[key]["information"], dense[key]["information"], atol=1e-12
        )
        np.testing.assert_allclose(
            compressed[key]["singular_values"], dense[key]["singular_values"], atol=1e-12
        )


def test_exact_confounding_and_separate_prior():
    x = np.array([[1, 0], [0, 2], [0, 0]], float)
    result = diagnose(x, x[:, :1], np.ones(3), prior_information=np.eye(2))
    assert result["raw"]["rank"] == 2
    assert result["projected"]["rank"] == 1
    np.testing.assert_allclose(result["projected"]["information"], np.diag([0, 4]))
    np.testing.assert_allclose(result["projected_plus_prior_information"], np.diag([1, 5]))
    full = diagnose(x, x, np.ones(3))
    assert full["projected"]["rank"] == 0


def test_orthogonal_nuisance_weighted_information():
    x = np.array([[1, 0], [0, 2], [0, 0]], float)
    result = diagnose(x, np.array([[0], [0], [1]]), [4, 1, 9])
    np.testing.assert_allclose(result["raw"]["information"], np.diag([4, 4]))
    np.testing.assert_allclose(result["projected"]["information"], result["raw"]["information"])


def test_rotation_equivariance():
    x = np.array([[1, 2], [3, 1], [2, -1], [0, 3]], float)
    z = np.ones((4, 1))
    rotation = np.array([[0.8, -0.6], [0.6, 0.8]])
    original = diagnose(x, z, np.ones(4))
    rotated = diagnose(x @ rotation, z, np.ones(4))
    for key in ("raw", "projected"):
        np.testing.assert_allclose(
            rotated[key]["information"], rotation.T @ original[key]["information"] @ rotation
        )
        np.testing.assert_allclose(
            rotated[key]["singular_values"], original[key]["singular_values"]
        )
        for i in range(2):
            expected = rotation.T @ original[key]["right_directions"][:, i]
            actual = rotated[key]["right_directions"][:, i]
            np.testing.assert_allclose(np.outer(actual, actual), np.outer(expected, expected))


def test_duplicate_nuisance_and_zero_weights():
    x = np.array([[1, 0], [0, 2], [1, 1]], float)
    z = np.ones((3, 1))
    a = diagnose(x, z, [1, 1, 0])
    b = diagnose(x, np.column_stack([z, z, z * 0]), [1, 1, 0])
    assert b["nuisance_rank"] == 1
    np.testing.assert_allclose(a["projected"]["information"], b["projected"]["information"])
    zero = diagnose(x, z, np.zeros(3))
    assert zero["raw"]["rank"] == zero["projected"]["rank"] == 0
    assert zero["nuisance_rank"] == 0


def test_empty_and_one_row_right_basis():
    for n in (0, 1):
        result = diagnose(np.ones((n, 2)), np.empty((n, 0)), np.ones(n))
        directions = result["raw"]["right_directions"]
        np.testing.assert_allclose(directions.T @ directions, np.eye(2), atol=1e-15)


def test_nuisance_column_rescaling_preserves_span():
    x = np.array([[1, 2], [3, 1], [2, -1], [0, 3]], float)
    z = np.column_stack([np.ones(4), np.arange(4)])
    a = diagnose(x, z, np.ones(4))
    b = diagnose(x, z * [1e-100, -1e100], np.ones(4))
    assert a["nuisance_rank"] == b["nuisance_rank"] == 2
    np.testing.assert_allclose(
        a["projected"]["information"], b["projected"]["information"], atol=1e-13
    )


@pytest.mark.parametrize("change", ["negative", "nan", "shape", "rtol", "prior"])
def test_invalid_inputs(change):
    x, z, w, options = np.eye(2), np.empty((2, 0)), np.ones(2), {}
    if change == "negative":
        w[0] = -1
    elif change == "nan":
        x[0, 0] = np.nan
    elif change == "shape":
        z = np.zeros((3, 1))
    elif change == "rtol":
        options["rtol"] = 1
    else:
        options["prior_information"] = np.diag([-1, 1])
    with pytest.raises(ValueError):
        diagnose(x, z, w, **options)
