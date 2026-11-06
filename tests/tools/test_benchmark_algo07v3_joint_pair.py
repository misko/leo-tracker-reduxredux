import copy

import benchmark_algo07v3_joint_pair as benchmark
import pytest

from leo.analysis.localization_v3.numerical_policy import NumericalPolicy


@pytest.mark.parametrize('numerical', [False, True])
def test_real_forks_preserve_both_results_and_receipts(numerical):
    context = {'numerical_policy': NumericalPolicy()} if numerical else {}

    def operation(d, targets, arm, method, step):
        policy = d.get('numerical_policy')
        if policy:
            policy.receipt['problem_count'] += 1
            policy.receipt['optimizer_calls'].append({'arm': arm})
            policy.receipt['reference_updates'].append({'arm': arm, 'step': step})
        return dict(arm=arm, history=[1, 2], objective=10 if arm == 'c0' else 12)

    rows = benchmark.measure(operation, (context, [], 'c0', 'joint', .0625), lambda _: None)
    assert [r['side'] for r in rows] == ['baseline', 'candidate', 'candidate', 'baseline']
    assert all(r['exact'] for r in rows)
    assert all(len(r['arm_signatures']) == 2 for r in rows)
    # The live checkpoint remains pristine after all four forked trials.
    if numerical:
        assert context['numerical_policy'].receipt['problem_count'] == 0


def test_changed_paired_result_is_rejected(monkeypatch):
    def fits(operation, args, parallel):
        return [dict(result=bool(parallel), seconds=0., cpu_seconds=0.)] * 2

    monkeypatch.setattr(benchmark, 'fits', fits)
    with pytest.raises(ValueError, match='Complete paired fits'):
        benchmark.measure(None, ({}, [], 'c0', 'joint', .0625), lambda _: None)


def test_child_failure_is_not_a_scientific_rejection():
    def failed(d, targets, arm, method, step):
        if arm == 'fitted_c':
            raise ValueError('failed fitting child')
        return {'arm': arm}

    from leo.operations.localization_v3_parallel import ParallelFitFailure

    with pytest.raises(ParallelFitFailure):
        benchmark.fits(failed, ({}, [], 'c0', 'joint', .0625), True)


def test_serial_and_parallel_receipts_are_ordered_without_audits():
    context = {'numerical_policy': NumericalPolicy()}

    def operation(d, targets, arm, method, step):
        d['numerical_policy'].receipt['optimizer_calls'].append({'arm': arm})
        return arm

    left, right = copy.deepcopy(context), copy.deepcopy(context)
    benchmark.fits(operation, (left, [], 'c0', 'joint', .0625), False)
    benchmark.fits(operation, (right, [], 'c0', 'joint', .0625), True)
    assert left['numerical_policy'].receipt == right['numerical_policy'].receipt
    assert right['numerical_policy'].receipt['optimizer_calls'] == [
        {'arm': 'c0'}, {'arm': 'fitted_c'}]
