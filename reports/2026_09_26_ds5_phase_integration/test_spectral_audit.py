from pathlib import Path
import json
import numpy as np
from spectral_audit import fit_delay
from joint_mode_audit import regression

HERE=Path(__file__).resolve().parent/'spectral-audit'

def test_delay_fit_preserves_carrier_pivot_phase():
    f=np.arange(8)*234375.;f-=f.mean();delay=46e-9;phase=.73
    z=np.exp(1j*(phase+2*np.pi*f*delay))
    recovered,boundary=fit_delay(z,f)
    assert not boundary and abs(recovered-delay)<1e-12
    assert abs(np.angle(np.sum(z*np.exp(-2j*np.pi*f*recovered)))-phase)<1e-10

def test_held_samples_do_not_fit_regression_coefficients():
    rng=np.random.default_rng(2);X=rng.normal(size=(100,4))+1j*rng.normal(size=(100,4));beta=np.array([1,.2j,.3,0]);train=np.arange(100)%2==0;y=X@beta
    a,_=regression(X,y,train);y[~train]+=100
    b,_=regression(X,y,train)
    assert np.allclose(a,b) and np.allclose(a,beta)

def test_joint_model_rejects_absent_synthetic_mode():
    d=json.loads((HERE/'joint-mode-results.json').read_text())
    assert len(d['real'])==8 and len(d['synthetic'])==6
    for row in d['synthetic']:
        for m in row['metrics']:
            expected=1 if row['source']=='both' or row['source']==m['mode'] else 0
            assert abs(m['joint_coefficient_power']-expected)<1e-10

def test_high_R_can_be_single_source_leakage():
    d=json.loads((HERE/'single-source-injections.json').read_text())
    false=[r for r in d['rows'] if r['synthetic_snr_db'] is None and r['source_mode']!=r['extracted_mode']]
    assert len(false)==4
    assert all(r['held_R']>.999 for r in false)
    assert any(min(r['held_exact_control_ratios'])>2 for r in false)

def test_real_spectral_accounting():
    for sid in ('scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'):
        d=json.loads((HERE/(sid+'.json')).read_text())
        assert len(d['rows'])==216 and len(d['template_overlaps'])==108
        assert len({(r['visit'],r['start_ms'],r['mode']) for r in d['rows']})==216
        assert all(len(r['held_complex'])==8 for r in d['rows'])
