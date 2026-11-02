"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import numpy as np
from scipy.special import logsumexp
from leo.analysis.research.retained_track_likelihood import PERIOD


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
