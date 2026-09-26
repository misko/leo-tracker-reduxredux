from pathlib import Path
import json
import numpy as np
from long_overlap_predict import score

HERE=Path(__file__).resolve().parent/'long-overlap'

def test_complete_window_and_control_accounting():
    plan=json.loads((HERE/'plan.json').read_text())
    total=0
    for scan in plan['scans']:
        data=json.loads((HERE/(scan['session_id']+'.json')).read_text())
        assert not data['errors']
        expected={(v['visit'],m,s) for v in scan['selected'] for m in (0,1) for s in plan['starts_ms']}
        actual=[(r['visit'],r['mode'],r['start_ms']) for r in data['rows']]
        assert len(actual)==len(set(actual)) and set(actual)==expected
        total+=len(actual)
    assert total==432
    control=json.loads((HERE/'shifted-controls.json').read_text())
    assert len(control['rows'])==48
    assert all(r['median_exact_held_R']>r['median_shifted_held_R'] for r in control['summary'])

def test_rate_evidence_invariant_to_unknown_constant():
    t=np.linspace(0,22,18);y=np.radians(3*t);train=np.arange(18)%2==0
    a=score(y,t,train,2,5);b=score(y+1.77,t,train,2,5)
    for key in a:assert np.isclose(a[key],b[key],atol=1e-12)
    assert a['gain_vs_constant']>0

def test_zero_rate_prior_is_constant_model():
    t=np.linspace(0,22,18);y=np.sin(t);train=np.arange(18)%2==0
    assert abs(score(y,t,train,1,0)['gain_vs_constant'])<1e-12

def test_prediction_partitions_keep_dwell_groups_together():
    plan=json.loads((HERE/'plan.json').read_text())
    results=json.loads((HERE/'prediction.json').read_text())
    byid={s['session_id']:s for s in plan['scans']}
    for result in results['scans']:
        scan=byid[result['session_id']];assignments={}
        assert result['visit_ids']==[v['visit'] for v in scan['selected']]
        for v,train in zip(scan['selected'],result['fold0_training']):
            group=v['valid_start_counter']//10_000_000
            assert group not in assignments or assignments[group]==train
            assignments[group]=train
        assert 0<sum(result['fold0_training'])<len(result['visit_ids'])
