import copy

import numpy as np
import pytest

from recover_ds23_discovery_finalist import reconcile, write, read


def fixture():
    selected = [(float(i), {'seed': {'rows': [i], 'state': np.zeros(2)},
                            'aliases': np.array([i])}) for i in range(3)]
    checkpoint = dict(GPS_used=False, choices=[dict(hypothesis=i, center_score=float(i),
        node={'seed': {'rows': [i], 'state': [0., 0.]}, 'aliases': [i]},
        arms={'c0': {}, 'fitted_c': {}}) for i in range(2)])
    return selected, checkpoint


def test_saved_two_branches_are_prefix_not_complete_search():
    selected, checkpoint = fixture()
    assert len(reconcile(selected, checkpoint)) == 2
    with pytest.raises(ValueError, match='three-finalist'):
        reconcile(selected[:2], checkpoint)


def test_changed_ranked_candidate_or_missing_c_arm_fails_closed():
    selected, checkpoint = fixture()
    changed = copy.deepcopy(checkpoint)
    changed['choices'][1]['node']['aliases'] = [2]
    with pytest.raises(ValueError, match='finalists differ'):
        reconcile(selected, changed)
    changed = copy.deepcopy(checkpoint)
    changed['choices'][1]['arms'].pop('c0')
    with pytest.raises(ValueError, match='complete c pair'):
        reconcile(selected, changed)


def test_reference_seeded_or_out_of_order_checkpoint_is_rejected():
    selected, checkpoint = fixture()
    checkpoint['GPS_used'] = True
    with pytest.raises(ValueError, match='GPS-free'):
        reconcile(selected, checkpoint)
    checkpoint['GPS_used'] = False
    checkpoint['choices'].reverse()
    with pytest.raises(ValueError, match='ordered incomplete prefix'):
        reconcile(selected, checkpoint)


def test_scientific_checkpoint_roundtrips_nested_arrays(tmp_path):
    path = tmp_path / 'checkpoint.json'
    write(path, {'choices': [{'arms': {'c0': {'parameters': np.zeros(2),
                                            'count': np.int64(3)}}}]})
    assert read(path)['choices'][0]['arms']['c0'] == {'parameters': [0., 0.], 'count': 3}
