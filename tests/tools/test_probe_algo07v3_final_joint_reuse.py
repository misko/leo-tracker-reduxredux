from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_final_joint_reuse import candidate

from leo.analysis.localization_v3 import joint_recovery as joint
from tests.analysis.test_joint_predictive_families import fixture


@pytest.mark.parametrize('name', ['_fit_lbfgsb', '_fit_powell'])
@pytest.mark.parametrize('method', ['control', 'factorized', 'joint'])
@pytest.mark.parametrize('optimized', [True, False])
def test_final_reuse_preserves_all_fields_and_ordered_fit_receipts(
        monkeypatch, name, method, optimized):
    inputs = fixture()
    before = fingerprint(inputs)
    calls, receipts = [], []
    p = SimpleNamespace(
        keep=np.array([True]), labels=np.array([0]),
        calculate=lambda _: dict(negative_twice_elbo=100., elevation=np.array([10.])),
        state=lambda _: dict(phases=np.zeros(1)))
    monkeypatch.setattr(joint, 'NewFamily', lambda *a, **kw: SimpleNamespace(phases=np.zeros(1)))
    monkeypatch.setattr(joint, 'make_event_problem', lambda *a, **kw: p)
    monkeypatch.setattr(joint, 'attach_event_predictive', lambda *a: None)
    monkeypatch.setattr(joint, 'cached', lambda p: p)
    monkeypatch.setattr(joint, 'summary', lambda *a: dict(negative_twice_elbo=100.))
    monkeypatch.setattr(joint, 'joint_inputs', lambda *a: inputs)
    original = joint.joint_density

    def observed(*args):
        result = original(*args)
        calls.append(fingerprint(result))
        return result

    monkeypatch.setattr(joint, 'joint_density', observed)

    def minimize(d, fn, objective, x, **kw):
        result = SimpleNamespace(x=x, fun=objective(x), success=True, message='done', nfev=1)
        receipts.append(('minimize', result.fun, deepcopy(kw)))
        return result

    def refresh(d, p, phases, reference):
        receipts.append(('refresh', phases.copy(), reference.copy()))
        return reference.copy(), {'phase_change_s': 0.}

    monkeypatch.setattr(joint.numerics, 'minimize', minimize)
    monkeypatch.setattr(joint.numerics, 'refresh', refresh)
    monkeypatch.setattr(joint.numerics, 'check_problem', lambda *a: None)
    d = dict(scan=object(), model={}, means=[0], node={}, keep=[True], powers=[1], entries=[])
    d['numerical_policy'] = SimpleNamespace(joint_contraction_optimized=optimized)
    baseline = getattr(joint, name)(d, [[], []], 'c0', method, .025)
    baseline_calls, baseline_receipts = list(calls), fingerprint(receipts)
    calls.clear()
    receipts.clear()
    fn, _ = candidate(name)
    result = fn(d, [[], []], 'c0', method, .025)
    assert fingerprint(result) == fingerprint(baseline)
    assert fingerprint(receipts) == baseline_receipts
    assert len(calls) == len(baseline_calls) - 1
    assert calls == baseline_calls[:-1]
    assert fingerprint(inputs) == before


def test_source_drift_refused():
    with pytest.raises(ValueError, match='boundary'):
        candidate('_fit_lbfgsb', 'def _fit_lbfgsb(): return {}')
