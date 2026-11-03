from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_frame_phase_harmonics import phase_harmonics


def test_discrete_quarter_rotations_are_visible_without_continuous_phase():
    t=np.arange(16)/750
    shifts=np.array([0,1,3,2,2,0,1,3,1,0,2,3,3,2,0,1])*np.pi/2
    result=phase_harmonics(t,shifts+2*np.pi*35*t,seed=19)
    assert result['harmonics']['4']['coherence']>1-1e-12
    assert result['harmonics']['1']['coherence']<.6
    assert result['harmonics']['4']['frequency_correction_modulo_alias_hz']==35
    assert result['fourth_harmonic_rotation_candidate']


def test_continuous_carrier_is_not_labeled_discrete_rotation():
    t=np.arange(16)/750
    result=phase_harmonics(t,2*np.pi*25*t,seed=21)
    assert result['harmonics']['1']['coherence']>1-1e-12
    assert not result['fourth_harmonic_rotation_candidate']


def test_unsupported_frame_series_rejected():
    with pytest.raises(ValueError):phase_harmonics([0,1,1,2],[0,0,0,0])
