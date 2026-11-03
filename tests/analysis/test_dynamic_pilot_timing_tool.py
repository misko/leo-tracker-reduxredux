"""Synthetic propagation has consistent delay and Doppler-rate derivatives."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_dynamic_pilot_timing import periodic_sample,geometry


def test_periodic_fractional_sampling_wraps_without_phase_conjugation():
    wave=np.array([1+1j,3+2j,5+3j])
    assert periodic_sample(wave,np.array([0,.5,3,3.5]))==pytest.approx([1+1j,2+1.5j,1+1j,2+1.5j])


def test_delay_derivative_matches_injected_doppler_geometry():
    t=np.array([-100.,0.,100.]);h=.01
    delay,rate=geometry(t)
    derivative=(geometry(t+h)[0]-geometry(t-h)[0])/(2*h)
    assert derivative==pytest.approx(rate,abs=1e-12)
    assert rate[0]<0 and rate[2]>0 and delay[1]<delay[0]
