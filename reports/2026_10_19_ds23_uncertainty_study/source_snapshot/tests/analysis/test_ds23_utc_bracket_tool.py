"""UTC corrections shift orbit queries while preserving device elapsed time."""

import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_utc_bracket import shift_geometry


def test_clock_shift_does_not_shift_receiver_design_or_original_observation_times():
    times=np.array([0.,1.,2.]);hardware=np.array([[1.],[2.],[3.]])
    p=SimpleNamespace(flat_times=times,hardware=hardware,smooth=hardware.copy())
    shift_geometry(p,.125)
    assert p.flat_times==pytest.approx([.125,1.125,2.125])
    assert times==pytest.approx([0,1,2])
    assert p.hardware is hardware and p.smooth==pytest.approx(hardware)


def test_zero_shift_preserves_orbit_query_times():
    p=SimpleNamespace(flat_times=np.array([1.,2.]))
    assert shift_geometry(p,0).flat_times==pytest.approx([1,2])
