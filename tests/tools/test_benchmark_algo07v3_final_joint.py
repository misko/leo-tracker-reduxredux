from types import SimpleNamespace

import benchmark_algo07v3_final_joint as benchmark
import pytest


@pytest.mark.parametrize('fault', [None, 'result', 'receipt', 'calls'])
def test_checkpoint_requires_whole_fit_receipt_and_one_removed_call(monkeypatch, fault):
    context = dict(numerical_policy=SimpleNamespace(
        receipt={'calls': 0}, joint_contraction_optimized=False))
    monkeypatch.setattr(benchmark.joint, 'joint_density',
                        lambda *a: {'phase_pair_count': 10, 'score': 12.})

    def operation(d, *args):
        benchmark.joint.joint_density(d)
        benchmark.joint.joint_density(d)
        d['numerical_policy'].receipt['calls'] += 1
        return dict(history=[1, 2], objective=12.)

    def optimized(d, *args):
        benchmark.joint.joint_density(d)
        if fault == 'calls':
            benchmark.joint.joint_density(d)
        d['numerical_policy'].receipt['calls'] += 2 if fault == 'receipt' else 1
        return dict(history=[1, 3] if fault == 'result' else [1, 2], objective=12.)

    def fork(fn, tasks, workers):
        assert workers == 1
        # Mimic each child's private state, while keeping errors visible to pytest.
        context['numerical_policy'].receipt = {'calls': 0}
        return [fn(tasks[0])]

    monkeypatch.setattr(benchmark, '_ordered', fork)
    def build(name, source):
        assert name == 'operation'
        assert 'def operation(' in source
        assert 'def observed(' not in source
        return optimized, source

    monkeypatch.setattr(benchmark, 'candidate', build)
    saved = []
    if fault:
        with pytest.raises(ValueError):
            benchmark.measure(operation, (context,), saved.append)
    else:
        result = benchmark.measure(operation, (context,), saved.append)
        assert [r['side'] for r in result] == ['baseline', 'candidate', 'candidate', 'baseline']
        assert [len(r['calls']) for r in result] == [2, 1, 1, 2]
        assert all(r['exact'] for r in result)
        assert result == saved
