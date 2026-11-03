from probe_ds23_refined_joint_search import combinations


def test_joint_search_permits_swaps_that_cannot_be_valid_single_replacements():
    pools={1:[dict(target=2,changes=[{'row_index':0,'candidate_index':2}])],
           2:[dict(target=1,changes=[{'row_index':1,'candidate_index':1}])]}
    ops=combinations(pools,[1,2,3])
    assert len(ops)==1 and ops[0]['families']==[1,2]
    assert len(ops[0]['changes'])==2


def test_joint_search_keeps_independent_families_distinct_and_enumerates_all_orders():
    pools={1:[dict(target=4,changes=[{'candidate_index':4}])],2:[dict(target=5,changes=[{'candidate_index':5}])]}
    ops=combinations(pools,[1,2,3])
    assert sorted(len(r['families']) for r in ops)==[1,1,2]
    assert combinations({1:[dict(target=3,changes=[])]},[1,2,3])==[]
