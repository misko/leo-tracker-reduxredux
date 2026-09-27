import numpy as np
from run_long import eligible

def test_duration_uses_training_support_only():
    t=dict(t=np.array([0.,29.,300.]),mask=np.array([True,True,False]))
    assert not eligible(t)
    t['t'][2]=1e9;assert not eligible(t)
    t['t'][1]=30.;assert eligible(t)
