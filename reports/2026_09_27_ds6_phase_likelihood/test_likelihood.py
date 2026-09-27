import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
spec=importlib.util.spec_from_file_location('likelihood',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_common_phase_integral_matches_direct_quadrature():
    z=np.exp(1j*np.array([.4,.8,-1.,-.5]));s=np.array([-1,-1,1,1]);d=1.2;k=4.;a=z[s==-1].sum();b=z[s==1].sum();phi=np.linspace(-np.pi,np.pi,20000,endpoint=False)
    direct=logsumexp(k*np.real(np.exp(-1j*phi)*(a+b*np.exp(-1j*d))))-np.log(len(phi))
    assert abs(direct-m.log_i0(k*abs(a+b*np.exp(-1j*d))))<1e-12


def test_integrating_dd_agrees_with_two_free_phase_evidence():
    t=np.array([-.002,-.0005,.001,.0025]*2);s=np.repeat([-1,1],4);z=np.exp(1j*(2*np.pi*37*t+.8*s));f=np.linspace(-375,375,751);d=np.linspace(-np.pi,np.pi,720,endpoint=False);k=16
    a,b=m.sums(t,z,s,f);w=np.ones(len(f));w[[0,-1]]=.5;w/=w.sum()
    explicit=logsumexp(m.log_i0(k*abs(a[:,None]+b[:,None]*np.exp(-1j*d)))-len(t)*m.log_i0(k)+np.log(w)[:,None])-np.log(len(d))
    assert abs(explicit-m.evidence((t,z,s),k,f))<1e-10
    p=m.posterior((t,z,s),k,f,d);assert abs(m.base.wrap(p['mean_dd_rad']-1.6))<.001
    assert abs(sum(p['probability'])-1)<1e-12


def test_gauge_invariance_and_source_exchange():
    t=np.linspace(-.003,.003,10);s=np.where(np.arange(10)%2,1,-1);z=np.exp(1j*(2*np.pi*23*t+.6*s));f=np.linspace(-375,375,751);d=np.linspace(-np.pi,np.pi,720,endpoint=False)
    a=m.posterior((t,z,s),4,f,d);b=m.posterior((t,z*np.exp(1j*1.1),s),4,f,d);c=m.posterior((t,z,-s),4,f,d)
    np.testing.assert_allclose(a['probability'],b['probability'],atol=1e-12)
    assert abs(m.base.wrap(a['mean_dd_rad']+c['mean_dd_rad']))<1e-10


def test_completed_membership_and_normalization():
    root=Path(__file__).resolve().parent;result=json.loads((root/'results.json').read_text());protocol=json.loads((root/'protocol.json').read_text());pool=json.loads((root/'pool-results.json').read_text())
    assert result['complete'] and pool['complete']
    assert result['protocol_sha256']==hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()
    count=0
    for scan in result['scans']:
        path=root.parent/'2026_09_27_ds6_phase_curvature'/(scan['session_id']+'-frames.json');assert hashlib.sha256(path.read_bytes()).hexdigest()==protocol['source_hashes'][scan['session_id']]
        original=json.loads(path.read_text());key=lambda w:(w['visit'],w['group'],w['start_ms'])
        assert {key(w) for w in original}=={key(w) for w in scan['windows']}
        count+=len(scan['windows'])
        for w in scan['windows']:
            for arm in w['arms'].values():assert abs(sum(arm['probability'])-1)<1e-10
    assert count==75 and len(pool['rows'])==16
    for r in pool['rows']:
        assert not set(r['train_starts_ms'])&set(r['held_starts_ms'])
        if 'phase_probability' in r:assert abs(sum(r['phase_probability'])-1)<1e-10
