"""Optimizer accounting uses tiny fake fits without native or corpus access."""

import json
import multiprocessing
import os
from copy import deepcopy
from types import SimpleNamespace

import pytest

from leo.contracts.localization_v5 import annotation_training_policy
from leo.operations.localization_v5_training import ProcessTrainingFit, validate_provenance


def fit(problem, *args, **kwargs):
    problem.residual(0)
    problem.residual(1)
    return dict(parameters=[51.0, -1.0], history=[dict(parameters=[51.0, -1.0])],
                evaluations=2, converged=None, reference_fit_completed=True, budget_exhausted=False,
                stopped='primary unsuccessful', scipy_result=dict(success=False, status=2),
                score_correction=None,
                fallback=dict(attempted=True, completed=True, evaluations=1, stopped='completed'),
                attempts=[dict(optimizer='lbfgsb', evaluations=1, converged=False,
                               score_correction=dict(reason='restored score', reported_score=4.,
                                                     recorded_score=3.,
                                                     additional_residual_evaluations=0)),
                          dict(optimizer='original_gn', evaluations=1)])


fit.policy = annotation_training_policy()


def problem():
    return SimpleNamespace(residual=lambda value: [value])


def child_call(wrapper):
    wrapper(problem())


def test_receipts_preserve_attempts_and_drop_parameters(tmp_path):
    wrapper = ProcessTrainingFit(fit, tmp_path)
    policy = wrapper.policy
    policy['options']['maxiter'] = 0
    assert wrapper.policy['options']['maxiter'] == 48
    returned = wrapper(problem())
    assert returned['parameters'] == [51., -1.]
    work = wrapper.provenance()
    counts = work['counts']
    assert [counts[key] for key in ('started', 'completed', 'failed', 'evaluations')] == (
        [1, 1, 0, 2])
    assert counts['optimizer_attempts'] == 2
    assert counts['primary_failures'] == counts['score_corrections'] == 1
    assert counts['fallback_attempted'] == counts['fallback_completed'] == 1
    result = work['receipts'][0]['fits'][0]['result']
    assert result['scipy_result'] == dict(success=False, status=2)
    assert result['converged'] is None
    assert result['score_correction'] is None
    assert result['attempts'][0]['score_correction']['recorded_score'] == 3.
    assert result['attempts'][1]['optimizer'] == 'original_gn'
    assert 'parameters' not in json.dumps(work)
    assert list(tmp_path.glob('*.json')) == []
    assert len(list((tmp_path / 'annotation-training').glob('*.json'))) == 1
    assert list((tmp_path / 'annotation-training').glob('*.partial')) == []


def test_failure_retains_physical_calls_and_propagates_original_error(tmp_path):
    error = RuntimeError('private data must not enter the receipt')

    def fails(problem):
        problem.residual(0)
        raise error

    fails.policy = fit.policy
    wrapper = ProcessTrainingFit(fails, tmp_path)
    with pytest.raises(RuntimeError) as caught:
        wrapper(problem())
    assert caught.value is error
    work = wrapper.provenance()
    assert work['counts']['failed'] == work['counts']['evaluations'] == 1
    assert work['counts']['completed'] == work['counts']['optimizer_attempts'] == 0
    assert work['counts']['optimizer_attempts_unknown_fits'] == 1
    assert work['receipts'][0]['fits'] == [
        dict(state='failed', evaluations=1, error_type='RuntimeError')]
    assert 'private data' not in json.dumps(work)


def test_forked_worker_does_not_repeat_inherited_parent_records(tmp_path):
    wrapper = ProcessTrainingFit(fit, tmp_path)
    wrapper(problem())
    child = multiprocessing.get_context('fork').Process(target=child_call, args=(wrapper,))
    child.start()
    child.join(timeout=5)
    assert child.exitcode == 0
    work = wrapper.provenance()
    assert {receipt['pid'] for receipt in work['receipts']} == {os.getpid(), child.pid}
    assert [len(receipt['fits']) for receipt in work['receipts']] == [1, 1]
    assert work['counts']['completed'] == 2
    assert work['counts']['evaluations'] == 4


def test_abrupt_worker_exit_leaves_explicit_in_progress_receipt(tmp_path):
    def exits(problem):
        os._exit(3)

    exits.policy = fit.policy
    wrapper = ProcessTrainingFit(exits, tmp_path)
    child = multiprocessing.get_context('fork').Process(target=child_call, args=(wrapper,))
    child.start()
    child.join(timeout=5)
    assert child.exitcode == 3
    work = wrapper.provenance()
    assert work['counts']['started'] == work['counts']['in_progress'] == 1
    assert work['counts']['completed'] == work['counts']['failed'] == 0
    assert work['counts']['optimizer_attempts_unknown_fits'] == 1


@pytest.mark.parametrize('change', ['binding', 'pid', 'counts', 'parameters', 'evaluations'])
def test_receipt_tampering_is_rejected(tmp_path, change):
    wrapper = ProcessTrainingFit(fit, tmp_path)
    wrapper(problem())
    receipt_path, = (tmp_path / 'annotation-training').glob('*.json')
    receipt = json.loads(receipt_path.read_text())
    if change == 'binding':
        receipt['policy_sha256'] = 'sha256:' + '0' * 64
    elif change == 'pid':
        receipt['pid'] += 1
    elif change == 'counts':
        receipt['counts']['evaluations'] += 1
    elif change == 'evaluations':
        receipt['fits'][0]['evaluations'] = True
    else:
        receipt['fits'][0]['result']['parameters'] = [51., -1.]
    receipt_path.write_text(json.dumps(receipt))
    wrapper.pid = None
    with pytest.raises(ValueError):
        wrapper.provenance()


def test_saved_provenance_requires_exact_policy_and_counts(tmp_path):
    wrapper = ProcessTrainingFit(fit, tmp_path)
    wrapper(problem())
    value = wrapper.provenance()
    assert validate_provenance(value, wrapper.policy) is value
    changed = deepcopy(value)
    changed['policy']['options']['maxiter'] = 48.
    with pytest.raises(ValueError):
        validate_provenance(changed, wrapper.policy)
    changed = deepcopy(value)
    changed['counts']['completed'] = True
    with pytest.raises(ValueError):
        validate_provenance(changed, wrapper.policy)


def test_incomplete_atomic_file_cannot_replace_a_complete_receipt(tmp_path):
    wrapper = ProcessTrainingFit(fit, tmp_path)
    wrapper(problem())
    path, = (tmp_path / 'annotation-training').glob('*.json')
    path.with_suffix('.partial').write_text('{incomplete')
    wrapper.pid = None
    work = wrapper.provenance()
    assert work['counts']['completed'] == 1
    assert work['counts']['evaluations'] == 2


def test_count_mismatch_is_operational_failure(tmp_path):
    def mismatched(problem):
        problem.residual(0)
        return dict(evaluations=0)

    mismatched.policy = fit.policy
    wrapper = ProcessTrainingFit(mismatched, tmp_path)
    with pytest.raises(ValueError, match='physical residual'):
        wrapper(problem())
    assert wrapper.provenance()['counts']['failed'] == 1


def test_qnap_work_receipts_are_forbidden():
    with pytest.raises(ValueError, match='QNAP'):
        ProcessTrainingFit(fit, '/mnt/qnap01/no-write')
