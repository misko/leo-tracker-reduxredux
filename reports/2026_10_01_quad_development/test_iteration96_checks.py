from copy import deepcopy
from iteration96_checks import compare


def fixture(converged):
    fit = dict(seed_index=0, mean=[1., 2.], objectives=[100.-i for i in range(65 if not converged else 6)],
               converged=converged, reason='objective_stable' if converged else 'iteration_limit',
               iterations=5 if converged else 64, associations=[0, 1])
    parent = dict(unit='case', config=dict(seed_limit=1, max_iterations=64), fits=[fit], best=fit,
        proposal=dict(seeds=[[1., 2.]], scores=[3.], requested=1, unique_points=1, spacing=1))
    parent.update({k: [] for k in ('binding', 'columns', 'precision', 'inputs', 'height', 'observations', 'model')})
    new = deepcopy(parent); new['config']['max_iterations'] = 96
    new['status'] = 'converged_local_mode' if converged else 'unresolved'
    return parent, new


def test_converged_control_stays_unchanged():
    parent, new = fixture(True)
    assert all(compare(parent, new).values())
    new['best']['mean'][0] += .01
    assert not all(compare(parent, new).values())


def test_failed_prefix_can_continue_but_cannot_be_rewritten():
    parent, new = fixture(False)
    new['best']['objectives'].extend([35., 34.])
    new['best'].update(iterations=66, converged=True, reason='objective_stable', associations=[1, 1])
    new['status'] = 'converged_local_mode'
    assert all(compare(parent, new).values())
    new['best']['objectives'][4] += .01
    assert not all(compare(parent, new).values())


def test_wrong_cap_proposal_and_missing_fit_fail_even_with_unchanged_state():
    for variant in ('cap', 'proposal', 'missing'):
        parent, new = fixture(True)
        if variant == 'cap': new['config']['max_iterations'] = 128
        elif variant == 'proposal': new['proposal']['scores'][0] += .01
        else: new['fits'] = []
        assert not all(compare(parent, new).values()), variant
