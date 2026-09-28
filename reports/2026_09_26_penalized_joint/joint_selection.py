"""Deterministic joint assignment with a prior penalty for identity changes."""
import numpy as np
from scipy.special import logsumexp


def select_joint(options,original,prior_logweights,change_penalty,max_passes=20):
    tids=sorted(options);variable=[t for t in tids if len(options[t])>1];cache={}
    if change_penalty<0:raise ValueError('nonnegative penalty required')
    def objective(ids):
        groups={}
        for tid,cid in ids.items():groups.setdefault(cid,[]).append(tid)
        score=-change_penalty*sum(cid!=original[tid] for tid,cid in ids.items())
        for cid,members in groups.items():
            key=(cid,tuple(sorted(members)))
            if key not in cache:cache[key]=float(logsumexp(prior_logweights[cid]+sum(options[t][cid]['train'] for t in members)))
            score+=cache[key]
        return score
    ranked={t:sorted(rr,key=lambda c:(-float(logsumexp(prior_logweights[c]+rr[c]['train']))-
        change_penalty*(c!=original[t]),str(c))) for t,rr in options.items()}
    seeds=[dict(original),{t:r[0] for t,r in ranked.items()}]
    for rank in range(1,max(map(len,ranked.values()))):seeds.append({t:r[rank%len(r)] for t,r in ranked.items()})
    runs=[]
    for seed in seeds:
        ids=seed.copy();score=objective(ids);initial=score
        for iteration in range(max_passes):
            changed=False
            for tid in variable:
                best=ids[tid];best_score=score
                for cid in ranked[tid]:
                    trial=dict(ids);trial[tid]=cid;value=objective(trial)
                    if value>best_score+1e-9:best=cid;best_score=value
                if best!=ids[tid]:changed=True;ids[tid]=best;score=best_score
            if not changed:break
        runs.append({'ids':ids,'training_score':score,'initial_training_score':initial,
            'passes':iteration+1,'converged':not changed,'changes':sum(c!=original[t] for t,c in ids.items())})
    best=max(runs,key=lambda r:(r['training_score'],-r['changes'],tuple((t,r['ids'][t]) for t in tids)))
    return best,{'starts':len(runs),'runs':runs,'cached_group_scores':len(cache)}
