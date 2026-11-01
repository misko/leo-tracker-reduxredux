"""Random synchronized-block conditional prediction for the 0070 partition.

The candidate universe was previously discovered on full data, so this is a
conditional model check, not independent catalogue or population validation.
Calibration is frozen from the original complete-family omission fit.
"""
import numpy as np
from scipy.special import logsumexp
from experiment import OUT,PRIOR,INPUT,read,write,reconstruct,ORIGINAL_BUILD,ARMS
from track_debug import bank_for
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon

def fit_predict(raw,t,q,groups,train,test,phase):
    unique=np.unique(groups);lift=raw.copy();aliases=np.zeros((len(phase),len(unique)),int)
    for k,g in enumerate(unique):
        m=(groups==g)&train
        if not m.any():raise ValueError('every source needs training evidence for its alias')
        aliases[:,k]=np.rint(-raw[:,m].mean(axis=1)/PERIOD).astype(int)
        lift[:,groups==g]+=aliases[:,k,None]*PERIOD
    design=np.column_stack([(groups==g)*300. for g in unique]+[q*(t-150)*.5])/150.
    u=design[train];cov=np.linalg.inv(np.eye(u.shape[1])+u.T@u)
    beta=(lift[:,train]/150.)@u@cov
    residual=lift/150.-beta@design.T
    train_cost=np.sum(residual[:,train]**2,axis=1)+np.sum(beta**2,axis=1)+np.linalg.slogdet(np.eye(u.shape[1])+u.T@u)[1]+train.sum()*np.log(2*np.pi*150**2)
    logprior=-.5*(phase/5.)**2;logprior-=logsumexp(logprior)
    logpost=logprior-.5*train_cost;train_evidence=-2*logsumexp(logpost);logpost-=logsumexp(logpost)
    v=design[test];vgram=np.eye(v.shape[1])+cov@v.T@v
    # Woodbury predictive covariance: I + V C V' with standardized noise.
    a=residual[:,test];correction=np.linalg.solve(np.linalg.inv(cov)+v.T@v,np.eye(cov.shape[0]))
    quad=np.sum(a*a,axis=1)-np.einsum('ij,jk,ik->i',a@v,correction,a@v)
    test_cost=quad+np.linalg.slogdet(vgram)[1]+test.sum()*np.log(2*np.pi*150**2)
    predictive=-2*logsumexp(logpost-.5*test_cost)
    k=int(np.argmax(logpost))
    return dict(training_score=float(train_evidence),predictive_score=float(predictive),phase_map_s=float(phase[k]),
        training_track_cost={int(g):float(np.sum(residual[k,(groups==g)&train]**2)) for g in unique},
        alias_by_group=dict(zip(map(int,unique),map(int,aliases[k]))))

