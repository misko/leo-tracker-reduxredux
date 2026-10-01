from copy import deepcopy
import pytest
from failure_composition_checks import comparison_checks


def example():
    fit = dict(seed_index=0, mean=[1., 2.], objectives=[3., 2., 1.],
               converged=False, reason='iteration_limit', iterations=64, associations=[0, 1])
    parent = dict(unit='case', fits=[fit], config=dict(seed_limit=3, max_iterations=64),
                  proposal=dict(seeds=[[1., 2.]], scores=[3.], requested=1, unique_points=1, spacing=1))
    parent.update({k: [] for k in ('binding', 'columns', 'precision', 'inputs', 'height', 'observations', 'model')})
    receipt = dict(deepcopy(parent), status='unresolved', config=dict(seed_limit=1, max_iterations=64))
    receipt['best'] = receipt['fits'][0]
    launch = dict(returncode=0, within_budget=True, timed_out=False,
                  elapsed_seconds=10., external_limit_seconds=90.)
    row = dict(unit='case', accepted=False, fit_status='unresolved',
               failures=['AssertionError: unresolved'], error_m=None)
    outcome = dict(launch=launch, audit_launch=deepcopy(launch), evaluation=dict(rows=[row]))
    return {a: deepcopy(receipt) for a in ('original', 'blas')}, parent, {
        a: deepcopy(outcome) for a in ('original', 'blas')}


def test_matching_completed_iteration_limit_fits_pass_equivalence_only():
    assert all(comparison_checks(*example()).values())


@pytest.mark.parametrize('field,value', [
    ('mean', [1., 2.01]), ('objectives', [3., 2.01, 1.]),
    ('associations', [1, 1]), ('iterations', 63), ('reason', 'deadline'),
])
def test_matching_rejection_does_not_hide_changed_trajectory(field, value):
    receipts, parent, outcomes = example()
    receipts['blas']['fits'][0][field] = value
    assert not all(comparison_checks(receipts, parent, outcomes).values())


def test_timeout_missing_receipt_and_wrong_audit_cannot_pass():
    for mutation in ('timeout', 'missing', 'error', 'reason', 'accepted', 'proposal', 'binding'):
        receipts, parent, outcomes = example()
        if mutation == 'timeout': outcomes['blas']['launch']['timed_out'] = True
        elif mutation == 'missing': receipts['blas'] = None
        elif mutation == 'error': outcomes['blas']['evaluation']['rows'][0]['error_m'] = 10.
        elif mutation == 'reason': outcomes['blas']['evaluation']['rows'][0]['failures'] = ['bad seal']
        elif mutation == 'accepted': outcomes['blas']['evaluation']['rows'][0]['accepted'] = True
        elif mutation == 'proposal': receipts['blas']['proposal']['scores'][0] += .01
        elif mutation == 'binding': receipts['blas']['observations'] = ['different']
        assert not all(comparison_checks(receipts, parent, outcomes).values()), mutation
