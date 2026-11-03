import copy

from evaluate_regression import qualification


def example():
    best = dict(mean=[0., 0., 0., 0., 0.], objectives=[3., 2.], converged=True)
    return (dict(fits=[best], best=best, status='converged_local_mode'),
            dict(timed_out=False, returncode=0, within_budget=True, elapsed_seconds=30.))


def test_acceptance_requires_audit_and_supervised_budget():
    receipt, launch = example()
    assert qualification(receipt, launch, True) == []
    assert 'audit_failed' in qualification(receipt, launch, False)
    for update in [dict(timed_out=True), dict(returncode=1), dict(elapsed_seconds=90.01)]:
        assert 'worker_failed_or_over_budget' in qualification(receipt, launch | update, True)


def test_unresolved_better_mode_cannot_be_hidden_by_converged_seed():
    receipt, launch = example()
    unresolved = copy.deepcopy(receipt['best'])
    unresolved.update(objectives=[1.], converged=False)
    receipt['fits'].append(unresolved)
    assert 'winning_mode_not_converged' in qualification(receipt, launch, True)


def test_invalid_state_and_missing_receipt_not_accepted():
    receipt, launch = example()
    receipt['best']['mean'][0] = 251.
    assert 'invalid_state' in qualification(receipt, launch, True)
    assert qualification({}, launch, True)
