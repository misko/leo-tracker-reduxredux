from pathlib import Path
import copy,json
import numpy as np
from support_calibration import fit,predict
from timing_trial import evaluate
from test_timing_trial import option

def test_excluded_scan_cannot_train_uncertainty():
    rows=[dict(session_id=s,feature=x,error_rad=e) for s in ('a','b','held') for x,e in [(0.01,1.5),(.1,.6),(.3,.1)]]
    a=fit(rows,'held');modified=copy.deepcopy(rows)
    for row in modified:
        if row['session_id']=='held':row.update(feature=100,error_rad=3)
    b=fit(modified,'held')
    assert a==b
    assert np.all(np.diff(predict(a['parameters'],np.linspace(0,1,20)))>=0)
    assert a['development_scans']==['a','b']

def test_constant_kappa_vector_matches_scalar():
    y=np.array([.1,.2,.4,.5]);train=np.array([1,0,1,0],bool);f=np.full(4,11.2e9)
    a=[option('a',[[0,.1,.2,.3]],-.5)];b=[option('b',[[0,.2,.4,.6]],-.2)]
    scalar=evaluate(a,b,y,train,f,f,1,n_baseline=5)
    vector=evaluate(a,b,y,train,f,f,np.ones(4),n_baseline=5)
    for key in ('cfo_gain','phase_held_vs_uniform','phase_gain_vs_constant'):
        assert np.isclose(scalar[key],vector[key],atol=1e-12)

def test_real_calibrations_exclude_target_scan_and_keep_all_arms():
    root=Path(__file__).resolve().parent/'support-trial'
    results=[p for p in root.glob('scan-fw-*.json') if '-protocol' not in p.name]
    assert len(results)==2
    for path in results:
        d=json.loads(path.read_text());p=d['protocol']
        assert p['excluded_scan'] not in p['calibration']['development_scans']
        assert len(d['experiments'])==12
        for e in d['experiments']:
            if e['arm']=='support_calibrated':assert len(e['kappa'])==18
            assert np.isfinite(e['cfo_gain'])
