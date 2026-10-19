"""Causal satellite scale fallback and adaptation without RF or GPS labels."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from learn_ds23_satellite_phase_scale import posterior_multiplier


def test_no_history_and_no_adaptation_keep_population_scale():
    assert posterior_multiplier([],3.,1.)==1.
    assert posterior_multiplier([0.,100.],3.,0.)==1.


def test_consistently_small_and_large_innovations_change_scale_in_correct_direction():
    small=posterior_multiplier([.1,-.1,.1,-.1],3.,.5)
    large=posterior_multiplier([3.,-3.,3.,-3.],3.,.5)
    assert 0<small<1<large


def test_single_outlier_has_less_effect_than_repeated_large_errors():
    single=posterior_multiplier([.1,.1,.1,10.],3.,.5)
    repeated=posterior_multiplier([10.,10.,10.,10.],3.,.5)
    assert single<repeated


def test_nonfinite_innovations_are_rejected():
    with pytest.raises(ValueError):posterior_multiplier([np.nan],3.,.5)
