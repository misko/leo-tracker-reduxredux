import numpy as np
import pytest

from predictive_uniqueness import conditional_uniqueness
import validate_replacements as validation
from validate_replacements import predict, partitions
from predictive_check import fit_predict


def fixture():
    parts = [dict(fold=i,held_blocks=[i*3]) for i in range(5)]
    rows = [dict(arm=a,fold=i,norad=n,model='receiver_offset',phase_sd_s=5.,predictive_score=score)
            for a in ('c0','fitted_c') for i in range(5)
            for n,score in [(10,3.),(20,1.),(30,2.)]]
    return rows,parts


def test_requires_all_matched_competitors_not_only_incumbent():
    rows,parts=fixture()
    assert conditional_uniqueness(rows,parts,[10,20,30],20)['passed']
    # 30 beats incumbent10 but loses to20.
    assert conditional_uniqueness(rows,parts,[10,20,30],30)['status']=='rejected'


def test_zero_margin_is_strict_and_missing_is_not_a_failed_match():
    rows,parts=fixture()
    rows[2]['predictive_score']=1.
    assert conditional_uniqueness(rows,parts,[10,20,30],20)['minimum_margin']==0.
    assert not conditional_uniqueness(rows,parts,[10,20,30],20)['passed']
    assert conditional_uniqueness(rows[:-1],parts,[10,20,30],20)['status']=='not_evaluated'


def test_duplicate_held_partitions_do_not_inflate_evidence():
    rows,parts=fixture()
    parts[-1]['held_blocks']=parts[0]['held_blocks']
    result=conditional_uniqueness(rows,parts,[10,20,30],20)
    assert result['unique_folds']==4
    assert result['reason']=='insufficient_unique_partitions'


def test_added_track_model_matches_sealed_numerical_predictor():
    rng=np.random.default_rng(7)
    t=np.tile(np.linspace(50,250,30),2)
    groups=np.repeat([0,1],30)
    q=np.repeat([.98,1.03],30)
    phase=np.linspace(-30,30,151)
    raw=rng.normal(0,150,(151,60))+np.repeat([300.,-600.],30)
    train=np.arange(60)%3!=0
    a=fit_predict(raw,t,q,groups,train,~train,phase)
    b=predict(raw,t,q,groups,groups+1,train,~train,phase,'track_offset',5.)
    assert b['training_score']==pytest.approx(a['training_score'],abs=1e-9)
    assert b['predictive_score']==pytest.approx(a['predictive_score'],abs=1e-9)
    assert b['phase_map_s']==a['phase_map_s']


def test_partitions_are_unique_synchronized_and_guarded():
    t=np.tile(np.arange(0,100,.5),2)
    groups=np.repeat([0,1],200)
    parts=partitions(t,groups)
    assert len(parts)==len({tuple(p['held_blocks']) for p in parts})==10
    blocks=np.floor(t/5).astype(int)
    for p in parts:
        assert not np.any(p['train'] & p['test'])
        assert not np.any(p['train'] & np.isin(blocks,p['guard_blocks']))


def test_generic_check_accepts_unlisted_context_and_rejects_noncausal_elements(monkeypatch):
    from types import SimpleNamespace
    t=np.arange(0,150,2.)
    tracks=[dict(times=t,rf_hz=11.5e9,receiver=i+1,key=f'example{i}',
                 values=np.full(len(t),200.),observation_ids=[f'{i}:{j}' for j in range(len(t))]) for i in range(2)]
    scan=SimpleNamespace(tracks=tracks,rx_basis=[np.zeros((len(t),1))]*2,
                         hardware=lambda track,beta:np.zeros(len(t)))
    base=SimpleNamespace(rows=[dict(candidate_norad=10)]*2,members=[0,1],
                         slices=[slice(0,len(t)),slice(len(t),2*len(t))],keep=np.ones(2*len(t),bool))
    cavity=SimpleNamespace(scan=scan,state=lambda point:dict(beta=[],smooth=np.zeros((2,1))))
    monkeypatch.setattr(validation.e,'build',lambda *args,**kwargs:(cavity,{}))
    def bank_for(ledger,origin):
        nums=np.array(sorted(map(int,ledger)))
        pos=np.zeros((2,2,3));pos[:,0,0]=nums*10
        return nums,dict(time_s=np.array([0.,150.]),position_km=pos,velocity_km_s=pos),[]
    monkeypatch.setattr(validation.e.rec,'bank_for',bank_for)
    monkeypatch.setattr(validation,'paired_phase_frequency',lambda bank,times,*args:
                        (np.full(len(times),bank['position_km'][0,0,0]),np.full(len(times),45.)))
    d=dict(scan=scan,problems={'fitted_c':(base,np.zeros(2))})
    z=dict(scan_receipt=dict(cutoff_utc_ns=10**15,origin_utc_ns=10**15))
    screen=dict(nominees=[10,20],cavity={a:dict(reference=[],x=[0.,0.]) for a in ('c0','fitted_c')})
    ledger={str(n):dict(element_epoch_utc_ns=10**15-10**9,collected_utc_ns=10**15-10**8) for n in (10,20)}
    out=validation.receiver_shared_check(d,z,screen,10,20,ledger)
    assert len(out['parts'])==10
    assert len(out['rows'])==40
    assert out['old']==10 and out['new']==20
    ledger['20']['collected_utc_ns']=10**15+1
    with pytest.raises(ValueError,match='scan-causal'):
        validation.receiver_shared_check(d,z,screen,10,20,ledger)
