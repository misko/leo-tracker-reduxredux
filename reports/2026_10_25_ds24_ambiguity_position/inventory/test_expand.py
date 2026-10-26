"""Owned pool/selection controls; scientific algebra is the frozen old kernel."""
import copy
import ledger as L
from expand import pick,ranks,interrupt_rows

def row(case,component,gain=.05,**kw):
    return dict(case=case,component=component,paired_ranking_score=gain,points=20,span_s=30,eligible=True,status='complete',unexhausted_within_declared_audit=True,**kw)

def test_threshold_chronology_exposure_and_four_case_cap():
    cases=list(L.OLD_FOUR)+[f'DS24-{i:04d}' for i in range(14,20)]
    r=[row(c,c) for c in cases];r.append(row('DS24-0014','higher',.9));r.append(row('DS24-0015','already-worked',.99))
    r[-1]['unexhausted_within_declared_audit']=False;r[4]['paired_ranking_score']=.049999
    out=pick(r,cases)
    assert [q['case'] for q in out]==cases[4:8]
    assert out[0]['component']=='higher' and out[1]['component']!='already-worked'

def test_blocked_count_winner_is_retained_not_replaced():
    a=row('c','long',.9);a.update(status='blocked',points=200)
    b=row('c','short',.1);r=[a,b];ranks(r,['c'])
    assert a['count_rank']==1 and 'information_rank' not in a
    assert b['information_rank']==1 and b['count_rank']==2

def test_complete_postfit_overlap_and_missing_ownership_block():
    t=dict(key='t',times=[1.,2.],observation_ids=['a','b'],receiver='RX1',channel=1,rf_hz=1.)
    rr=dict(component='t',points=2,active_curvature=True,candidate_index=3,candidate_norad=4,compatible=False)
    p=dict(accepted=False,baseline_node=dict(seed=dict(rows=[rr]),aliases=[0]),baseline_entries=[],original_mask=[False,False])
    cov={a:dict(curved_observation_ids=[],predictive_observation_ids=[],accepted_observation_ids=['b'],postfit_only_observation_ids=['b'],active_curved_families=[]) for a in L.ARMS}
    q=L.make_rows('c',[t],p,cov,{})[0]
    assert not q['eligible'] and q['postfit_only_ID_overlap']['c0']==['b']
    cov['c0']['accepted_observation_ids']=[];cov['c0']['postfit_only_observation_ids']=[]
    assert not L.make_rows('c',[t],p,cov,{})[0]['eligible']
    assert not L.make_rows('c',[t],p,None,{})[0]['eligible']

def test_partial_arm_timeout_preserves_arm_without_complete_rank():
    q=row('c','partial');q.update(status='in_progress',arms={'c0':{'status':'complete','sentinel':12}})
    done=row('c','done');done['arms']={a:{'status':'complete'} for a in L.ARMS}
    unstarted=row('c','unstarted');unstarted.pop('status')
    r=[q,done,unstarted];interrupt_rows(r,'deadline');ranks(r,['c'])
    assert q['status']=='unavailable' and q['arms']['c0']['sentinel']==12
    assert 'information_rank' not in q and 'information_rank' not in unstarted
    assert done['status']=='complete' and done['information_rank']==1
