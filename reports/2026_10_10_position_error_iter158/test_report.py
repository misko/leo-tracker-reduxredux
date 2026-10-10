"""Postseal reporter must not turn missing or inconsistent coverage into success."""
import json
import pytest
from report import collect


def fixture(tmp_path):
    plan={'members':[{'label':'x','dataset':'DS16'}]}
    d={'status':'unresolved','axes':{'0':{'status':'budget_exhausted'},'1':{'status':'unattempted'}},
       'calls':[{'called':True,'objective_elapsed_s':.1}],'actual_joint_calls':1,'elapsed_s':1.}
    row={'label':'x','protocol_sha256':'hash','status':'failed','matched_model':True,'elapsed_s':3.,
         'arms':{arm:{'status':'unresolved','diagnostic':d} for arm in ('fitted-c','zero-c')}}
    (tmp_path/'x.claim.json').write_text(json.dumps({'label':'x','protocol_sha256':'hash'}))
    (tmp_path/'x.json').write_text(json.dumps(row))
    return plan,row


def test_partial_axes_are_retained_without_fabricated_width(tmp_path):
    plan,_=fixture(tmp_path)
    result=collect(plan,'hash',tmp_path)
    assert len(result['rows'])==2
    assert all(r['combined_log_width'] is None and r['status']=='unresolved' for r in result['rows'])
    assert all(r['axis_status']==['budget_exhausted','unattempted'] for r in result['rows'])


@pytest.mark.parametrize('corruption',['missing_arm','wrong_digest','call_count'])
def test_inconsistent_terminal_rejected(tmp_path,corruption):
    plan,row=fixture(tmp_path)
    if corruption=='missing_arm':del row['arms']['zero-c']
    if corruption=='wrong_digest':row['protocol_sha256']='foreign'
    if corruption=='call_count':row['arms']['fitted-c']['diagnostic']['actual_joint_calls']=7
    (tmp_path/'x.json').write_text(json.dumps(row))
    with pytest.raises(ValueError):collect(plan,'hash',tmp_path)
