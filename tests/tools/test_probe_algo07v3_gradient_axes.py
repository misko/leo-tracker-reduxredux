import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_gradient_axes import transform

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton


@pytest.mark.parametrize('initial', [[0., 0.], [-12.5, 12.5], [12.5, -12.5]])
def test_parallel_axes_preserve_complete_optimizer_history_and_evaluation_counts(initial):
    candidate, _, _ = transform()
    def residual(x):
        return np.array([x[0] - 3, x[1] + 2, .05 * x[0] * x[1]])
    kwargs = dict(iterations=12)
    reference = bounded_gauss_newton(residual, initial, [-12.5] * 2, [12.5] * 2, **kwargs)
    result = candidate(residual, initial, [-12.5] * 2, [12.5] * 2, **kwargs)
    assert fingerprint(result) == fingerprint(reference)


def test_trial_restores_optimizer_after_failure(monkeypatch):
    from probe_algo07v3_gradient_axes import position, prediction, trial

    original = position.bounded_gauss_newton
    def fail(*args, **kwargs):
        raise RuntimeError('fit failed')
    monkeypatch.setattr(prediction, 'fit_training', fail)
    with pytest.raises(RuntimeError, match='fit failed'):
        trial(dict(node={}), None, 'c0', object())
    assert position.bounded_gauss_newton is original
