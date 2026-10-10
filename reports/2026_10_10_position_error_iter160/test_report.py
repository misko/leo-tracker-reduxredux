import copy
import pytest
from report import audit_groups


def fixture():
    rows=[dict(visit_index=i,device_sample_start=i*10,device_sample_end=i*10+5,
               support_center_ns=i*10+2,receiver=i%2) for i in range(4)]
    return {'rows':rows},{'folds':{'0':[0,1],'1':[2,3]},'row_fold':[0,0,1,1]}


def test_partition_receiver_coverage_and_span():
    support,group=fixture();original=copy.deepcopy(support)
    result=audit_groups(support,group)
    assert result['0']['0']==dict(training_rows=1,held_rows=1,held_outside_training_center_span=1)
    assert support==original


@pytest.mark.parametrize('fault',['duplicate','assignment','visit','overlap'])
def test_independent_audit_rejects_corruption(fault):
    support,group=fixture()
    if fault=='duplicate':group['folds']['1']=[1,3]
    if fault=='assignment':group['row_fold'][0]=1
    if fault=='visit':support['rows'][2]['visit_index']=0
    if fault=='overlap':support['rows'][1]['device_sample_end']=25
    with pytest.raises(ValueError):audit_groups(support,group)
