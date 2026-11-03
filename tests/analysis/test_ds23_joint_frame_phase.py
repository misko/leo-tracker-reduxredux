import numpy as np

from ds23_joint_frame_phase import paired_phase, phase_line


def test_unknown_transmitter_phase_cancels_between_receivers():
    rng=np.random.default_rng(513);t=np.arange(15)/750;common=rng.uniform(-np.pi,np.pi,15)
    a=np.exp(1j*common);b=np.exp(1j*(common+2*np.pi*82.4*t+.7))
    result=paired_phase(t,a,b,np.ones(15)*100,np.ones(15)*100)
    assert result['coherence']>.99999
    assert abs(result['frequency_correction_mod750_hz']-82.4)<.01
    assert result['shared_nonlinear_phase_candidate']


def test_individually_coherent_pilots_do_not_prove_shared_transmitter_phase():
    t=np.arange(15)/750;a=np.exp(2j*np.pi*31*t);b=np.exp(2j*np.pi*52*t)
    result=paired_phase(t,a,b,np.ones(15)*100,np.ones(15)*100)
    assert result['coherence']>.99
    assert not result['shared_nonlinear_phase_candidate']


def test_frequency_ambiguity_is_explicit():
    t=np.arange(15)/750;z=np.exp(2j*np.pi*832.4*t)
    result=phase_line(t,z,np.ones(15))
    assert abs(result['frequency_correction_mod750_hz']-82.4)<.01
    assert result['ambiguity_period_hz']==750