def run():
    case='DS26-0070';z=read(INPUT/(case+'.json'));d=reconstruct(z);p=d['problems']['fitted_c'][0]
    f=read(PRIOR/case/'family_diagnostic.json');keys=[r['key'] for r in f['tracks']];tracks=[]
    for key in keys:
        k=next(k for k,row in enumerate(p.rows) if row['component']==key);i=p.members[k];tracks.append((i,p.keep[p.slices[k]]))
    times=np.concatenate([d['scan'].tracks[i]['times'][use] for i,use in tracks]);q=np.concatenate([np.full(use.sum(),d['scan'].tracks[i]['rf_hz']/11.5e9) for i,use in tracks])
    group=np.concatenate([np.full(use.sum(),k) for k,(i,use) in enumerate(tracks)]);blocks=np.floor(times/5).astype(int);available=np.unique(blocks)
    rng=np.random.default_rng(20261102);splits=[]
    for fold in range(10):
        for attempt in range(10000):
            held=np.sort(rng.choice(available,size=max(1,round(.2*len(available))),replace=False));guard=np.unique(np.r_[held-1,held,held+1])
            train=~np.isin(blocks,guard);test=np.isin(blocks,held)
            if all(((group==g)&train).sum()>=5 and ((group==g)&test).sum()>=2 for g in np.unique(group)):break
        else:raise ValueError('unable to construct declared synchronized holdout')
        splits.append(dict(fold=fold,held_blocks=held,excluded_training_blocks=guard,train=train,test=test,rejections_before_valid=attempt))
    write(OUT/'predictive_protocol.json',dict(seed=20261102,case=case,block_seconds=5,guard_seconds=5,folds=10,splits=splits,
        candidates=[62320,63571,67047],family_offset_prior_hz=300,shared_rate_prior_hz_s=.5,phase_prior_s=5,noise_hz=150,
        phase_grid_s=[-30,30,.2],radio_and_position='frozen RF-only complete-family-omission fit; never evaluation site',
        assignment='relearn whole-track labels from training residual costs, then jointly refit each proposed label',
        limits='conditional on previously discovered candidate catalogue and graph tracks; not untouched-scan validation'))
    ledger=read(PRIOR/case/'tle-ledger.json')['causal'];nums,bank,_=bank_for({str(n):ledger[str(n)] for n in [62320,63571,67047]},z['scan_receipt']['origin_utc_ns'])
    pp=np.linspace(-30,30,301);results=[]
    for arm in ARMS:
        saved=read(PRIOR/case/'extended_omit_62320.json')[arm]
        cavity,_=ORIGINAL_BUILD(d,z,arm,np.array(saved['reference']),omit=62320);point=np.array(saved['x']);state=cavity.state(point)
        values=np.concatenate([(tr['values']-cavity.scan.hardware(tr,state['beta'])-tr['rf_hz']/11.5e9*d['scan'].rx_basis[i]@state['smooth'][tr['receiver']-1])[use] for i,use in tracks for tr in [d['scan'].tracks[i]]])
        raw={}
        for j,n in enumerate(nums):
            bb=dict(time_s=bank['time_s'],position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
            ff,ee=paired_phase_frequency(bb,np.tile(times,len(pp)),np.repeat(np.arange(len(pp)),len(times)),pp,*latlon(point))
            if np.min(ee)<0:raise ValueError('this check requires common visibility across its bounded phase grid')
            raw[int(n)]=values[None,:]-ff.reshape(len(pp),-1)*q
        for split in splits:
            train,test=split['train'],split['test'];whole={n:fit_predict(y,times,q,group,train,test,pp) for n,y in raw.items()}
            mapping={g:min(whole,key=lambda n:whole[n]['training_track_cost'][g]) for g in map(int,np.unique(group))}
            predicted=0.;training=0.;per=[]
            for n in sorted(set(mapping.values())):
                selected=np.isin(group,[g for g in mapping if mapping[g]==n]);r=fit_predict(raw[n][:,selected],times[selected],q[selected],group[selected],train[selected],test[selected],pp)
                predicted+=r['predictive_score'];training+=r['training_score'];per.append(dict(norad=n,**r))
            penalty=2*max(0,len(set(mapping.values()))-1)*np.log(train.sum())
            best_single=min(whole,key=lambda n:whole[n]['training_score']);choose_split=training+penalty<whole[best_single]['training_score']
            results.append(dict(arm=arm,fold=split['fold'],train_points=int(train.sum()),held_points=int(test.sum()),whole=whole,
                learned_mapping=mapping,partition_training_score=training,partition_penalty=penalty,partition_predictive_score=predicted,
                best_training_single=best_single,training_selects_partition=choose_split,
                held_gain_over_training_best_single=whole[best_single]['predictive_score']-predicted,
                selected_predictive_score=predicted if choose_split else whole[best_single]['predictive_score'],per_family=per))
    write(OUT/'predictive_results.json',dict(case=case,track_keys=keys,results=results));print([(a,np.median([r['held_gain_over_training_best_single'] for r in results if r['arm']==a])) for a in ARMS])

if __name__=='__main__':run()
