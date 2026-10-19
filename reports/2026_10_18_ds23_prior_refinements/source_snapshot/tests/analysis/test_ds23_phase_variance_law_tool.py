"""The learned variance law is causal and monotone in its measured proxy."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from learn_ds23_phase_variance_law import phase_sigma,learn


def test_variance_law_has_positive_floor_and_increases_with_age_and_disagreement():
    assert phase_sigma(.7,.5,0,100,200)==pytest.approx(.7)
    values=phase_sigma(.7,.5,np.array([0,1,2]),100,200)
    assert np.all(np.diff(values)>0)
    assert phase_sigma(.7,.5,1,200,200)>phase_sigma(.7,.5,1,100,200)
    assert phase_sigma(.7,.5,1000,10000,1)==15


def test_insufficient_tle_history_does_not_fit_a_new_law():
    assert learn([])['fallback']
