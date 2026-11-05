from copy import deepcopy

import pytest
from compare_algo07v3_inventory import compare


def test_inventory_comparison_catches_owner_and_prior_solver_changes():
    reference = dict(owners=dict(c0={'point':123}), selected_targets=['curve'],
                     baseline_objective_replay={'c0':{'type':'float', 'hex':0.0.hex()}})
    prefix = dict(cavity_policy={'selected':True})
    candidate = dict(prefix, recovery_inventory=deepcopy(reference))
    assert compare(reference, candidate, prefix)['exact']
    candidate['recovery_inventory']['owners']['c0']['point'] = 456
    with pytest.raises(ValueError, match='owners'):
        compare(reference, candidate, prefix)
    candidate['recovery_inventory'] = reference
    with pytest.raises(ValueError, match='Preceding cavity'):
        compare(reference, candidate, {'cavity_policy':{}})
