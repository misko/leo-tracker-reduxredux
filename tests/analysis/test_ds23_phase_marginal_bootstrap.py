import numpy as np
import pytest

from ds23_phase_marginal_bootstrap import FrameResampledPhaseIQ
from test_ds23_phase_marginal_iq import make


def test_paired_frame_resampling_is_exact_likelihood_and_gradient_weighting():
    original,p=make();draw=np.array([0,1,1,2,4])
    weighted=FrameResampledPhaseIQ(original.y,original.fs,'lower',original.epochs,original.frames,
        original.noise,original.gain,draw_indices=draw)
    expected_loss=0.;expected_gradient=np.zeros_like(p)
    frames=original.frames
    for k in draw:
        original.frames=[frames[k]]
        statistics=original.statistics(p)
        expected_loss+=statistics['NLL'];expected_gradient+=statistics['gradient_scaled']
    statistics=weighted.statistics(p)
    np.testing.assert_allclose(statistics['NLL'],expected_loss,atol=1e-8)
    np.testing.assert_allclose(statistics['gradient_scaled'],expected_gradient,atol=1e-8)
    assert len(np.unique(weighted.used))<len(weighted.used)


def test_invalid_paired_frame_resampling_is_explicit():
    original,p=make()
    for draw in [[0,1,1,2],[0,1,2,8],[0.,1.,2.,3.]]:
        with pytest.raises(ValueError):
            FrameResampledPhaseIQ(original.y,original.fs,'lower',original.epochs,original.frames,
                original.noise,original.gain,draw_indices=draw)
