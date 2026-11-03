import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('remaining',
    Path(__file__).with_name('run_remaining.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@dataclass
class Context:
    deadline: float


def test_finish_only_uses_same_state_and_unspent_whole_budget():
    raw = dict(vector=[1.], nuisance=[2.], diagnostics=dict(
        evaluations=871, elapsed_seconds=20., objective=10.))
    def fit(*args, **kwargs):
        assert kwargs['max_evaluations'] == 1000
        return raw
    audits = iter([dict(accepted=False, feasible=True, training_objective=10., stationarity=.0011),
                   dict(accepted=True, feasible=True, training_objective=10., stationarity=.0001)])
    def polish(ctx, vector, nuisance, **kwargs):
        assert vector is raw['vector'] and nuisance is raw['nuisance']
        assert kwargs['max_evaluations'] == 129
        assert 0 < kwargs['max_seconds'] <= 1
        assert kwargs['expected_objective'] == 10.
        return dict(vector=vector, nuisance=nuisance, diagnostics=dict(evaluations=4))
    result = module.execute(Context(time.monotonic()+1), {}, {}, anneal=True,
                            fit=fit, polish=polish, auditor=lambda *args: next(audits))
    assert result['diagnostics']['evaluations'] == 875
    assert result['raw'] is raw and result['audit']['accepted']


@pytest.mark.parametrize('accepted,remaining', [(True, 1), (False, -1)])
def test_no_finish_of_accepted_or_expired_endpoint(accepted, remaining):
    def forbidden(*args, **kwargs):
        pytest.fail('no supplementary fitting permitted')
    def fit(*args, **kwargs):
        return dict(vector=[1.], nuisance=[2.], diagnostics=dict(
            evaluations=50, elapsed_seconds=1., objective=10.))
    result = module.execute(Context(time.monotonic()+remaining), {}, {}, anneal=False,
        fit=fit, polish=forbidden, auditor=lambda *args: dict(accepted=accepted, feasible=True,
            training_objective=10., stationarity=.0001 if accepted else .1))
    assert result['supplement'] is None
