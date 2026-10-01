from __future__ import annotations

import numpy as np
import pytest
from association_diagnostics import normalized_diagnostics


def test_dominant_satellite_has_low_conditional_entropy():
    result = normalized_diagnostics([0., -20., -30.])
    assert result["background_probability"] < 1e-10
    assert not result["background_is_argmax"]
    assert result["conditional_satellite_entropy_nats"] < 1e-6
    assert result["max_satellite_probability"] == pytest.approx(1., abs=1e-8)
    assert result["effective_branch_count"] == pytest.approx(1., abs=1e-6)


def test_background_and_equal_satellites_are_normalized_and_distinct():
    background = normalized_diagnostics([-10., -11., 0.])
    assert background["background_is_argmax"]
    assert background["background_probability"] > .999
    ambiguous = normalized_diagnostics([0., 0., -np.inf])
    assert ambiguous["background_probability"] == 0.
    assert ambiguous["conditional_satellite_entropy_nats"] == pytest.approx(np.log(2))
    assert ambiguous["effective_branch_count"] == pytest.approx(2.)


def test_all_impossible_weights_are_rejected():
    background_only = normalized_diagnostics([-np.inf, -np.inf, 0.])
    assert background_only["background_probability"] == 1.
    assert background_only["conditional_satellite_entropy_nats"] is None
    assert background_only["max_satellite_probability"] == 0.

    with pytest.raises(ValueError, match="finite"):
        normalized_diagnostics([-np.inf, -np.inf])
