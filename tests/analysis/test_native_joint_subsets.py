import pytest
from run_native_joint_subsets import nonoverlapping_subsets


def test_enumeration_preserves_conflicting_alternatives_but_never_double_owns():
    rows=[dict(branch_id='a',observation_ids=['1','2','3']),
          dict(branch_id='b',observation_ids=['1','4']),dict(branch_id='c',observation_ids=['2','5'])]
    found=nonoverlapping_subsets(rows)
    assert found==[dict(branch_ids=['a'],points=3),dict(branch_ids=['b'],points=2),dict(branch_ids=['c'],points=2),dict(branch_ids=['b','c'],points=4)]
    assert nonoverlapping_subsets(rows[::-1])==found
    with pytest.raises(ValueError,match='duplicate'):nonoverlapping_subsets([dict(branch_id='d',observation_ids=['1','1'])])


def test_policy_uses_gate_and_unique_coverage_not_evaluation_error():
    from run_native_joint_subsets import select_valid_subset
    rows=[dict(branch_ids=['a'],points=50,paired_valid=False,error_km=.01),
          dict(branch_ids=['b','c'],points=40,paired_valid=True,error_km=.02),
          dict(branch_ids=['d'],points=40,paired_valid=True,error_km=3.)]
    assert select_valid_subset(rows)['branch_ids']==['d']
    assert select_valid_subset([rows[0]]) is None
