import numpy as np
from evaluate import covered, peaks

def test_empty_flat_and_negative_surfaces():
    assert peaks(np.zeros(20))==[]
    assert peaks(np.ones(20))==[]
    assert peaks(-np.ones(20))==[]

def test_peak_order_circular_exclusion_and_budget():
    scores=np.zeros(30);scores[[0,3,10,20,28]]=[5,6,4,4,7]
    assert peaks(scores,3)==[28,3,10]

def test_coverage_uses_absolute_epoch_distance():
    assert covered(10,[8],2)
    assert not covered(11,[8],2)
    assert not covered(0,[29],2)
