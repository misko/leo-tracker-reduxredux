"""Deterministic exact soft assignment with track-independent TLE timing."""
import numpy as np
from scipy.special import logsumexp


def block_average(times,values,mask):
    bins=np.floor(np.asarray(times)).astype(int);mask=np.asarray(mask,bool)
    return np.stack([np.mean(values[...,mask & (bins==b)],axis=-1) for b in np.unique(bins[mask])],axis=-1)


def intercept_evidence(residual,sigma,offset_sigma=1e6):
    r=np.asarray(residual,float);n=r.shape[-1];v=sigma*sigma;B=offset_sigma**2
    avg=r.mean(axis=-1);center=np.sum((r-avg[...,None])**2,axis=-1)
    return -.5*(n*np.log(2*np.pi)+(n-1)*np.log(v)+np.log(v+n*B)+center/v+n*avg**2/(v+n*B))


def profiles(train,test,sigma):
    tr=intercept_evidence(train,sigma)
    return {'train':tr,'predict':intercept_evidence(np.concatenate([train,test],axis=-1),sigma)-tr,
        'n_test':test.shape[-1]}


def _identity_logprior(candidates, null_mass):
    candidates=sorted(candidates);real=[c for c in candidates if c!='__null__']
    if not real:raise ValueError('at least one satellite candidate is required')
    if '__null__' not in candidates:
        return {c:-np.log(len(real)) for c in real}
    if not 0<null_mass<1:raise ValueError('null_mass must be in (0,1)')
    return {c:(np.log(null_mass) if c=='__null__' else np.log1p(-null_mass)-np.log(len(real)))
        for c in candidates}


def exact_soft(options,priors,clock_logprior,*,null_mass=.1):
    """Marginalize identity, per-track timing, and optional shared scan clock.

    Candidate identity and timing are inferred from training evidence only. Test
    evidence is used only in the returned conditional predictive scores.
    """
    clock_logprior=np.asarray(clock_logprior,float)
    clock_logprior=clock_logprior-logsumexp(clock_logprior)
    tids=sorted(options);train={};joint={};candidate_train={};n_test={}
    for tid in tids:
        idlp=_identity_logprior(options[tid],null_mass);candidate_train[tid]={}
        tz=[];jz=[]
        for cid,row in sorted(options[tid].items()):
            tr=np.asarray(row['train'],float);pred=np.asarray(row['predict'],float)
            if tr.shape!=pred.shape or tr.ndim!=2 or tr.shape[0]!=len(clock_logprior):
                raise ValueError('profile shape mismatch')
            if cid=='__null__':
                ct=tr[:,0];cj=tr[:,0]+pred[:,0]
            else:
                lp=np.asarray(priors[cid],float)
                if len(lp)!=tr.shape[1] or abs(float(logsumexp(lp)))>1e-8:
                    raise ValueError('normalized timing prior required')
                ct=logsumexp(lp[None,:]+tr,axis=1)
                cj=logsumexp(lp[None,:]+tr+pred,axis=1)
            candidate_train[tid][cid]=ct+idlp[cid]
            tz.append(ct+idlp[cid]);jz.append(cj+idlp[cid])
            n_test.setdefault(tid,row['n_test'])
            if n_test[tid]!=row['n_test']:raise ValueError('candidate test denominator mismatch')
        train[tid]=logsumexp(np.stack(tz),axis=0)
        joint[tid]=logsumexp(np.stack(jz),axis=0)
    clock_train=clock_logprior+sum(train.values())
    clock_post=clock_train-logsumexp(clock_train)
    tracks=[]
    for tid in tids:
        pred=joint[tid]-train[tid]
        logscore=float(logsumexp(clock_post+pred))
        probs={cid:float(np.exp(logsumexp(clock_post+lp-train[tid])))
            for cid,lp in candidate_train[tid].items()}
        norm=sum(probs.values());probs={c:p/norm for c,p in probs.items()}
        tracks.append({'track_id':tid,'probabilities':probs,
            'entropy_nats':float(-sum(p*np.log(p) for p in probs.values() if p>0)),
            'predictive_log_score':logscore,'test_blocks':n_test[tid]})
    total_blocks=sum(n_test.values())
    full_score=float(logsumexp(clock_logprior+sum(joint.values()))-logsumexp(clock_train))
    return {'composite_nll_per_test_block':-sum(t['predictive_log_score'] for t in tracks)/total_blocks,
        'full_scan_nll_per_test_block':-full_score/total_blocks,
        'mean_null_probability':float(np.mean([t['probabilities'].get('__null__',0.) for t in tracks])),
        'ambiguous_tracks_maxprob_below_0_8':sum(max(t['probabilities'].values())<.8 for t in tracks),
        'clock_probabilities':np.exp(clock_post).tolist(),'tracks':tracks}
