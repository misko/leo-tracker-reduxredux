"""Controlled purple-basin interventions preserve data and alias choices."""

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from debug_dsx01_purple_basin import (  # noqa: E402
    family_swap,
    finite_hessian,
    label_differences,
)


def node(norads):
    return dict(
        seed=dict(rows=[
            dict(component=k, candidate_index=v, candidate_norad=v) for k, v in norads.items()
        ]),
        aliases=[2, -1],
    )


def test_family_swap_changes_only_requested_labels_and_preserves_recipient():
    original = node(dict(A=1, B=2))
    saved = copy.deepcopy(original)
    swapped = family_swap(original, node(dict(A=3, B=4)), components=("A",))
    assert original == saved
    assert swapped["aliases"] == original["aliases"]
    assert [r["component"] for r in swapped["seed"]["rows"]] == ["A", "B"]
    assert [r["candidate_norad"] for r in swapped["seed"]["rows"]] == [3, 2]
    assert [r["component"] for r in label_differences(original, swapped)] == ["A"]
    with pytest.raises(ValueError, match="must be present"):
        family_swap(original, node(dict(A=3, B=4)), components=("missing",))


def test_numerical_hessian_preserves_cross_curvature():
    expected = np.array([[4.0, 1.5], [1.5, 2.0]])
    result = finite_hessian(lambda x: 0.5 * x @ expected @ x, [2.0, -1.0])
    np.testing.assert_allclose(result, expected, atol=1e-10)
