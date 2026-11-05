import ast
import inspect
import json
from types import SimpleNamespace

import benchmark_algo07v3_family_gates as benchmark
import pytest

from leo.analysis.localization_v3 import recovery_controller as controller
from leo.analysis.localization_v3 import recovery_inclusion as inclusion


def test_old_audit_uses_identical_context_builders():
    for name in ('_problem', '_targets', 'attach_recovery_predictive'):
        assert ast.dump(ast.parse(inspect.getsource(getattr(benchmark.oracle, name)))) == (
            ast.dump(ast.parse(inspect.getsource(getattr(inclusion, name)))))


@pytest.mark.parametrize('different', [False, True])
@pytest.mark.parametrize('numerical', [False, True])
def test_order_exactness_and_hook_restoration(monkeypatch, tmp_path, different, numerical):
    calls, affinities = [], []
    context = dict(numerical_policy=SimpleNamespace(receipt=dict(calls=[]))) if numerical else {}

    def record(args):
        if numerical:
            args[0]['numerical_policy'].receipt['calls'].append('audit')

    def baseline(*args, **kwargs):
        calls.append('baseline')
        record(args)
        return dict(answer=43 if different else 42)

    def candidate(*args, **kwargs):
        calls.append('candidate')
        record(args)
        return dict(answer=42)

    monkeypatch.setattr(benchmark.oracle, 'audit_inclusion', baseline)
    monkeypatch.setattr(controller, 'audit_inclusion', candidate)
    monkeypatch.setattr(benchmark.os, 'sched_getaffinity', lambda pid: {2, 3, 4})
    monkeypatch.setattr(benchmark.os, 'sched_setaffinity',
                        lambda pid, mask: affinities.append(mask))
    monkeypatch.setattr(benchmark, 'worker', lambda *args:
                        controller.audit_inclusion(context, shared=True))
    if different:
        with pytest.raises(ValueError, match='Complete audit differs'):
            benchmark.observed_worker(tmp_path, 2)
        assert not (tmp_path / 'audits.json').exists()
    else:
        assert benchmark.observed_worker(tmp_path, 2) == dict(answer=42)
        assert calls == ['candidate', 'baseline', 'candidate', 'candidate', 'baseline']
        rows = json.loads((tmp_path / 'audits.json').read_text())[0]['rows']
        assert all(row['exact'] and row['completed'] for row in rows)
    assert affinities == [{2}, {2, 3, 4}]
    assert controller.audit_inclusion is candidate
    if numerical:
        assert context['numerical_policy'].receipt == dict(calls=['audit'])


@pytest.mark.parametrize('repeats', [0, 4])
def test_repetition_budget_is_bounded(repeats):
    with pytest.raises(ValueError, match='one to three'):
        benchmark.trials({}, {}, repeats)
