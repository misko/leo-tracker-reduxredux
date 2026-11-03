import numpy as np
import pytest
from probe_ds23_frame_phase_coherence import coherence


def test_coherent_frame_gains_recover_carrier_phase_rate_under_amplitude_changes():
    t=np.arange(14)/750
    gain=(1+.15*np.arange(14))*np.exp(1j*(1.2+2*np.pi*24.5*t))
    result=coherence(t,gain,np.ones(14))
    assert result['frequency_correction_hz']==pytest.approx(24.5)
    # Unequal amplitudes are correctly penalized by the common complex gain.
    expected=abs(sum(abs(gain)))**2/(len(gain)*sum(abs(gain)**2))
    assert result['coherent_fraction']==pytest.approx(expected)
    assert result['phase_only_fraction']==pytest.approx(1.)
    assert result['phase_RMS_rad']<1e-12


def test_random_frame_phases_do_not_get_called_coherent_after_search():
    rng=np.random.default_rng(14);t=np.arange(14)/750
    result=coherence(t,np.exp(1j*rng.uniform(-np.pi,np.pi,14)),np.ones(14))
    assert result['coherent_fraction']<.7
