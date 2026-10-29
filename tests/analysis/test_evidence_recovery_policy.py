from run_evidence_recovery_policy import choose_preserving_subset


def test_maximum_coverage_preserves_point_owners_without_using_position_error():
    rows=[dict(branch_id='old',observation_ids=['a','b'],norad=1,error=0),
          dict(branch_id='extend',observation_ids=['a','b','c'],norad=1,error=100),
          dict(branch_id='wrong',observation_ids=['a','b','c','d'],norad=2,error=0),
          dict(branch_id='separate',observation_ids=['d'],norad=3,error=100)]
    chosen,conflicts=choose_preserving_subset(rows,{'a':1,'b':1})
    assert chosen==dict(branch_ids=['extend','separate'],points=4)
    assert conflicts==['wrong']


def test_incomplete_replacement_does_not_drop_previously_supported_points():
    rows=[dict(branch_id='old',observation_ids=['a','b'],norad=1),
          dict(branch_id='partial',observation_ids=['b','c','d'],norad=1)]
    chosen,_=choose_preserving_subset(rows,{'a':1,'b':1})
    assert chosen['branch_ids']==['old']
