import numpy as np
import pytest
from phase import masks,designs_for,extract,analyze,wrap

def example(rate):
    return dict(edge='upper',modes=[dict(seeds=[dict(integer_epoch_sample=round(epoch*rate),fractional_epoch_offset_samples=.2,cfo_hz=cfo+rx*678000) for rx in (0,1)]) for epoch,cfo in [(0.00005,-120000),(0.00065,220000)]])

@pytest.mark.parametrize('rate',[2500000,5000000,7500000,10000000])
def test_phase_and_absent_source_all_rates(rate):
    v=example(rate);n=round(rate*.007);d,c=designs_for(v,rate,0,n,[0,0]);t=(np.arange(n)-n/2)/rate
    signal=np.column_stack([sum(d[rx][m].sum(axis=1)*np.exp(1j*rx*(p+2*np.pi*75*t)) for m,p in enumerate([.7,-.5])) for rx in (0,1)])
    out=extract(d,c,signal,rate)
    assert out['both_qualified']
    for m,p in zip(out['modes'],[.7,-.5]):assert abs(wrap(m['evaluation']['phase_rad']-p))<.01
    single=np.column_stack([d[rx][0].sum(axis=1)*np.exp(.7j*rx) for rx in (0,1)])
    rng=np.random.default_rng(43);single+=.15*(rng.normal(size=single.shape)+1j*rng.normal(size=single.shape));out=extract(d,c,single,rate)
    assert out['modes'][0]['qualified'] and not out['modes'][1]['qualified']
    sets,_=masks(n,rate);assert np.all(np.sum(sets,axis=0)==1)
    assert [int(s.sum()) for s in sets]==[round(rate*.0035),round(rate*.00174),round(rate*.00176)]

def test_evaluation_cannot_select_timing_or_qualification():
    rate=2500000;v=example(rate);n=round(rate*.007);d,c=designs_for(v,rate,0,n,[.25,-.25]);signal=np.column_stack([sum(d[rx][m].sum(axis=1)*np.exp(1j*rx*p) for m,p in enumerate([.7,-.5])) for rx in (0,1)])
    a=analyze(signal,v,rate,0);signal[masks(n,rate)[0][2]]+=10; b=analyze(signal,v,rate,0)
    assert a['timing_offsets_samples']==b['timing_offsets_samples']
    assert a['metrics']==b['metrics']
    assert [m['frequency_hz'] for m in a['modes']]==[m['frequency_hz'] for m in b['modes']]

@pytest.mark.parametrize('rate',[2500000,5000000,7500000,10000000])
def test_continuous_rf_oracle(rate):
    from physical_oracle import case
    for edge in ['lower','upper']:
        r=case(rate,edge)
        assert r['both_qualified'] and abs(r['error_rad'])<.02

def test_single_mode_requires_both_receivers():
    rate=2500000;v=example(rate);v['modes']=v['modes'][:1];n=round(rate*.007);d,c=designs_for(v,rate,0,n,[0.]);signal=np.column_stack([d[rx][0].sum(axis=1)*np.exp(.7j*rx) for rx in (0,1)])
    result=extract(d,c,signal,rate)
    assert result['modes'][0]['qualified'] and not result['both_qualified']
    assert abs(wrap(result['modes'][0]['evaluation']['phase_rad']-.7))<.01
    signal[:,1]=0
    assert not extract(d,c,signal,rate)['modes'][0]['qualified']
