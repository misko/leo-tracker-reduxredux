from pathlib import Path
import json
import numpy as np
from joint_phase import masks,extract,common_frequency
from joint_phase_run import build
from physical_phase_audit import case

HERE=Path(__file__).resolve().parent

def test_common_rate_preserves_independent_phase_intercepts():
    t=[np.array([.001,.002,.003,.004]),np.array([.0013,.0023,.0033,.0043])]
    z=[np.exp(1j*(p+2*np.pi*75*(x-.0035))) for p,x in zip([.7,-1.2],t)]
    assert abs(common_frequency(z,t,.0035)-75)<1e-5
    assert abs(common_frequency([z[0]*np.exp(1.8j),z[1]*np.exp(-2.7j)],t,.0035)-75)<1e-5

def test_shared_rate_does_not_use_evaluation_samples():
    scan=next(s for s in json.loads((HERE/'long-overlap/plan.json').read_text())['scans'] if s['selected']);old=json.loads((HERE/'long-overlap'/(scan['session_id']+'.json')).read_text())['rows'];d,c=build(scan['selected'][0],old,0)
    t=(np.arange(70000)-35000)/1e7
    iq=np.column_stack([sum(d[rx][m].sum(axis=1)*np.exp(1j*rx*(.7-m+2*np.pi*75*t)) for m in (0,1)) for rx in (0,1)])
    a=extract(d,c,iq,shared_frequency=True);evaluation=masks()[0][2];rng=np.random.default_rng(94);iq[evaluation]+=100*(rng.normal(size=iq[evaluation].shape)+1j*rng.normal(size=iq[evaluation].shape));b=extract(d,c,iq,shared_frequency=True)
    assert a['metrics']==b['metrics']
    assert [r['frequency_hz'] for r in a['modes']]==[r['frequency_hz'] for r in b['modes']]

def test_physical_geometric_phase_survives_shared_rate_fit():
    r=case(.6,63,shared_frequency=True,geometric_rates_hz=(-.25,.25))
    assert r['both_qualified'] and abs(r['error_rad'])<.01
