"""Confidence is a bounded likelihood power, not an evidence multiplier."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_learned_prior_weights import powers


def test_all_measurements_have_unit_power_in_control():
    assert powers([0,.2,1],'unit')==pytest.approx([1,1,1])


def test_confidence_preserves_order_and_has_positive_floor():
    assert powers([0,.2,1],'confidence_only')==pytest.approx([.05,.2,1])


@pytest.mark.parametrize('bad',[[np.nan],[1.1],[-.1],[[.5]]])
def test_invalid_confidence_cannot_enter_the_likelihood(bad):
    with pytest.raises(ValueError):powers(bad,'confidence_only')
