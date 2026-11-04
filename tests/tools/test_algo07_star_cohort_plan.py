import copy

import pytest
from plan_algo07_star_cohort import plan


def inventory():
    return dict(kind='algo07-star-cohort-input-inventory', fast_members=3, members=[
        dict(dataset_label=f'DS26-{i:04d}', recording_id=f'scan-{i}',
             run_id=f'run-{i}' if i < 3 else None,
             input_sha256='sha256:'+str(i)*64 if i < 3 else None,
             availability='available' if i < 3 else 'no_native_run') for i in range(1, 4)])


def test_every_member_is_accounted_for_without_fit_outcome_selection():
    result = plan(inventory(), seed=123)
    assert result['fast_members'] == 3
    assert result['available_members'] == 2
    assert result['unavailable_members'] == 1
    assert set(result['execution_order']) == {'DS26-0001', 'DS26-0002'}
    assert len(result['members']) == 3
    assert not result['performance_comparison']
    assert not result['ds26_equivalence_verified']


def test_order_is_reproducible_independent_of_input_row_order():
    source = inventory()
    other = copy.deepcopy(source)
    other['members'].reverse()
    assert plan(source, seed=123)['execution_order'] == plan(other, seed=123)['execution_order']


def test_duplicate_identity_and_missing_input_are_rejected():
    source = inventory()
    source['members'][1]['recording_id'] = source['members'][0]['recording_id']
    with pytest.raises(ValueError, match='unique'):
        plan(source, seed=123)
    source = inventory()
    source['members'][0]['input_sha256'] = None
    with pytest.raises(ValueError, match='exact native'):
        plan(source, seed=123)


def test_case_label_cannot_escape_research_root():
    source = inventory()
    source['members'][0]['dataset_label'] = '../outside'
    with pytest.raises(ValueError, match='DS26 fast'):
        plan(source, seed=123)
