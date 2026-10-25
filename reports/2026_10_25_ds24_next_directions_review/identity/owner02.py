"""Technical owner-harness repair only; preserve first results and total cap."""

import signal
import time
from pathlib import Path
import numpy as np
from scipy.linalg import solve_triangular
import review as m


def components(d,arm,x,entries):
    # Use the unchanged ORIGINAL parent builder, not the new-factor adapter.
    p=m.r.build(d,arm,d['arms'][arm]['phase_reference'])
    parent=p.curved_calculate(x) if d['entries'] else p.calculate(x)
    g=p.noise_groups[p.keep];weight=d['powers'][g]*parent['noise_precision'][g]/p.point_noise[p.keep]**2
    train=parent['features'][p.keep];gram=np.diag(parent['coefficient_prior_precision'])+train.T@(train*weight[:,None])
    root=np.linalg.cholesky(gram)
    view,values,sigma,groups,slices=m.original.linear_geometry(p,entries)
    hw=view.hardware.copy();hw[:,[4,6]]*=10
    ht=np.zeros((len(values),len(gram)));width=p.hardware.shape[1]+p.smooth.shape[1]
    ht[:,:width]=np.column_stack((hw,view.smooth*200));ut=solve_triangular(root,ht.T,lower=True).T
    if d['entries']:
        ev,ey,es,eg,_=m.original.linear_geometry(p,d['entries']);geo=m.original.geometry_features(ev,x,0.)
        he=geo['features'];raw=ey-ev.q*geo['intercept']-he@parent['coefficient']
        ue=solve_triangular(root,he.T,lower=True).T
        fe=np.column_stack((ue,np.eye(int(eg.max())+1)[eg]*300.))
        ft=np.column_stack((ut,np.zeros((len(ut),fe.shape[1]-len(gram)))))
        white=fe/(es*np.sqrt(2))[:,None];re=np.linalg.cholesky(np.eye(fe.shape[1])+white.T@white)
        mean=solve_triangular(re.T,solve_triangular(re,white.T@(raw/(es*np.sqrt(2))),lower=True),lower=False)
        update=ft@mean;uncertainty=solve_triangular(re,ft.T,lower=True).T
    else:update=np.zeros(len(ut));uncertainty=ut
    cov=np.diag(2*sigma**2)+uncertainty@uncertainty.T+300.**2*(groups[:,None]==groups[None,:])
    changed=dict(d,target_track=dict(times=view.flat_times,rf_hz=11.5e9))
    return dict(d=changed,x=np.asarray(x),raw=values-ht@parent['coefficient']-update,
        covariance=(cov+cov.T)/2,q=view.q,slices=slices,groups=groups,
        parent_coefficients=parent['coefficient'],parent_noise=parent['noise_precision'])


def run():
    first=m.r.read(m.HERE/'results.json');spent=first['seconds']
    m.write('owner02_protocol.json',dict(reason='initial harness called predictive adapter without branch rather than original parent builder',
        first_failed_result_sha256=m.r.sha(m.HERE/'results.json'),first_seal_sha256=m.r.sha(m.HERE/'seal.json'),
        first_seconds=spent,remaining_scientific_seconds=300-spent,
        new_candidates=False,position_fits=0,source_sha256=m.r.sha(Path(__file__))))
    start=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('remaining cumulative300s cap')));signal.alarm(max(1,int(300-spent)))
    rows=[];tests=[]
    try:
        item=next(row for row in m.r.read(m.HERE/'inventory.json')['rows'] if row['case']=='DS24-0013')
        target=item['target'];d=m.t.load_target(target)
        owners=[dict(component=target['component'],alias=target['alias'],observation_ids=target['observation_ids'])]+item['other_same_family_raw_sources']
        allids=[oid for owner in owners for oid in owner['observation_ids']]
        disjoint=len(allids)==len(set(allids)) and all(len(owner['observation_ids'])==len(set(owner['observation_ids'])) for owner in owners)
        tests.append(dict(test='native IDs unique within/across all four raw owners',points=len(allids),distinct=len(set(allids)),passed=disjoint))
        if not disjoint:raise ValueError('raw witness native IDs overlap; no trimming authorized')
        accepted=set().union(*(set(d['parent_membership'][arm]['accepted_observation_ids']) for arm in m.t.ARMS))
        if accepted & set(allids):raise ValueError('raw witness overlaps complete parent accepted IDs')
        entries=[]
        for owner in owners:
            i=next(i for i,track in enumerate(d['scan'].tracks) if track['key']==owner['component'])
            entries.append(dict(track_index=i,component=owner['component'],candidate_index=target['candidate_index'],
                alias=owner['alias'],observation_ids=owner['observation_ids'],points=len(owner['observation_ids'])))
        for arm in m.t.ARMS:
            x=np.asarray(d['arms'][arm]['endpoint_east_north_km']);comp=components(d,arm,x,entries)
            allidx=np.arange(len(comp['raw']));scores={}
            for count in (1281,2561):
                scores[count]=dict(joint=m.multi_score(comp,count,allidx),owners=[])
                for index,sl in enumerate(comp['slices']):
                    own=np.arange(sl.start,sl.stop);other=np.setdiff1d(allidx,own)
                    marginal=m.multi_score(comp,count,own);rest=m.multi_score(comp,count,other)
                    scores[count]['owners'].append(dict(component=entries[index]['component'],points=len(own),
                        marginal_NLL=marginal['objective'],others_NLL=rest['objective'],
                        conditional_NLL=scores[count]['joint']['objective']-rest['objective']))
            p=m.q.build(d,arm,d['arms'][arm]['phase_reference'],m.t.BRANCHES[1],1281)
            single=m.q.integrate(d,m.q.conditional_components(d,p,x),1281,True)['objective']
            error=abs(single-scores[1281]['owners'][0]['marginal_NLL'])
            tests.append(dict(test='original single-source equivalence including RF/q scaling',arm=arm,error=error,passed=error<=1e-6))
            row=dict(case=item['case'],arm=arm,owners=entries,scores=scores,identity_qualified=False,
                maximum_1281_2561_score_difference=max(abs(scores[1281]['joint']['objective']-scores[2561]['joint']['objective']),
                    *(abs(a['conditional_NLL']-b['conditional_NLL']) for a,b in zip(scores[1281]['owners'],scores[2561]['owners']))))
            rows.append(row)
        result=dict(status='complete',owner_challenges=rows,tests=tests,all_tests_passed=all(v['passed'] for v in tests),
            seconds=time.monotonic()-start,cumulative_scientific_seconds=spent+time.monotonic()-start,
            position_fits=0,GPS_used=False,identity_qualified=False)
    except Exception as exc:
        import traceback
        result=dict(status='failed',error=repr(exc),traceback=traceback.format_exc(),owner_challenges=rows,tests=tests,
            seconds=time.monotonic()-start,cumulative_scientific_seconds=spent+time.monotonic()-start,
            position_fits=0,GPS_used=False,identity_qualified=False)
    finally:signal.alarm(0)
    m.write('owner02_results.json',result)
    m.write('owner02_seal.json',dict(files={name:m.r.sha(m.HERE/name) for name in ('owner02.py','owner02_protocol.json','owner02_results.json')},
        original_seal_sha256=m.r.sha(m.HERE/'seal.json'),position_fits=0,GPS_used=False))
    print(m.r.json.dumps(result,default=m.r.encode,indent=2))


if __name__=='__main__':run()
