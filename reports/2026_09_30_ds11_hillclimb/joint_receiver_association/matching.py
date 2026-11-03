"""Exact soft partial bipartite matching with a normalized matching prior.

Rows/columns represent mutually exclusive track hypotheses on opposite RXs.
This primitive does not resolve shared raw observations inside one RX; callers
must provide disjoint units or an explicit additional observation-assignment model.
"""
import numpy as np
from scipy.special import logsumexp

def partition(log_edges, *, marginals=True, max_columns=16):
    edges=np.asarray(log_edges,dtype=float)
    if edges.ndim!=2 or np.isnan(edges).any() or np.isposinf(edges).any():
        raise ValueError('edges must be a finite-or-negative-infinity matrix')
    transposed=edges.shape[1]>edges.shape[0]
    if transposed:edges=edges.T
    n,m=edges.shape
    if m>max_columns:raise ValueError('exact matching state budget exceeded; do not silently prune')
    states=1<<m
    forward=np.full((n+1,states),-np.inf);forward[0,0]=0.
    for i in range(n):
        forward[i+1]=forward[i]
        for mask in range(states):
            if not np.isfinite(forward[i,mask]):continue
            for j in range(m):
                if not mask&(1<<j) and np.isfinite(edges[i,j]):
                    target=mask|(1<<j)
                    forward[i+1,target]=np.logaddexp(forward[i+1,target],forward[i,mask]+edges[i,j])
    normal=float(logsumexp(forward[n]))
    if not marginals:return normal
    backward=np.zeros((n+1,states))
    for i in range(n-1,-1,-1):
        for mask in range(states):
            values=[backward[i+1,mask]]
            values.extend(edges[i,j]+backward[i+1,mask|(1<<j)] for j in range(m) if not mask&(1<<j))
            backward[i,mask]=logsumexp(values)
    posterior=np.zeros((n,m))
    for i in range(n):
        for j in range(m):
            if not np.isfinite(edges[i,j]):continue
            terms=[forward[i,mask]+edges[i,j]+backward[i+1,mask|(1<<j)]-normal
                   for mask in range(states) if not mask&(1<<j)]
            posterior[i,j]=np.exp(logsumexp(terms))
    if transposed:posterior=posterior.T
    return normal,posterior

def evidence(left_scores,right_scores,pair_scores,log_prior_edges):
    left=np.asarray(left_scores,dtype=float);right=np.asarray(right_scores,dtype=float)
    pairs=np.asarray(pair_scores,dtype=float);prior=np.asarray(log_prior_edges,dtype=float)
    if left.ndim!=1 or right.ndim!=1 or pairs.shape!=(len(left),len(right)) or prior.shape!=pairs.shape:
        raise ValueError('score cardinalities do not match')
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError('single-unit alternatives must have finite support')
    if np.isnan(pairs).any() or np.isposinf(pairs).any():raise ValueError('invalid pair score')
    prior_normal=partition(prior,marginals=False)
    gain=pairs-left[:,None]-right[None,:]
    normal,posterior=partition(prior+gain)
    return dict(log_evidence=float(left.sum()+right.sum()+normal-prior_normal),
                pair_posterior=posterior,left_unmatched=np.maximum(0.,1-posterior.sum(axis=1)),
                right_unmatched=np.maximum(0.,1-posterior.sum(axis=0)),log_prior_normalizer=prior_normal)
