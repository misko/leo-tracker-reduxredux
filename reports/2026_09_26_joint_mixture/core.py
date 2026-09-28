"""Collapsed assignment sampler with shared satellite time and integrated CFO."""
import numpy as np
from scipy.special import logsumexp


def block_average(times,values,mask):
    bins=np.floor(np.asarray(times)).astype(int);mask=np.asarray(mask,bool)
    return np.stack([np.mean(values[...,mask & (bins==b)],axis=-1) for b in np.unique(bins[mask])],axis=-1)


def intercept_evidence(residual,sigma,offset_sigma=1e6):
    """Normalized Gaussian likelihood integrated over b~Normal(0,offset_sigma)."""
    r=np.asarray(residual,float);n=r.shape[-1];v=sigma*sigma;B=offset_sigma**2
    avg=r.mean(axis=-1);center=np.sum((r-avg[...,None])**2,axis=-1)
    return -.5*(n*np.log(2*np.pi)+(n-1)*np.log(v)+np.log(v+n*B)+center/v+n*avg**2/(v+n*B))


def profiles(train,test,sigma):
    tr=intercept_evidence(train,sigma)
    return {'train':tr,'predict':intercept_evidence(np.concatenate([train,test],axis=-1),sigma)-tr,
            'n_test':test.shape[-1]}


def sample(options,priors,clock_logprior,original,*,seed=1,burn=100,draws=200):
    """Gibbs draws of identity + clock; satellite times analytically summed on grid.

    Never reads evaluation arrays. Null option represented by '__null__'.
    """
    rng=np.random.default_rng(seed);tids=sorted(options);ids=dict(original);clock=int(np.argmax(clock_logprior))
    priorid={t:{c:(np.log(.1) if c=='__null__' else np.log(.9/(len(options[t])-1))) for c in options[t]} for t in tids}
    states=[]
    def factors(ids,clock):
        groups={}
        for tid,cid in ids.items():
            if cid!='__null__':groups.setdefault(cid,[]).append(tid)
        return {cid:priors[cid]+sum(options[t][cid]['train'][clock] for t in members) for cid,members in groups.items()}
    def score(ids,clock):
        return sum(float(logsumexp(v)) for v in factors(ids,clock).values())+sum(
            priorid[t][c]+(float(options[t][c]['train'][clock,0]) if c=='__null__' else 0.) for t,c in ids.items())
    for sweep in range(burn+draws):
        # Cache group sums within this sweep; update just the affected groups.
        sums={}
        for t,c in ids.items():
            if c!='__null__':sums[c]=sums.get(c,0)+options[t][c]['train'][clock]
        for tid in rng.permutation(tids):
            old=ids[tid]
            if old!='__null__':sums[old]=sums[old]-options[tid][old]['train'][clock]
            choices=sorted(options[tid]);lp=[]
            for cid in choices:
                if cid=='__null__':value=float(options[tid][cid]['train'][clock,0])
                else:
                    before=priors[cid]+sums.get(cid,0)
                    value=float(logsumexp(before+options[tid][cid]['train'][clock])-logsumexp(before))
                lp.append(priorid[tid][cid]+value)
            prob=np.exp(np.array(lp)-logsumexp(lp));new=str(rng.choice(choices,p=prob));ids[tid]=new
            if new!='__null__':sums[new]=sums.get(new,0)+options[tid][new]['train'][clock]
        lp=np.array([score(ids,c) for c in range(len(clock_logprior))])+clock_logprior
        clock=int(rng.choice(len(lp),p=np.exp(lp-logsumexp(lp))))
        if sweep>=burn:states.append((dict(ids),clock))
    return states


def assess(options,priors,states):
    predictive={t:[] for t in options};counts={t:{} for t in options};bound=[]
    for ids,clock in states:
        groups={}
        for t,c in ids.items():
            if c!='__null__':groups.setdefault(c,[]).append(t)
        post={}
        for c,tt in groups.items():
            lp=priors[c]+sum(options[t][c]['train'][clock] for t in tt)
            post[c]=lp-logsumexp(lp);bound.append(float(np.exp(post[c][0])+np.exp(post[c][-1])))
        for t,c in ids.items():
            counts[t][c]=counts[t].get(c,0)+1
            predictive[t].append(float(options[t][c]['predict'][clock,0]) if c=='__null__' else
                float(logsumexp(post[c]+options[t][c]['predict'][clock])))
    tracks=[]
    for t,vals in predictive.items():
        probs={c:n/len(states) for c,n in counts[t].items()}
        tracks.append({'track_id':t,'probabilities':probs,'entropy_nats':float(-sum(p*np.log(p) for p in probs.values())),
            'predictive_log_score':float(logsumexp(vals)-np.log(len(vals))),
            'test_blocks':next(iter(options[t].values()))['n_test']})
    return {'composite_nll_per_test_block':-sum(r['predictive_log_score'] for r in tracks)/sum(r['test_blocks'] for r in tracks),
        'mean_null_probability':float(np.mean([r['probabilities'].get('__null__',0.) for r in tracks])),
        'ambiguous_tracks_maxprob_below_0_8':sum(max(r['probabilities'].values())<.8 for r in tracks),
        'max_endpoint_mass':max(bound,default=0.),'tracks':tracks}
