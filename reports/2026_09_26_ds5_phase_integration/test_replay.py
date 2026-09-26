from pathlib import Path
import json
import hashlib
import numpy as np
import pilot_extract as E
from run import split,summarize

HERE=Path(__file__).resolve().parent

def test_extractor_recovers_known_midpoint_phase_with_large_receiver_offset():
    rate=10_000_000;mid=35000.;epoch=800.2
    iq=np.zeros((70000,2),complex);base=E.qin_edge_pilot_frame(rate,'lower')
    for index in range(6):
        floating=epoch+index*rate/750;start=round(floating)
        if start+len(base)>len(iq):continue
        template=E.fractional_shift(base,floating-start)
        t=(start+np.arange(len(base))-mid)/rate
        for rx,f in enumerate((100000.,778000.)):
            iq[start:start+len(base),rx]=template*np.exp(1j*(2*np.pi*f*t+rx*.7))
    seeds=[dict(receiver_id=rx,integer_epoch_sample=800,fractional_epoch_offset_samples=.2,tracking_absolute_baseband_cfo_hz=f) for rx,f in enumerate((100000.,778000.))]
    train,held,_=split();r=E.extract_candidate(iq,'lower',seeds,0,70000,[0.],train,held)
    measured=summarize(r,r['alternatives'][0],len(train))['coefficients']
    assert abs(float(E.wrap(measured['held']['phase_rad']-.7)))<.01
    assert measured['held']['R']>.999

def test_real_selection_and_group_denominators():
    plan=json.loads((HERE/'plan.json').read_text());assert len(plan['scans'])==3
    total=0
    for s in plan['scans']:
        data=json.loads((HERE/(s['session_id']+'.json')).read_text())
        assert data['plan_sha256']==hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
        expected=6*sum(len(v['modes']) for v in s['selected'])
        assert len(data['rows'])+len(data['errors'])==expected
        assert len(data['chunk_audits'])==len(s['selected'])
        for r in data['rows']:
            v=next(v for v in s['selected'] if v['visit']==r['visit'])
            assert r['partition']==v['partition']
        total+=len(data['rows'])
    assert total==324

def test_training_symbol_groups_disjoint_and_guarded():
    train,held,blocks=split();assert not set(train)&set(held)
    for b in range(10):
        support=set(range(4+30*b,30*b+30))
        assert support<=set(held if b in blocks else train)
