from tools.research.matched_bandwidth_phase import split_groups, circular_affine, wrapped_phase_error
import numpy as np


def test_split_is_seeded_whole_groups():
    a = split_groups(6); b = split_groups(6)
    assert a == b and a == ([1, 2, 5], [0, 3, 4])
    assert set(a[0]).isdisjoint(a[1]) and sorted(a[0]+a[1]) == list(range(6))


def test_circular_affine_uses_only_training_points():
    t=np.arange(6)*.02; phase=np.pi*.2+2*np.pi*5*t
    phase[3:] += 1.4
    intercept,hz=circular_affine(t,phase,np.array([True,True,True,False,False,False]))
    assert abs(hz-5)<.1 and abs(np.angle(np.exp(1j*(intercept-np.pi*.2))))<.03


def test_cross_vector_phase_does_not_collapse_pi_difference():
    assert np.isclose(abs(wrapped_phase_error(np.array([np.pi]), np.array([0.]))[0]), np.pi)
