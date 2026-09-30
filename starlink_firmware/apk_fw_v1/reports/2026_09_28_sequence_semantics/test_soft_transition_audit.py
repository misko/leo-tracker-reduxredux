import numpy as np
from soft_transition_audit import moments


def test_real_axis_noise_and_forced_qam_points_are_distinguishable():
    signs = np.array([1, -1, 1, -1])
    soft = 0.7 * signs + 0.01j * signs[::-1]
    hard = 0.7 * signs + 0.236j * signs[::-1]
    assert moments(soft)["quadrature_to_inphase_power"] < 0.001
    assert moments(hard)["quadrature_to_inphase_power"] > 0.1
    assert moments(soft)["median_abs_real"] == moments(hard)["median_abs_real"]
