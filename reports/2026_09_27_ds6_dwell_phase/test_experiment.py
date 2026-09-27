import numpy as np
import pytest
from experiment import fit_joint,evaluate,frames,phase,refine_window

def synthetic(rate=.13,offset=1.1):
    windows=[]
    for i,mid in enumerate(np.arange(6)*.021+.0035):
        t=np.tile(np.arange(5)/750-.003,2);s=np.repeat([-1,1],5)
        a=.2+i*.7;common=17-2*i
        pred=a+2*np.pi*common*t+s/2*(offset+2*np.pi*rate*(mid+t))
        data={k:dict(t=t.copy(),s=s.copy(),z=np.exp(1j*pred)) for k in ['fit','evaluation']}
        modes=[dict(train=dict(phase_rad=a+sign/2*(offset+2*np.pi*rate*mid)),frequency_hz=common+sign*rate/2) for sign in [-1,1]]
        windows.append(dict(midpoint=mid,data=data,result=dict(modes=modes)))
    return windows

@pytest.mark.parametrize('rate,bound',[(.13,.2),(-.12,.2),(1.3,20.)])
def test_preserves_nonzero_phase_and_slope(rate,bound):
    windows=synthetic(rate)
    out=evaluate(windows,[0,2,5],[1,3,4],bound)
    assert out['held_rms_deg']<1e-4
    assert abs(out['model']['rate']-rate)<1e-5
    assert abs(phase.wrap(out['model']['dd']-(1.1+2*np.pi*rate*out['model']['ref'])))<1e-5

def test_evaluation_cannot_tune_joint_model():
    windows=synthetic();a=fit_joint(windows,[0,2,5],.2)
    for w in windows:w['data']['evaluation']['z']*=np.exp(2j)
    b=fit_joint(windows,[0,2,5],.2)
    assert a==b

def test_common_receiver_offsets_cancel():
    windows=synthetic();base=fit_joint(windows,[0,2,5],.2)
    for i,w in enumerate(windows):
        shift=.4*i
        for d in w['data'].values():d['z']*=np.exp(1j*shift)
        for m in w['result']['modes']:m['train']['phase_rad']+=shift
    changed=fit_joint(windows,[0,2,5],.2)
    assert abs(phase.wrap(base['dd']-changed['dd']))<1e-5
    assert abs(base['rate']-changed['rate'])<1e-5

def test_iq_to_joint_dwell_preserves_slow_phase():
    rate=2500000;n=round(rate*.007);windows=[]
    v=dict(edge='upper',modes=[dict(seeds=[dict(integer_epoch_sample=round(ep*rate),fractional_epoch_offset_samples=.2,cfo_hz=cfo+rx*678000) for rx in (0,1)]) for ep,cfo in [(.00005,-120000),(.00065,220000)]])
    for ms in [0,21,42,63,84,105]:
        start=round(ms*rate/1000);d,c=phase.designs_for(v,rate,start,n,[0,0]);t=(np.arange(n)+start)/rate
        iq=np.column_stack([sum(d[rx][m].sum(axis=1)*np.exp(1j*rx*(p+2*np.pi*(75+m*.13)*t)) for m,p in enumerate([.7,-.5])) for rx in (0,1)])
        result=phase.extract(d,c,iq,rate);result['timing_offsets_samples']=[0,0]
        assert result['both_qualified']
        adjusted,result=refine_window(iq,v,rate,start,result)
        if ms==0:
            changed=iq.copy();changed[phase.masks(n,rate)[0][2]]+=3+2j
            initial_changed=phase.extract(d,c,changed,rate)
            adjusted_changed,refined_changed=refine_window(changed,v,rate,start,initial_changed)
            assert adjusted==adjusted_changed
            assert result['timing_offsets_samples']==refined_changed['timing_offsets_samples']
            assert result['metrics']==refined_changed['metrics']
        windows.append(frames(iq,adjusted,rate,start,result))
    out=evaluate(windows,[0,2,5],[1,3,4],.2)
    assert out['held_rms_deg']<.1
    assert abs(out['model']['rate']-.13)<.005
    assert abs(phase.wrap(out['model']['dd']-(-1.2+2*np.pi*.13*out['model']['ref'])))<.005
