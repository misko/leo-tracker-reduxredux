"""The initial-branch observer delegates unchanged and restores every hook."""

import numpy as np
import pytest
from profile_algo07v3_initial_convergence import FirstCappedCapture, observe

from leo.analysis.localization_v3 import position


@pytest.mark.parametrize('fail', [False, True])
def test_phase_coordinates_identity_and_restoration(monkeypatch, fail):
    sentinel = dict(precision_iterations=256, final_log_precision_change=.02)
    args = (np.ones(3), np.ones((3, 2)), np.ones(3), np.arange(3))
    def bound(*a, **kw):
        assert a is not None
        return sentinel
    def calculate(self, x):
        return position.hierarchical_bound(*args)
    def fit(p, x):
        result = p.calculate(x)
        if fail:
            raise RuntimeError('original failure')
        return result
    monkeypatch.setattr(position, 'hierarchical_bound', bound)
    monkeypatch.setattr(position, 'fit', fit)
    monkeypatch.setattr(position.NormalPosition, 'calculate', calculate)
    p = object.__new__(position.NormalPosition)
    rows = []
    try:
        with observe(rows):
            assert position.fit(p, [1., 2.]) is sentinel
            assert p.calculate([1., 2.]) is sentinel
            assert position.fit(p, [3., 4.]) is sentinel
    except RuntimeError as exc:
        assert fail and str(exc) == 'original failure'
    assert len(rows) == (1 if fail else 3)
    assert rows[0]['phase'] == 0 and rows[0]['in_fit']
    assert rows[0]['position'] == [float(1).hex(), float(2).hex()]
    assert rows[0]['iterations'] == 256
    if not fail:
        assert not rows[1]['in_fit']
        assert rows[0]['input_signature'] == rows[1]['input_signature']
        assert rows[0]['result_signature'] == rows[1]['result_signature']
        assert rows[2]['phase'] == 1 and rows[2]['in_fit']
    assert position.fit is fit and position.hierarchical_bound is bound
    assert position.NormalPosition.calculate is calculate


def test_capture_first_capped_fit_owns_inputs(tmp_path):
    capture = FirstCappedCapture()
    a = np.arange(3.)
    kwargs = dict(prior_groups=np.array([-1, 0]), iterations=256)
    capture.record(dict(in_fit=False, iterations=256), (a,), kwargs)
    capture.record(dict(in_fit=True, iterations=20), (a,), kwargs)
    assert capture.value is None
    capture.record(dict(in_fit=True, iterations=256, phase=1), (a,), kwargs)
    a[:] = 10
    kwargs['prior_groups'][:] = 1
    capture.record(dict(in_fit=True, iterations=256, phase=2), (a,), kwargs)
    assert capture.value[0]['phase'] == 1
    np.testing.assert_array_equal(capture.value[1][0], np.arange(3.))
    np.testing.assert_array_equal(capture.value[2]['prior_groups'], [-1, 0])
    assert capture.save(tmp_path/'capture')
    with np.load(tmp_path/'capture'/'hardest.npz', allow_pickle=False) as data:
        np.testing.assert_array_equal(data['argument_0'], np.arange(3.))
    assert not FirstCappedCapture().save(tmp_path/'empty')
