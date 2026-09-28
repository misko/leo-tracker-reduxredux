from copy import deepcopy
import numpy as np
import pytest
from compare_scan_clock import compare


def inputs():
    def row(tid,cid,tau,rms,cfo):
        return dict(track_id=tid,candidate_id=cid,tau_s=tau,training_rms_hz=rms,reserved_rms_hz=rms,cfo_hz=cfo)
    return [(10,np.array([-1,1]),[row('a','1',-1,1,100),row('a','2',1,10,200)]),
            (20,np.array([-1,1]),[row('b','3',-1,10,300),row('b','4',1,1,400)])]


def test_shared_tau_keeps_distinct_track_identities_and_offsets():
    result=compare(inputs(),'s')
    free=result['per_track']['scans'][0]['tracks']
    shared=result['one_per_scan']['scans'][0]['tracks']
    assert [r['tau_s'] for r in free]==[-1,1]
    assert [r['tau_s'] for r in shared]==[1,1]
    assert [r['candidate_id'] for r in shared]==['2','4']
    assert [r['cfo_hz'] for r in shared]==[200,400]
    assert result['changed_identities']==1
    assert result['one_per_scan']['fixed_weight_seconds']==30


def test_evaluation_error_cannot_select_shared_clock():
    a=inputs(); b=deepcopy(a)
    for _,_,rows in b:
        for row in rows: row['reserved_rms_hz']=700 if row['tau_s']==1 else 0
    x,y=compare(a,'s'),compare(b,'s')
    assert x['one_per_scan']['scans'][0]['clock_tau_s']==y['one_per_scan']['scans'][0]['clock_tau_s']
    assert y['one_per_scan']['reserved_capped_weighted_rms_hz']==pytest.approx(700)
