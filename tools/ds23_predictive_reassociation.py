"""Discrete predictive reassociation with full shared calibration covariance.

Every pool represents the same physical track. Selecting a label never changes
that track's data or noise. Predictive observations do not update the curved
calibration posterior; their shared conditional covariance is used for scoring.
"""

import numpy as np
import copy
import itertools

from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.retained_track_likelihood import PERIOD


def curved_alias(raw,sigma):
    r,s=np.asarray(raw,float),np.asarray(sigma,float)
    if r.ndim!=1 or not len(r) or s.shape!=r.shape or not np.isfinite(r).all() or not np.isfinite(s).all() or np.any(s<=0):
        raise ValueError('finite curve residuals and matching positive noise required')
    weight=1/s**2
    return int(np.rint(-np.sum(r*weight)/sum(weight)/PERIOD))


def family_pattern_product(nodes,active_components,*,maximum=512):
    """Recombine observed within-family assignment patterns, with a hard cap.

    A pattern can split an old family; no artificial same-label requirement is
    imposed on its fragments. Inactive-only alternatives do not inflate search.
    """
    if not nodes or maximum<1:raise ValueError('nodes and positive search cap required')
    base=nodes[0];rows=base['seed']['rows'];keys=[r['component'] for r in rows]
    if len(set(keys))!=len(keys):raise ValueError('unique curved components required')
    if any([r['component'] for r in n['seed']['rows']]!=keys for n in nodes):
        raise ValueError('all family hypotheses need identical physical row order')
    groups={}
    for k,r in enumerate(rows):groups.setdefault(r['candidate_index'],[]).append(k)
    pools=[];metadata=[]
    for label,indices in groups.items():
        active=[k for k in indices if keys[k] in active_components]
        if not active:continue
        patterns=[];seen=set()
        for n in nodes:
            signature=tuple((n['seed']['rows'][k]['candidate_index'],int(n['aliases'][k])) for k in active)
            if signature not in seen:
                seen.add(signature);patterns.append([(k,copy.deepcopy(n['seed']['rows'][k]),n['aliases'][k]) for k in indices])
        if len(patterns)>1:
            pools.append(patterns);metadata.append(dict(original_candidate_index=label,
                original_norad=rows[indices[0]]['candidate_norad'],active_components=[keys[k] for k in active],patterns=len(patterns)))
    count=int(np.prod([len(p) for p in pools],dtype=np.int64)) if pools else 1
    if count>maximum:raise ValueError('family product exceeds predeclared bounded search cap')
    result=[]
    for choices in itertools.product(*pools):
        node=copy.deepcopy(base)
        for pattern in choices:
            for k,row,alias in pattern:node['seed']['rows'][k]=row;node['aliases'][k]=alias
        result.append(node)
    return result,dict(groups=metadata,hypotheses=count,maximum=maximum,
                       all_combinations_of_observed_active_family_patterns=True)


def block_objective(blocks, *, bias_sigma_hz=300.):
    """Exact Gaussian predictive density for a particular discrete assignment."""
    if not blocks or bias_sigma_hz<=0:
        raise ValueError('nonempty predictive blocks and positive bias scale required')
    raw=np.concatenate([b['raw'] for b in blocks])
    u=np.vstack([b['uncertainty'] for b in blocks])
    sigma=np.concatenate([b['sigma'] for b in blocks])
    if u.ndim!=2 or u.shape[0]!=len(raw) or sigma.shape!=raw.shape or not np.isfinite(u).all() or not np.isfinite(raw).all() or not np.isfinite(sigma).all() or np.any(sigma<=0):
        raise ValueError('matching finite predictive arrays and positive noise required')
    covariance=u@u.T+np.diag(sigma**2)
    start=0
    for b in blocks:
        stop=start+len(b['raw']);covariance[start:stop,start:stop]+=bias_sigma_hz**2;start=stop
    root=np.linalg.cholesky(covariance);white=np.linalg.solve(root,raw)
    return float(white@white+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi))


def select_assignment(pools, *, top_k=3, sweeps=3):
    """Bounded coordinate descent; retain original label if still supported."""
    if not pools or any(not pool for pool in pools) or top_k<1 or sweeps<1:
        raise ValueError('one nonempty candidate pool per physical track required')
    shortlisted=[];single_scores=[]
    for pool in pools:
        scores=[block_objective([b]) for b in pool];single_scores.append(scores)
        chosen=list(np.argsort(scores,kind='stable')[:top_k])
        chosen.extend(i for i,b in enumerate(pool) if b.get('incumbent',False) and i not in chosen)
        shortlisted.append(chosen)
    selected=[int(np.argmin(scores)) for scores in single_scores]
    cache={}
    def objective(indices):
        key=tuple(indices)
        if key not in cache:cache[key]=block_objective([pool[i] for pool,i in zip(pools,indices,strict=True)])
        return cache[key]
    current=objective(selected);history=[dict(sweep=-1,objective=current,indices=selected.copy())]
    for sweep in range(sweeps):
        changed=0
        for k,choices in enumerate(shortlisted):
            best=current;best_index=selected[k]
            for candidate in choices:
                proposed=selected.copy();proposed[k]=int(candidate);cost=objective(proposed)
                if cost<best-1e-8:best=cost;best_index=int(candidate)
            if best_index!=selected[k]:changed+=1
            selected[k]=best_index;current=best
        history.append(dict(sweep=sweep,objective=current,indices=selected.copy(),changes=changed))
        if not changed:break
    return dict(indices=selected,objective=current,history=history,evaluations=len(cache),
                all_pool_sizes=[len(p) for p in pools],shortlist_sizes=list(map(len,shortlisted)),
                full_shared_covariance=True,no_global_assignment_optimality_claim=True)


def proposal_pools(p,position,original_entries,powers):
    """All curved-supported satellite labels, independent of original families."""
    c=p.calculate(position);group=p.noise_groups[p.keep]
    w=np.asarray(powers)[group]*c['noise_precision'][group]/p.point_noise[p.keep]**2
    u=c['features'][p.keep]
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
    root=np.linalg.cholesky(gram)
    labels=sorted({row['candidate_index'] for row,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()})
    offered=[]
    for original in original_entries:
        for label in labels:
            offered.append(dict(original,candidate_index=label,norad=int(p.scan.norads[label]),alias=0))
    view,values,sigma,_,slices=linear_geometry(p,offered)
    geometry=geometry_features(view,position,0.)
    mean=view.q*geometry['intercept']+geometry['features']@c['coefficient']
    uncertainty=np.linalg.solve(root,geometry['features'].T).T
    pools=[[] for _ in original_entries]
    for k,(entry,sl) in enumerate(zip(offered,slices,strict=True)):
        track_number=k//len(labels);original=original_entries[track_number]
        raw=values[sl]-mean[sl]
        alias=curved_alias(raw,sigma[sl])
        # The alias is proposed using curved calibration and candidate orbital
        # prediction; no linear-track fitted calibration enters this decision.
        entry=dict(entry,alias=alias,association_source='full_covariance_predictive_reassociation')
        pools[track_number].append(dict(entry=entry,raw=raw+alias*PERIOD,
            uncertainty=uncertainty[sl],sigma=sigma[sl]*np.sqrt(2),
            incumbent=entry['candidate_index']==original['candidate_index'] and alias==original['alias']))
    for original,pool in zip(original_entries,pools,strict=True):
        if any(b['entry']['observation_ids']!=original['observation_ids'] or b['entry']['track_index']!=original['track_index'] for b in pool):
            raise ValueError('reassociation changed physical predictive support')
    return pools
