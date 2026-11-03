import numpy as np
import pytest

from ds23_joint_iq_frame_bootstrap import FrameResampledJointIQ


def test_paired_frame_weights_match_independent_weighted_least_squares():
    rng = np.random.default_rng(119)
    samples = rng.normal(size=(2, 20000))+1j*rng.normal(size=(2, 20000))
    segments = [np.arange(a, a+900) for a in [250, 3650, 7050, 10450, 13850, 17250]]
    draw = np.array([0, 0, 1, 2, 3, 4])
    noise = [.3, .5]
    problem = FrameResampledJointIQ(samples, 2500000., 'lower', [[23.2, 193.4], [23.28, 193.35]], segments, noise, draw)
    p = np.r_[12000., 42000., 1500., .123, 6.4, -.234, -3.3, .143, 6.2, -.214, -3.1, .8, .2, .9, -.1]
    signals = problem.signals(p)
    signals[1] *= problem.ratios(p)
    expected = 0.
    for k, ix in enumerate(segments):
        n = len(ix)
        design = np.zeros((2*n, 4), complex)
        design[:n, :2] = signals[0][ix]
        design[n:, :2] = signals[1][ix]
        design[:n, 2] = 1.
        design[n:, 3] = 1.
        w = np.repeat(1/np.sqrt(noise), n)
        design *= w[:, None]
        y = np.r_[samples[0, ix], samples[1, ix]]*w
        coefficient = np.linalg.lstsq(design, y, rcond=1e-8)[0]
        residual = y-design@coefficient
        expected += np.count_nonzero(draw == k)*np.vdot(residual, residual).real
    np.testing.assert_allclose(problem.statistics(p)['quadratic'], expected, rtol=1e-12)


def test_too_few_distinct_physical_frames_cannot_supply_bootstrap_information():
    segments = [np.arange(a, a+900) for a in [250, 3650, 7050, 10450]]
    with pytest.raises(ValueError, match='four distinct'):
        FrameResampledJointIQ(np.zeros((2, 15000)), 2500000., 'lower', [[23.2, 193.4], [23.28, 193.35]],
            segments, [1., 1.], [0, 0, 1, 2])
