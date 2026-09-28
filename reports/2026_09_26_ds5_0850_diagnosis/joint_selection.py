"""Training-only coordinate search for a bounded identity/timing diagnostic."""
import numpy as np
from scipy.special import logsumexp


def select_joint(options, original, prior_logweights, max_passes=20):
    """Multi-start coordinate ascent of integrated shared-timing training score.

    This is not exhaustive identity marginalization. Test observations are never
    consulted. Unchanged singleton-option tracks constrain shared satellite time.
    """
    tids=sorted(options);variable=[tid for tid in tids if len(options[tid])>1]
    cache={}
    def objective(ids):
        groups={}
        for tid,cid in ids.items():groups.setdefault(cid,[]).append(tid)
        score=0.
        for cid,members in groups.items():
            key=(cid,tuple(sorted(members)))
            if key not in cache:
                cache[key]=float(logsumexp(prior_logweights[cid]+sum(options[tid][cid]['train'] for tid in members)))
            score+=cache[key]
        return score
    ranked={tid:sorted(opts,key=lambda cid:(-float(logsumexp(prior_logweights[cid]+opts[cid]['train'])),int(cid))) for tid,opts in options.items()}
    seeds=[dict(original),{tid:r[0] for tid,r in ranked.items()}]
    for rank in range(1,max(map(len,ranked.values()))):
        seeds.append({tid:r[rank%len(r)] for tid,r in ranked.items()})
    runs=[]
    for seed in seeds:
        ids=seed.copy();score=objective(ids);initial=score
        for iteration in range(max_passes):
            changed=False
            for tid in variable:
                best=ids[tid];best_score=score
                for cid in ranked[tid]:
                    trial=dict(ids);trial[tid]=cid;value=objective(trial)
                    if value>best_score+1e-9:
                        best=cid;best_score=value
                if best!=ids[tid]:changed=True;ids[tid]=best;score=best_score
            if not changed:break
        runs.append({'ids':ids,'training_score':score,'initial_training_score':initial,
            'passes':iteration+1,'converged':not changed})
    best=max(runs,key=lambda x:x['training_score'])
    return best,{'starts':len(runs),'runs':runs,'cached_group_scores':len(cache)}
